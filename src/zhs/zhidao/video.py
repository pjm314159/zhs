"""知到视频播放器

ZhidaoVideoPlayer 实现视频播放主循环，包含：
- 进度模拟（速度控制、随机暂停、人类延迟）
- 弹窗答题（延迟机制）
- 进度上报（V2 格式）
- 线程安全的视频流请求
"""

import contextlib
import json
import re
import threading
import time
from base64 import b64encode
from random import randint, random, uniform
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from zhs.crypto import WatchPoint, encode_ev
from zhs.exceptions import ApiError, CaptchaRequired, TimeLimitExceeded
from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, progress_bar, tree_print, wipe_line

if TYPE_CHECKING:
    from zhs.session import ZhsSession
    from zhs.zhidao.models import PopupQuestion, QuestionPoint, ZhidaoContext


CLASSIC_CACHE_INTERVAL = 180
CLASSIC_DB_INTERVAL = 300
CLASSIC_INTERVAL_JITTER = 5
# Database 上报失败后的重试间隔（秒）
DB_RETRY_DELAY = 30
# 随机暂停：触发概率与暂停时长（秒）
PAUSE_CHANCE = 0.0025
PAUSE_SECONDS = 60


def _hms(seconds: int) -> str:
    """播放位置格式化为网页端的 HH:MM:SS。"""
    hours, rest = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _jitter(interval: int) -> int:
    """给心跳间隔加 ±CLASSIC_INTERVAL_JITTER 秒抖动，避免严格等距"""
    return interval + randint(-CLASSIC_INTERVAL_JITTER, CLASSIC_INTERVAL_JITTER)


def _advance(position: float, speed: float, duration: int) -> float:
    """播放位置前进 speed 秒；到底后回到开头（等价网页端的重看）"""
    if duration <= 0:
        return position
    return (position + speed) % duration


class ZhidaoVideoPlayer:
    """知到视频播放器"""

    def __init__(
        self,
        session: "ZhsSession",
        speed: float | None = None,
        end_threshold: float = 0.91,
        time_limit: int = 0,
    ) -> None:
        self._session = session
        self._speed = speed
        self.end_threshold = end_threshold
        self._time_limit = time_limit
        self._progress_line: str | None = None
        self._resume_time = 0.0

    def _print_with_progress(self, text: str, depth: int = 0, enabled: bool = True) -> None:
        """打印消息，保持进度条在底部（若激活则清除→打印→重印进度条）"""
        if not enabled:
            return
        indent = "  " * depth
        if self._progress_line is not None:
            wipe_line()
            print(f"{indent}{text}")
            print(f"\r{self._progress_line}", end="", flush=True)
        else:
            print(f"{indent}{text}")

    def _clear_progress(self) -> None:
        """清除进度条（若激活）"""
        if self._progress_line is not None:
            wipe_line()
            self._progress_line = None

    def play_course(self, rac_id: str, ctx: "ZhidaoContext") -> None:
        """播放整个课程，遍历所有章节/课时/子视频

        单个视频失败不中断整个课程，记录错误后继续下一个视频。
        """
        course = ctx.course
        course_name = course.course_info.name if course.course_info else course.course_name
        begin_time = time.time()
        tv = True
        logger.info(f"play_course: {course_name}, chapters={len(ctx.chapters)}")
        self._print_with_progress(f"{course_tag('zhidao')} 新课程: {course_name}", enabled=tv)

        for chapter in ctx.chapters:
            self._print_with_progress(f"章节: {chapter.name}", depth=1, enabled=tv)
            for lesson in chapter.video_lessons:
                self._print_with_progress(f"课时: {lesson.name}", depth=2, enabled=tv)
                for video in lesson.video_small_lessons:
                    try:
                        self.play_video(rac_id, video.video_id, ctx)
                    except CaptchaRequired:
                        self._clear_progress()
                        logger.warning(
                            "Course stopped: captcha required (racId={}, course={}, videoId={})",
                            rac_id,
                            course_name,
                            video.video_id,
                        )
                        tree_print(msg_warn("!! 需要验证码，停止课程"), depth=3, enabled=tv)
                        return
                    except TimeLimitExceeded:
                        self._clear_progress()
                        logger.warning(
                            "Course stopped: study time limit reached (racId={}, course={}, videoId={})",
                            rac_id,
                            course_name,
                            video.video_id,
                        )
                        tree_print(msg_warn("!! 学习时间已达上限，停止课程"), depth=3, enabled=tv)
                        return
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        self._clear_progress()
                        logger.error(
                            "Video failed: {} (racId={}, videoId={}) - {}",
                            video.name,
                            rac_id,
                            video.video_id,
                            exc,
                        )
                        tree_print(msg_error(f"!! 视频失败: {video.name} - {exc}"), depth=3, enabled=tv)
                        continue

        cost = time.time() - begin_time
        self._clear_progress()

        logger.info("play_course done: {} ({:.1f}s)", course_name, cost)
        tree_print(msg_done(f"完成课程: {course_name} ({cost:.1f}s)"), depth=1, enabled=tv)

    def play_video(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> None:
        """播放单个视频

        播放位置（learnTimeSec）与累计学习时长（studyTotalTime）是两条独立的量：
        服务端按累计判定完成（累计可以超过视频时长），位置只用于续播和 ev 里的
        HH:MM:SS。因此循环目标是累计秒，位置在 0..video_sec 之间循环使用。
        """
        video = ctx.videos[video_id]
        watch_state = video.watch_state

        # 已看完视频跳过（除非 end_threshold > 1.0 强制重看）
        if watch_state == 1 and self.end_threshold <= 1.0:
            self._print_with_progress(msg_skip(f"跳过(已完成): {video.name}"), depth=3, enabled=True)
            logger.debug(f"Skipping completed video: {video.name} (watchState=1)")
            return

        token_id, server_total = self._prelearning_note(rac_id, video_id, ctx)
        position = self._resume_time
        total_base = max(server_total, video.study_total_time)
        target = int(max(video.video_sec * self.end_threshold, 1.0))

        logger.debug(
            f"play_video: videoId={video_id}, name={video.name}, duration={video.video_sec}s, "
            f"position={position:.1f}s, total={total_base}s, target={target}s, "
            f"watchState={watch_state}, threshold={self.end_threshold}"
        )

        # 获取弹窗题目（按播放位置过滤已答部分）
        questions = self._load_questions(rac_id, video_id, ctx)
        questions = [q for q in questions if q.time_sec > position]
        questions.sort(key=lambda q: q.time_sec, reverse=True)

        logger.debug(
            "popup queue: videoId={} position={:.1f}s pending={} timeSec={}",
            video_id,
            position,
            len(questions),
            [q.time_sec for q in questions],
        )

        # 时间限制：-l 统计的是视频时长（不是墙钟），与本循环推进的累计秒同一口径
        if self._time_limit > 0:
            remaining = self._time_limit - ctx.fucked_time
            if remaining <= 0:
                logger.info(f"Time limit reached, skipping {video.name}")
                self._print_with_progress(msg_skip(f"跳过(时间限制): {video.name}"), depth=3, enabled=True)
                return
            affordable = total_base + int(remaining * (self._speed or 1.5))
            if affordable < target:
                target = max(affordable, total_base)
                logger.warning(
                    f"Time limit nearly exhausted for {video.name}: "
                    f"remaining={remaining:.0f}s (video), target={target}s"
                )
                self._print_with_progress(
                    msg_warn(f"时间不足: {video.name} (剩余{remaining:.0f}s)"),
                    depth=3,
                    enabled=True,
                )

        # 开播预检：立即上报一次零进度心跳（与服务端风控评估的常规心跳同格式），
        # 提前发现验证码(-12)/时长上限(-9)，避免进入观看循环后白等首个心跳(~30s)才发现
        total_base = self._precheck(rac_id, video_id, ctx, position, token_id, total=total_base)

        # 累计已达标（位置可能停在半途）：预检已经发过一条心跳，不再空转
        if total_base >= target:
            logger.info(
                f"Skip playback: total {total_base}s already reaches target {target}s "
                f"(position={position:.0f}s, watchState={watch_state})"
            )
            self._print_with_progress(msg_skip(f"跳过(累计已达标): {video.name}"), depth=3, enabled=True)
            return

        # 启动视频流请求（反检测）
        self._start_watch_thread(video.video_id)

        # 三维课件请求
        self._three_dimensional_course_ware(video.video_id)

        # 进入主循环
        self._main_loop(rac_id, video_id, ctx, position, target, total_base, token_id, questions)

        logger.info(
            f"play_video done: videoId={video_id}, name={video.name}, target={target}s, total_base={total_base}s"
        )

        # 人类延迟
        time.sleep(random() + 1)

    def _main_loop(
        self,
        rac_id: str,
        video_id: int,
        ctx: "ZhidaoContext",
        position: float,
        target: int,
        total_base: int,
        token_id: str,
        questions: list["QuestionPoint"],
    ) -> None:
        """视频播放主循环

        position 是播放游标（在 0..video_sec 之间循环），target 是**累计学习秒数**的目标：
        服务端按累计判定完成，位置播到底后回到开头继续累累计（等价网页端重看）。
        本段秒一律按累计增量计算，所以位置回绕不会出现负数。
        """
        from zhs.zhidao.quiz import ZhidaoQuizzer

        video = ctx.videos[video_id]
        duration = video.video_sec
        base_speed = self._speed or 1.5
        speed = base_speed + uniform(-0.15, 0.15)
        watched = 0.0
        submitted_total = float(total_base)
        elapsed_time = 0
        db_next = _jitter(CLASSIC_DB_INTERVAL)
        cache_next = _jitter(CLASSIC_CACHE_INTERVAL)
        answer_delay: int | None = None
        current_question: PopupQuestion | None = None
        force_db = False
        pause = 0
        wp = WatchPoint()
        wp.reset(total_base)
        # 跟踪本循环内已打印的最大行宽，用于填充空格覆盖残留字符
        prev_len = len(self._progress_line) if self._progress_line else 0

        while total_base + int(watched) < target:
            time.sleep(1)
            elapsed_time += 1
            ctx.fucked_time += 1

            # 暂停与答题期间冻结：位置和累计都不前进，也不消耗 -l 配额（-l 按视频时长计）
            paused_now = pause > 0
            if pause:
                pause -= 1
            elif answer_delay is not None:
                pass
            elif random() < PAUSE_CHANCE:
                pause = PAUSE_SECONDS
                paused_now = True
                # 暂停开始时把未上报的增量落库，避免长时间悬空
                force_db = True
            else:
                position = _advance(position, speed, duration)
                watched += speed

            if elapsed_time % 30 == 0:
                logger.debug(
                    f"Main loop: elapsed={elapsed_time}, position={position:.1f}, "
                    f"total={total_base + int(watched)}, submitted={int(submitted_total)}, "
                    f"pause={pause}, questions={len(questions)}, answer_delay={answer_delay}"
                )

            # 观看轨迹点（按累计秒，每 2 秒）
            if not elapsed_time % 2:
                wp.add(total_base + int(watched))

            # 检查弹窗题目
            if questions and position >= questions[-1].time_sec:
                q_point = questions.pop()
                logger.debug(
                    "popup triggered: videoId={} timeSec={} position={:.1f}s questionIds={} pending={}",
                    video_id,
                    q_point.time_sec,
                    position,
                    q_point.question_ids,
                    len(questions),
                )
                try:
                    quizzer = ZhidaoQuizzer(self._session)
                    popup = quizzer.get_popup_exam(
                        rac_id,
                        video_id,
                        q_point.question_ids,
                        lesson_id=video.lesson_id,
                        lesson_video_id=video.id,
                    )
                    answer_delay = 2
                    force_db = True
                    current_question = popup
                    logger.debug(
                        "popup question loaded: questionId={} options={}",
                        popup.question_id,
                        len(popup.question_options),
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to get question detail: questionIds={} err={}",
                        q_point.question_ids,
                        exc,
                    )

            # 答题延迟
            if answer_delay is not None:
                if answer_delay == 0:
                    answer_delay = None
                    if current_question is not None:
                        quizzer = ZhidaoQuizzer(self._session)
                        answer = quizzer.answer_question(current_question)
                        course_id = ctx.course_id
                        recruit_id = ctx.course.recruit_id or 0
                        quizzer.save_answer(
                            rac_id,
                            video_id,
                            current_question.question_id,
                            answer,
                            lesson_id=video.lesson_id,
                            lesson_video_id=video.id,
                            recruit_id=recruit_id,
                            course_id=course_id,
                        )
                else:
                    answer_delay -= 1

            # 两种心跳各自计时，只有上报成功才推进共享增量链；
            # 达标那一拍交给 Database（结尾只发 Database，进度的落库才算完成）
            total = total_base + int(watched)
            due_db = elapsed_time >= db_next or force_db or total >= target
            if elapsed_time >= cache_next and not due_db:
                wp.add(total)
                if self._report_cache_progress(video_id, ctx, position, submitted_total, wp.get(), token_id, total):
                    submitted_total = float(total)
                    wp.reset(total)
                cache_next = elapsed_time + _jitter(CLASSIC_CACHE_INTERVAL)

            if due_db:
                force_db = False
                wp.add(total)
                confirmed, success = self._report_progress_v2(
                    rac_id, video_id, ctx, position, submitted_total, wp.get(), token_id, initial=False, total=total
                )
                if success:
                    # -8 返回的是服务端累计：抬高基数后继续，不能改动播放位置
                    if confirmed > total:
                        total_base += int(confirmed) - total
                    submitted_total = float(total)
                    wp.reset(total)
                    db_next = elapsed_time + _jitter(CLASSIC_DB_INTERVAL)
                    speed = base_speed + uniform(-0.15, 0.15)
                else:
                    logger.warning(
                        f"Progress report failed, retry in {DB_RETRY_DELAY}s "
                        f"(pending delta={total - int(submitted_total)}s)"
                    )
                    db_next = elapsed_time + DB_RETRY_DELAY

            # 进度条：按累计秒显示
            if answer_delay is not None:
                action = "answering"
            elif paused_now:
                action = "pause"
            else:
                action = f"playing {video.video_id}"
            bar_current, bar_total = (
                (PAUSE_SECONDS - pause, float(PAUSE_SECONDS)) if paused_now else (min(total, target), float(target))
            )
            bar_str = progress_bar(bar_current, bar_total)
            line = f"{action} {bar_str}"
            self._progress_line = line
            # 填充空格至已打印的最大行宽，避免变短时旧字符残留
            padded = line.ljust(prev_len)
            prev_len = len(padded)
            print(f"\r{padded}", end="", flush=True)

        # 收尾：把最后一段增量落库（失败的话留给下一次运行补）
        total = total_base + int(watched)
        if total > int(submitted_total):
            wp.add(total)
            self._report_progress_v2(
                rac_id, video_id, ctx, position, submitted_total, wp.get(), token_id, initial=False, total=total
            )

        # 显示最终进度（保留进度条在底部，不换行不清除）
        final_bar = progress_bar(min(total_base + int(watched), target), float(target))
        final_line = f"playing {video.video_id} {final_bar}"
        self._progress_line = final_line
        print(f"\r{final_line.ljust(prev_len)}", end="", flush=True)

    def _prelearning_note(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> tuple[str, int]:
        """获取学习令牌（base64 编码的 token_id）和服务器最新学习时间"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/prelearningNote"
        video = ctx.videos[video_id]
        data: dict[str, Any] = {
            "ccCourseId": ctx.course_id,
            "chapterId": video.chapter_id,
            "isApply": 1,
            "lessonId": video.lesson_id,
            "lessonVideoId": video.id,
            "recruitId": ctx.course.recruit_id or 0,
            "videoId": video.video_id,
        }
        result = self._session.zhidao_query(url, data)
        dto = result.get("data", {}).get("studiedLessonDto", {})
        # 续播位置取 learnTimeSec（播放位置），累计时长取 studyTotalTime，两者不能混用
        try:
            # learnTimeSec 是播放位置；用 float 兼容 "42.5" 这类返回值
            self._resume_time = float(min(max(int(float(dto.get("learnTimeSec") or 0)), 0), video.video_sec))
        except (TypeError, ValueError):
            logger.warning(f"Invalid learnTimeSec, restarting from 0: {dto.get('learnTimeSec')!r}")
            self._resume_time = 0.0
        token_id = dto.get("id", 0)
        server_time = dto.get("studyTotalTime", 0)
        return b64encode(str(token_id).encode()).decode(), server_time

    def _load_questions(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> list["QuestionPoint"]:
        """加载弹窗题目列表"""
        from zhs.zhidao.quiz import ZhidaoQuizzer

        video = ctx.videos[video_id]
        course_id = ctx.course_id
        recruit_id = ctx.course.recruit_id or 0
        quizzer = ZhidaoQuizzer(self._session)
        return quizzer.load_video_pointer_info(
            rac_id,
            video_id,
            lesson_id=video.lesson_id,
            lesson_video_id=video.id,
            recruit_id=recruit_id,
            course_id=course_id,
        )

    def _start_watch_thread(self, video_id: int) -> None:
        """在新线程中请求视频流（反检测）"""
        t = threading.Thread(target=self._watch_video, args=(video_id,), daemon=True)
        t.start()

    def _watch_video(self, video_id: int) -> None:
        """在新线程中请求视频流

        使用独立的 httpx.Client，复制必要的浏览器 headers。
        线程内捕获所有异常并记录日志，不向上传播。
        """
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(
                    f"{self._session.urls.newbase}/video/initVideo",
                    params={
                        "jsonpCallBack": "result",
                        "videoID": str(video_id),
                        "_": int(time.time() * 1000),
                    },
                    headers={
                        "Accept": "*/*",
                        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="149", "Google Chrome";v="149"',
                        "sec-ch-ua-mobile": "?0",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                            " AppleWebKit/537.36 (KHTML, like Gecko)"
                            " Chrome/149.0.0.0 Safari/537.36"
                        ),
                        "sec-ch-ua-platform": '"Windows"',
                        "Accept-Encoding": "gzip, deflate, br",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Referer": "https://studyh5.zhihuishu.com/",
                    },
                )
                match = re.match(r"^result\((.*)\)$", r.text)
                if not match:
                    logger.error(f"Invalid video response for {video_id}")
                    return
                resp_data = json.loads(match.group(1))
                video_url = resp_data.get("result", {}).get("lines", [{}])[0].get("lineUrl", "")
                if video_url:
                    client.get(video_url)
        except Exception as exc:
            logger.error(f"Failed to watch video {video_id}: {exc}")

    def _three_dimensional_course_ware(self, video_id: int) -> None:
        """三维课件请求"""
        url = f"{self._session.urls.study}/gateway/t/v1/course/threeDimensionalCourseWare"
        with contextlib.suppress(Exception):
            self._session.zhidao_query(url, {"videoId": video_id}, method="GET")

    def _report_cache_progress(
        self,
        video_id: int,
        ctx: "ZhidaoContext",
        position: float,
        submitted_total: float,
        watch_point: str,
        token_id: str,
        total: int,
    ) -> bool:
        """Cache 心跳：字段顺序与 Database 不同，返回是否成功以维护共享增量链

        `submitted_total` 是上次成功上报的累计秒，本段秒按累计增量计算。
        """
        video = ctx.videos[video_id]
        course_info = ctx.course.course_info
        raw_ev: list[int | str] = [
            ctx.course.recruit_id or 0,
            video.chapter_id,
            course_info.course_id if course_info else 0,
            video.lesson_id,
            _hms(min(video.video_sec, int(position))),
            total,
            video.video_id,
            video.id,
            max(total - int(submitted_total), 0),
            (self._session.uuid or "") + "zhs",
        ]
        sdsew = encode_ev(raw_ev, self._session.crypto.ev_key)
        url = f"{self._session.urls.study}/gateway/t/v1/learning/saveCacheIntervalTimeV2"
        data: dict[str, Any] = {
            "ewssw": watch_point,
            "sdsew": sdsew,
            "zwsds": token_id,
        }
        try:
            self._session.zhidao_query(url, data)
        except CaptchaRequired:
            raise
        except ApiError as exc:
            if exc.code == -9:
                raise TimeLimitExceeded(f"学习时长已达上限: {exc.message}") from exc
            logger.warning(f"Cache progress report failed: {exc}")
            return False
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(f"Cache progress report failed: {exc}")
            return False
        return True

    def _precheck(
        self,
        rac_id: str,
        video_id: int,
        ctx: "ZhidaoContext",
        played_time: float,
        token_id: str,
        total: int | None = None,
    ) -> int:
        """开播前预检上报：delta=0 的常规心跳格式，返回已确认累计时长

        实测：服务端风控仅在常规心跳（initial=False）上评估，
        initial=True 补报不返回 -12/-9，故用 last_submit=played_time 的
        零进度心跳预检，不虚报进度。

        Raises:
            CaptchaRequired: 服务端要求验证码（code -12）
            TimeLimitExceeded: 学习时长已达上限（code -9）
        """
        total_seconds = int(played_time) if total is None else int(total)
        watch_point = WatchPoint()
        watch_point.reset(total_seconds)
        watch_point.add(total_seconds)
        confirmed_total, success = self._report_progress_v2(
            rac_id,
            video_id,
            ctx,
            played_time,
            float(total_seconds),
            watch_point.get(),
            token_id,
            initial=False,
            total=total_seconds,
        )
        return int(confirmed_total) if success else total_seconds

    def _report_progress_v2(
        self,
        rac_id: str,
        video_id: int,
        ctx: "ZhidaoContext",
        position: float,
        submitted_total: float,
        watch_point: str,
        token_id: str,
        initial: bool = False,
        total: int | None = None,
    ) -> tuple[float, bool]:
        """上报进度 V2，返回 (累计学习时长, 是否上报成功)

        `position` 只用于 ev 里的 HH:MM:SS，`submitted_total` 是上次成功上报的累计秒，
        本段秒按累计增量计算（位置回绕到开头时不会出现负数）。
        """
        total_seconds = int(position) if total is None else total
        url = f"{self._session.urls.study}/gateway/t/v1/learning/saveDatabaseIntervalTimeV2"
        video = ctx.videos[video_id]
        recruit_id = ctx.course.recruit_id or 0
        # courseId 必须使用 courseInfo.courseId（来自 queryCourse API），
        # 而非 videoList 返回的 courseId，否则服务端会返回 -1 参数解码错误
        course_info = ctx.course.course_info
        course_id = course_info.course_id if course_info else 0
        session_uuid = self._session.uuid or ""

        logger.debug(
            f"Report progress: videoId={video_id}, position={position:.1f}, "
            f"submitted={submitted_total:.1f}, delta={max(total_seconds - int(submitted_total), 0)}"
        )

        if initial:
            raw_ev: list[int | str] = [
                recruit_id,
                video.chapter_id,
                course_id,
                video.lesson_id,
                _hms(min(video.video_sec, int(position))),
                int(position),
                video.video_id,
                "0",
                int(position),
                session_uuid,
            ]
        else:
            raw_ev = [
                recruit_id,
                video.lesson_id,
                video.id,
                video.video_id,
                video.chapter_id,
                "0",
                max(total_seconds - int(submitted_total), 0),
                total_seconds,
                _hms(min(video.video_sec, int(position))),
                session_uuid + "zhs",
            ]

        sdsew = encode_ev(raw_ev, self._session.crypto.ev_key)

        data: dict[str, Any] = {
            "ewssw": watch_point,
            "sdsew": sdsew,
            "zwsds": token_id,
        }
        if not initial:
            data["courseId"] = course_id

        try:
            self._session.zhidao_query(url, data)
            return float(total_seconds), True
        except CaptchaRequired:
            raise
        except Exception as exc:
            if isinstance(exc, ApiError) and exc.code == -9:
                # 学习时长已达上限（当日封顶）：观看不再计进度，终止课程
                # （网页端对应提示"学习时间已经结束, 观看视频将不再计进度"）
                raise TimeLimitExceeded(f"学习时间已达上限: {exc.message}") from exc
            exc_msg = str(exc)
            if "-10" in exc_msg:
                # 疑是多窗口观看：刷新 token 重试一次
                logger.warning(f"Multi-window detected, refreshing token: {exc}")
                time.sleep(3)
                try:
                    new_token, _ = self._prelearning_note(rac_id, video_id, ctx)
                    data["zwsds"] = new_token
                    self._session.zhidao_query(url, data)
                    logger.info("Progress report succeeded after token refresh")
                    return float(total_seconds), True
                except Exception as retry_exc:
                    logger.error(f"Progress report failed after retry: {retry_exc}")
            elif "-8" in exc_msg:
                # 学习总时长下降了：服务器记录的时间比我们上报的高
                # 获取服务器最新时间，用最新时间重新上报
                logger.warning(f"Study time decreased, syncing with server: {exc}")
                try:
                    new_token, server_time = self._prelearning_note(rac_id, video_id, ctx)
                    if server_time > total_seconds and not initial:
                        # 只同步累计字段，保持本段增量和播放位置不变。
                        raw_ev[7] = server_time
                        data["sdsew"] = encode_ev(raw_ev, self._session.crypto.ev_key)
                        data["zwsds"] = new_token
                        self._session.zhidao_query(url, data)
                        logger.info(f"Progress report succeeded after -8 sync (server={server_time}s)")
                        return float(server_time), True
                except Exception as retry_exc:
                    logger.error(f"Progress report failed after -8 retry: {retry_exc}")
            else:
                logger.error(f"Failed to report progress: {exc}")
        return float(total_seconds), False

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
from datetime import timedelta
from random import random
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from zhs.crypto import WatchPoint, encode_ev
from zhs.exceptions import CaptchaRequired
from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, progress_bar, tree_print, wipe_line

if TYPE_CHECKING:
    from zhs.session import ZhsSession
    from zhs.zhidao.models import PopupQuestion, QuestionPoint, ZhidaoContext


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

    def play_course(self, rac_id: str, ctx: "ZhidaoContext") -> None:
        """播放整个课程，遍历所有章节/课时/子视频

        单个视频失败不中断整个课程，记录错误后继续下一个视频。
        """
        from zhs.exceptions import CaptchaRequired

        course = ctx.course
        course_name = course.course_info.name if course.course_info else course.course_name
        begin_time = time.time()
        tv = True
        logger.info(f"play_course: {course_name}, chapters={len(ctx.chapters)}")
        tree_print(f"{course_tag('zhidao')} 课程: {course_name}", enabled=tv)

        for chapter in ctx.chapters:
            tree_print(f"章节: {chapter.name}", depth=1, enabled=tv)
            for lesson in chapter.video_lessons:
                tree_print(f"课时: {lesson.name}", depth=2, enabled=tv)
                for video in lesson.video_small_lessons:
                    try:
                        self.play_video(rac_id, video.video_id, ctx)
                    except CaptchaRequired:
                        tree_print(msg_warn("!! 需要验证码，停止课程"), depth=3, enabled=tv)
                        return
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        tree_print(msg_error(f"!! 视频失败: {video.name} - {exc}"), depth=3, enabled=tv)
                        continue

        cost = time.time() - begin_time
        tree_print(msg_done(f"完成课程: {course_name} ({cost:.1f}s)"), depth=1, enabled=tv)

    def play_video(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> None:
        """播放单个视频"""
        video = ctx.videos[video_id]
        played_time = float(video.study_total_time)
        watch_state = video.watch_state

        logger.debug(
            f"play_video: videoId={video_id}, name={video.name}, "
            f"duration={video.video_sec}s, played={played_time}s, "
            f"watchState={watch_state}, threshold={self.end_threshold}"
        )

        # 已看完视频跳过（除非 end_threshold > 1.0 强制重看）
        if watch_state == 1 and self.end_threshold <= 1.0:
            tree_print(msg_skip(f"跳过(已完成): {video.name}"), depth=3, enabled=True)
            logger.debug(f"Skipping completed video: {video.name} (watchState=1)")
            return

        # 获取学习令牌（同时获取最新的学习时间）
        token_id, server_time = self._prelearning_note(rac_id, video_id, ctx)
        # 使用服务器返回的最新学习时间，避免 -8 学习总时长下降
        if server_time > played_time:
            logger.info(f"Server time {server_time}s > local {played_time}s, using server time")
            played_time = float(server_time)

        # 获取弹窗题目
        questions = self._load_questions(rac_id, video_id, ctx)
        # 过滤已答题目
        questions = [q for q in questions if q.time_sec > played_time]
        questions.sort(key=lambda q: q.time_sec, reverse=True)

        # 计算结束时间
        end_time = max(video.video_sec * self.end_threshold, 1.0)
        if questions:
            end_time = max(questions[-1].time_sec, end_time)

        # 时间限制检查
        real_end_time = end_time  # 保存真实结束时间，用于进度条显示
        if self._time_limit > 0:
            speed = self._speed or 1.5
            remaining = self._time_limit - ctx.fucked_time
            if remaining <= 0:
                logger.info(f"Time limit reached, skipping {video.name}")
                tree_print(msg_skip(f"跳过(时间限制): {video.name}"), depth=3, enabled=True)
                return
            # remaining 是真实秒数，视频以 speed 倍速前进，所以视频可前进 remaining * speed 秒
            end_time = min(end_time, played_time + remaining * speed)
            if end_time - played_time < 10:
                logger.warning(
                    f"Time limit nearly exhausted for {video.name}: "
                    f"remaining={remaining:.0f}s (real), video_advance={remaining * speed:.0f}s, "
                    f"played={played_time:.1f}s, end={end_time:.1f}s"
                )
                tree_print(msg_warn(f"时间不足: {video.name} (剩余{remaining:.0f}s)"), depth=3, enabled=True)

        # 启动视频流请求（反检测）
        self._start_watch_thread(video.video_id)

        # 三维课件请求
        self._three_dimensional_course_ware(video.video_id)

        # 进入主循环
        self._main_loop(rac_id, video_id, ctx, played_time, end_time, real_end_time, token_id, questions)

        logger.info(
            f"play_video done: videoId={video_id}, name={video.name}, "
            f"end_time={end_time:.1f}s, played_time={played_time:.1f}s"
        )

        # 人类延迟
        time.sleep(random() + 1)

    def _main_loop(
        self,
        rac_id: str,
        video_id: int,
        ctx: "ZhidaoContext",
        played_time: float,
        end_time: float,
        real_end_time: float,
        token_id: str,
        questions: list["QuestionPoint"],
    ) -> None:
        """视频播放主循环"""
        from zhs.zhidao.quiz import ZhidaoQuizzer

        video = ctx.videos[video_id]
        speed = self._speed or 1.5
        last_submit = played_time
        elapsed_time = 0
        db_interval = 30
        answer_delay: int | None = None
        current_question: PopupQuestion | None = None
        report = False
        pause = 0
        wp = WatchPoint()

        while played_time < end_time:
            time.sleep(1)
            ctx.fucked_time += 1
            elapsed_time += 1
            played_time = min(played_time + speed, end_time)

            if elapsed_time % 30 == 0:
                logger.debug(
                    f"Main loop: elapsed={elapsed_time}, "
                    f"played_time={played_time:.1f}, last_submit={last_submit:.1f}, "
                    f"pause={pause}, questions={len(questions)}, "
                    f"answer_delay={answer_delay}"
                )

            # 随机暂停 0.25%
            pause = pause or int(random() < 0.0025) * 60
            report = report or pause == 60

            # 暂停期间不前进
            if pause:
                pause -= 1
                played_time = last_submit

            # 更新 WatchPoint（每 2 秒）
            if not elapsed_time % 2:
                wp.add(int(played_time))

            # 检查弹窗题目
            if questions and played_time >= questions[-1].time_sec:
                q_point = questions.pop()
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
                    report = True
                    current_question = popup
                except Exception as exc:
                    logger.error(f"Failed to get question detail: {exc}")

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
                    pause = pause or 1
                    answer_delay -= 1

            # 上报进度
            if elapsed_time % db_interval == 0 or played_time >= end_time or report:
                report = False
                wp.add(int(played_time))
                server_played = self._report_progress_v2(
                    rac_id, video_id, ctx, played_time, last_submit, wp.get(), token_id, initial=False
                )
                # 同步服务器时间（处理 -8 学习总时长下降）
                if server_played > played_time:
                    played_time = server_played
                last_submit = played_time
                wp.reset(int(played_time))

            # 显示进度条（始终相对于真实结束时间，不受时间限制影响）
            bar_current, bar_total = (60 - pause, 60) if pause else (int(played_time), int(real_end_time))
            action = "pause" if pause else f"playing {video.video_id}" if answer_delay is None else "answering"
            bar_str = progress_bar(bar_current, bar_total)
            print(f"\r{action} {bar_str}", end="", flush=True)

        wipe_line()

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
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                            " AppleWebKit/537.36 (KHTML, like Gecko)"
                            " Chrome/101.0.4951.64 Safari/537.36"
                        ),
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

    def _report_progress_v2(
        self,
        rac_id: str,
        video_id: int,
        ctx: "ZhidaoContext",
        played_time: float,
        last_submit: float,
        watch_point: str,
        token_id: str,
        initial: bool = False,
    ) -> float:
        """上报进度 V2，返回服务器最新学习时间（用于同步 played_time）"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/saveDatabaseIntervalTimeV2"
        video = ctx.videos[video_id]
        recruit_id = ctx.course.recruit_id or 0
        # courseId 必须使用 courseInfo.courseId（来自 queryCourse API），
        # 而非 videoList 返回的 courseId，否则服务端会返回 -1 参数解码错误
        course_info = ctx.course.course_info
        course_id = course_info.course_id if course_info else 0
        session_uuid = self._session.uuid or ""

        logger.debug(
            f"Report progress: videoId={video_id}, "
            f"played_time={played_time:.1f}, last_submit={last_submit:.1f}, "
            f"delta={played_time - last_submit:.1f}"
        )

        if initial:
            raw_ev: list[int | str] = [
                recruit_id,
                video.chapter_id,
                course_id,
                video.lesson_id,
                str(timedelta(seconds=min(video.video_sec, int(played_time)))),
                int(played_time),
                video.video_id,
                "0",
                int(played_time),
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
                int(played_time - last_submit),
                int(played_time),
                str(timedelta(seconds=min(video.video_sec, int(played_time)))),
                session_uuid + "zhs",
            ]

        data: dict[str, Any] = {
            "ewssw": watch_point,
            "sdsew": encode_ev(raw_ev, self._session.crypto.ev_key),
            "zwsds": token_id,
        }
        if not initial:
            data["courseId"] = course_id

        try:
            self._session.zhidao_query(url, data)
        except CaptchaRequired:
            raise
        except Exception as exc:
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
                except Exception as retry_exc:
                    logger.error(f"Progress report failed after retry: {retry_exc}")
            elif "-8" in exc_msg:
                # 学习总时长下降了：服务器记录的时间比我们上报的高
                # 获取服务器最新时间，用最新时间重新上报
                logger.warning(f"Study time decreased, syncing with server: {exc}")
                try:
                    new_token, server_time = self._prelearning_note(rac_id, video_id, ctx)
                    if server_time > int(played_time):
                        # 用服务器时间重新构造 ev
                        new_played = float(server_time)
                        new_delta = new_played - last_submit
                        if new_delta < 0:
                            new_delta = 0
                        raw_ev[6] = int(new_delta)
                        raw_ev[7] = int(new_played)
                        raw_ev[8] = str(timedelta(seconds=min(video.video_sec, int(new_played))))
                        data["sdsew"] = encode_ev(raw_ev, self._session.crypto.ev_key)
                        data["zwsds"] = new_token
                        self._session.zhidao_query(url, data)
                        logger.info(f"Progress report succeeded after -8 sync (server={server_time}s)")
                        return float(server_time)
                except Exception as retry_exc:
                    logger.error(f"Progress report failed after -8 retry: {retry_exc}")
            else:
                logger.error(f"Failed to report progress: {exc}")
        return played_time

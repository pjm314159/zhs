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
from collections.abc import Callable
from random import randint, random
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from zhs.crypto import WatchPoint, encode_ev
from zhs.exceptions import ApiError, CaptchaRequired, TimeLimitExceeded
from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, progress_bar, tree_print, wipe_line

if TYPE_CHECKING:
    from zhs.session import ZhsSession
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.models import MapLesson, MapResource, PopupQuestion, QuestionPoint, ZhidaoContext


MAP_HEARTBEAT_INTERVAL = 30

# 旧版 videolist 课的心跳节奏：按网页端 ableVideoPlayer6.0 抓包取值（docs/capture-findings.md）
# saveDatabaseIntervalTimeV2 约每 300 秒一次，saveCacheIntervalTimeV2 约每 180 秒一次，触发时机各自计时；
# 但两者共用一条增量链：本段秒 = 距上一次任意上报的位置差，服务端把两种上报的本段秒都累加进 studyTotalTime
CLASSIC_DB_INTERVAL = 300
CLASSIC_CACHE_INTERVAL = 180
# 每次心跳间隔加一点抖动，避免严格等距
CLASSIC_INTERVAL_JITTER = 5
# 未配置倍速时与网页默认一致：1.0 倍，上报的学习秒数等于真实经过的秒数
DEFAULT_ZHIDAO_SPEED = 1.0

# 知识图谱课：多端/多窗口观看（账号级状态，继续播只会全部失败）
MAP_MULTI_WINDOW_CODE = 2021


class StudyRecordError(ApiError):
    """preLearningLoad 未建立学习记录（后续视频同样会失败，应停课）"""


def _course_stop_reason(exc: Exception) -> str | None:
    """导致整门课应停止的异常 → 提示文案；普通单视频失败返回 None"""
    if isinstance(exc, CaptchaRequired):
        return "需要验证码"
    if isinstance(exc, TimeLimitExceeded):
        return "学习时间已达上限"
    return None


def _map_stop_reason(exc: Exception) -> str | None:
    """知识图谱课额外的停课条件"""
    if isinstance(exc, StudyRecordError):
        return "学习记录建立失败（可稍后重试）"
    if isinstance(exc, ApiError) and exc.code == MAP_MULTI_WINDOW_CODE:
        return "检测到多端/多窗口观看（请关闭浏览器播放页或其他设备后重试）"
    return _course_stop_reason(exc)


def _parse_learn_time(value: str) -> int:
    """学习时长字符串（HH:MM:SS / MM:SS）→ 秒数"""
    parts = [p for p in str(value).split(":") if p != ""]
    try:
        numbers = [int(p) for p in parts]
    except (TypeError, ValueError):
        return 0
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] if numbers else 0


def _hms(seconds: int) -> str:
    """秒 → HH:MM:SS（小时补零，与网页端 ev 一致；timedelta 的 str 是 0:03:00）"""
    hours, rest = divmod(max(int(seconds), 0), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _jittered(interval: int) -> int:
    """心跳间隔加 ±CLASSIC_INTERVAL_JITTER 秒抖动"""
    return interval + randint(-CLASSIC_INTERVAL_JITTER, CLASSIC_INTERVAL_JITTER)


def _course_name(ctx: "ZhidaoContext") -> str:
    """课程显示名（优先 courseInfo.name）"""
    course = ctx.course
    return course.course_info.name if course.course_info else course.course_name


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
        self._progress_width = 0
        self._last_note: dict[str, Any] | None = None

    def _print_with_progress(self, text: str, depth: int = 0, enabled: bool = True) -> None:
        """打印消息，保持进度条在底部（若激活则清除→打印→重印进度条）"""
        if not enabled:
            return
        indent = "  " * depth
        if self._progress_line is not None:
            wipe_line()
            print(f"{indent}{text}")
            print(f"\r{self._progress_line.ljust(self._progress_width)}", end="", flush=True)
        else:
            print(f"{indent}{text}")

    def _update_progress_line(self, text: str) -> None:
        """原地刷新进度行（\\r 覆盖，不换行）"""
        padded = text.ljust(self._progress_width)
        self._progress_line = text
        self._progress_width = len(padded)
        print(f"\r{padded}", end="", flush=True)

    def _clear_progress(self) -> None:
        """清除进度条（若激活）"""
        if self._progress_line is not None:
            wipe_line()
            self._progress_line = None
            self._progress_width = 0

    def play_course(self, rac_id: str, ctx: "ZhidaoContext") -> None:
        """播放整个课程，遍历所有章节/课时/子视频

        单个视频失败不中断整个课程，记录错误后继续下一个视频。
        """
        # 新版共享课（知识图谱）走独立的数据源，停课/失败语义与旧流程一致
        if ctx.mode == "map":
            self._play_map_course(ctx)
            return

        course_name = _course_name(ctx)
        begin_time = time.time()
        failed = 0
        logger.info(f"play_course: {course_name}, chapters={len(ctx.chapters)}")
        self._print_with_progress(f"{course_tag('zhidao')} 新课程: {course_name}")

        for ch_idx, chapter in enumerate(ctx.chapters, 1):
            self._print_with_progress(f"章节 {ch_idx}: {chapter.name}", depth=1)
            for ls_idx, lesson in enumerate(chapter.video_lessons, 1):
                self._print_with_progress(f"课时 {ch_idx}.{ls_idx}: {lesson.name}", depth=2)
                for video in lesson.video_small_lessons:
                    try:
                        self.play_video(rac_id, video.video_id, ctx)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        if self._handle_unit_error(exc, course_name, video.name, _course_stop_reason):
                            return
                        failed += 1

        self._finish_course(course_name, begin_time, failed, has_videos=bool(ctx.videos))

    def _handle_unit_error(
        self,
        exc: Exception,
        course_name: str,
        unit_name: str,
        stop_reason: Callable[[Exception], str | None],
    ) -> bool:
        """统一处理单个视频的异常：返回 True 表示应停止整门课程"""
        self._clear_progress()
        reason = stop_reason(exc)
        if reason is not None:
            logger.warning(f"Course stopped: {reason} ({course_name}, {unit_name}) - {exc}")
            tree_print(msg_warn(f"!! {reason}，停止课程"), depth=3)
            return True
        logger.error(f"Video failed: {unit_name} ({course_name}) - {exc}")
        tree_print(msg_error(f"!! 视频失败: {unit_name} - {exc}"), depth=3)
        return False

    def _finish_course(self, course_name: str, begin_time: float, failed: int, *, has_videos: bool) -> None:
        """课程结束汇总：没有可播视频 / 有失败时不打印“完成课程”"""
        cost = time.time() - begin_time
        self._clear_progress()
        if not has_videos:
            logger.warning(f"play_course: no playable video found ({course_name})")
            tree_print(msg_warn(f"!! 未找到可播放的视频: {course_name}"), depth=1)
            return
        if failed:
            logger.warning(f"play_course finished with {failed} failed video(s): {course_name} ({cost:.1f}s)")
            tree_print(msg_warn(f"课程结束但有 {failed} 个视频失败: {course_name} ({cost:.1f}s)"), depth=1)
            return
        logger.info(f"play_course done: {course_name} ({cost:.1f}s)")
        tree_print(msg_done(f"完成课程: {course_name} ({cost:.1f}s)"), depth=1)

    def _play_map_course(self, ctx: "ZhidaoContext") -> None:
        """新版共享课（知识图谱）播放流程

        章节树来自 aistudy，视频资源来自 share-course-map，
        进度上报走 saveUserStudyProcess（明文 JSON）。
        是否跳过以 queryUserStudyInfo 的 state 为准（进度按「节点 + dataId」独立记录）。
        """
        from zhs.zhidao.course import ZhidaoCourseManager

        course_name = _course_name(ctx)
        begin_time = time.time()
        mgr = ZhidaoCourseManager(self._session)
        recruit_id = ctx.course.recruit_id or 0
        failed = 0
        has_videos = False

        logger.info(f"play_map_course: {course_name}, chapters={len(ctx.map_chapters)}")
        self._print_with_progress(f"{course_tag('zhidao')} 新课程(知识图谱): {course_name}")

        for ch_idx, chapter in enumerate(ctx.map_chapters, 1):
            done = sum(leaf.finish_num or 0 for leaf in chapter.leaf_nodes())
            total = sum(leaf.source_num or 0 for leaf in chapter.leaf_nodes())
            self._print_with_progress(f"章节 {ch_idx}: {chapter.name} ({done}/{total})", depth=1)
            for ls_idx, lesson in enumerate(chapter.leaf_nodes(), 1):
                if self._stop_on_time_limit(ctx, course_name):
                    return
                done_node = lesson.finish_num or 0
                total_node = lesson.source_num or 0
                self._print_with_progress(f"课时 {ch_idx}.{ls_idx}: {lesson.name} ({done_node}/{total_node})", depth=2)

                try:
                    resources = mgr.query_node_resources(lesson)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    if self._handle_unit_error(exc, course_name, lesson.name, _map_stop_reason):
                        return
                    failed += 1
                    continue

                videos = [r for r in resources if r.is_video and not r.is_elective]
                materials = [r for r in resources if r.is_courseware and not r.is_elective]
                elective = [r for r in resources if r.is_elective]
                has_videos = has_videos or bool(videos or materials)
                for resource in elective:
                    self._print_with_progress(msg_skip(f"跳过(选学，不计入进度): {resource.name}"), depth=3)

                for resource in materials:
                    # 课件一次上报就完成，不占今天的学习时长，不因为视频时间上限停掉
                    try:
                        self.complete_map_material(mgr, ctx, lesson, resource)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        if self._handle_unit_error(exc, course_name, resource.name, _map_stop_reason):
                            return
                        failed += 1

                for resource in videos:
                    if self._stop_on_time_limit(ctx, course_name):
                        return
                    try:
                        study = mgr.query_user_study_info(
                            course_id=ctx.course_id,
                            recruit_id=recruit_id,
                            lesson_hash=lesson.id_hash,
                            data_id=resource.file_id,
                        )
                        if study.get("state") == 2:
                            self._print_with_progress(msg_skip(f"跳过(已完成): {resource.name}"), depth=3)
                            continue
                        resume = _parse_learn_time(study.get("learnTime") or "")
                        self.play_map_video(mgr, ctx, lesson, resource, resume)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        if self._handle_unit_error(exc, course_name, resource.name, _map_stop_reason):
                            return
                        failed += 1

        self._finish_course(course_name, begin_time, failed, has_videos=has_videos)

    def _time_limit_reached(self, ctx: "ZhidaoContext") -> bool:
        """课程时间限制是否已到"""
        return self._time_limit > 0 and ctx.fucked_time >= self._time_limit

    def _stop_on_time_limit(self, ctx: "ZhidaoContext", course_name: str) -> bool:
        """时间限制已到时打印提示并返回 True"""
        if not self._time_limit_reached(ctx):
            return False
        self._clear_progress()
        logger.info(f"Time limit reached, stop course: {course_name}")
        tree_print(msg_skip(f"时间限制已到，停止课程: {course_name}"), depth=1)
        return True

    def play_map_video(
        self,
        manager: "ZhidaoCourseManager",
        ctx: "ZhidaoContext",
        lesson: "MapLesson",
        resource: "MapResource",
        resume_seconds: int = 0,
    ) -> bool:
        """播放知识图谱视频：按心跳上报学习时长

        Args:
            manager: 课程管理器（提供 pre_learning_load / save_study_process）
            ctx: 课程上下文
            lesson: 叶子节点
            resource: 视频资源
            resume_seconds: 续播起点（秒）

        Returns:
            是否真正播放并上报了进度（跳过返回 False）

        Raises:
            StudyRecordError: preLearningLoad 未建立学习记录
            ApiError: 进度上报失败（含 2021 多端观看）
        """
        duration = resource.duration
        target = min(duration, max(duration * self.end_threshold, 1.0))
        speed = self._speed or DEFAULT_ZHIDAO_SPEED
        learn = min(float(resume_seconds), target)
        recruit_id = ctx.course.recruit_id or 0

        logger.debug(
            f"play_map_video: {resource.name}, duration={duration}s, "
            f"resume={resume_seconds}s, target={target:.1f}s, speed={speed}"
        )

        if learn >= target:
            self._print_with_progress(msg_skip(f"跳过(已完成): {resource.name}"), depth=3)
            return False

        if self._time_limit_reached(ctx):
            return False

        # 必须先建立学习记录，否则 saveUserStudyProcess 返回 NPE / 2021 多端观看异常
        if not manager.pre_learning_load(
            course_id=ctx.course_id,
            recruit_id=recruit_id,
            chapter_hash=lesson.chapter_hash,
            lesson_hash=lesson.id_hash,
            data_id=resource.file_id,
        ):
            raise StudyRecordError(-1, "preLearningLoad 未返回成功，学习记录未建立")

        self._print_with_progress(f"视频: {resource.name} ({duration}s)", depth=3)
        while learn < target:
            if self._time_limit_reached(ctx):
                logger.info(f"Time limit reached, skipping {resource.name}")
                self._print_with_progress(msg_skip(f"跳过(时间限制): {resource.name}"), depth=3)
                return False

            # playTimes 是服务端累计学习时长的唯一依据：传多少秒，本次就加多少秒
            delta = max(1, min(int(MAP_HEARTBEAT_INTERVAL * speed), int(target - learn)))
            time.sleep(MAP_HEARTBEAT_INTERVAL)
            ctx.fucked_time += MAP_HEARTBEAT_INTERVAL

            data = manager.save_study_process(
                recruit_id=recruit_id,
                chapter_hash=lesson.chapter_hash,
                lesson_hash=lesson.id_hash,
                data_id=resource.file_id,
                play_times=delta,
                total_time=duration,
                learn_time=min(int(learn) + delta, duration),
            )
            if data.get("submitSuccess") is False:
                raise ApiError(-1, f"学习进度上报失败: {data}")

            previous = learn
            server_learn = data.get("learnTime")
            if isinstance(server_learn, int):
                learn = max(learn, float(server_learn))
            # 服务端未推进（异常情况）时本地兜底，避免死循环
            if learn <= previous:
                learn = min(previous + delta, target)

            bar = progress_bar(min(learn, target), target)
            self._update_progress_line(f"{'  ' * 4}playing {resource.file_id} {bar}")

        logger.info(f"play_map_video done: {resource.name}, learn={learn:.0f}s/{duration}s")
        time.sleep(random() + 1)
        return True

    def complete_map_material(
        self,
        manager: "ZhidaoCourseManager",
        ctx: "ZhidaoContext",
        lesson: "MapLesson",
        resource: "MapResource",
    ) -> bool:
        """标记图谱课 PPT/课件完成

        网页实测：先 preLearningLoad，再按 dataType=2 上报一次
        （playTimes=0，时长传空串），服务端直接返回 state=2。
        不需要打开课件内容，也不占今天的学习时长。

        Returns:
            是否本次新标记完成（已完成返回 False）
        """
        recruit_id = ctx.course.recruit_id or 0
        lesson_id = lesson.parent_hash or lesson.id_hash
        lesson_video_id = resource.node_uid_hash or lesson.id_hash
        study = manager.query_user_study_info(
            course_id=ctx.course_id,
            recruit_id=recruit_id,
            lesson_hash=lesson_id,
            data_id=resource.file_id,
            lesson_video_id=lesson_video_id,
        )
        if study.get("state") == 2:
            self._print_with_progress(msg_skip(f"跳过(已完成): {resource.name}"), depth=3)
            return False

        if not manager.pre_learning_load(
            course_id=ctx.course_id,
            recruit_id=recruit_id,
            chapter_hash=lesson.chapter_hash,
            lesson_hash=lesson_id,
            data_id=resource.file_id,
            lesson_video_id=lesson_video_id,
        ):
            raise StudyRecordError(-1, "preLearningLoad 未返回成功，学习记录未建立")

        data = manager.save_study_process(
            recruit_id=recruit_id,
            chapter_hash=lesson.chapter_hash,
            lesson_hash=lesson_id,
            data_id=resource.file_id,
            play_times=0,
            total_time=0,
            learn_time=0,
            data_type=2,
            lesson_video_id=lesson_video_id,
        )
        if data.get("submitSuccess") is False or data.get("state") != 2:
            raise ApiError(-1, f"课件完成上报失败: {data}")

        self._print_with_progress(msg_done(f"课件完成: {resource.name}"), depth=3)
        logger.info(f"complete_map_material: {resource.name} state={data.get('state')}")
        return True

    def play_video(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> None:
        """播放单个视频"""
        video = ctx.videos[video_id]
        watch_state = video.watch_state

        logger.debug(
            f"play_video: videoId={video_id}, name={video.name}, "
            f"duration={video.video_sec}s, studied={video.study_total_time}s, "
            f"watchState={watch_state}, threshold={self.end_threshold}"
        )

        # 已看完视频跳过（除非 end_threshold > 1.0 强制重看）
        if watch_state == 1 and self.end_threshold <= 1.0:
            self._print_with_progress(msg_skip(f"跳过(已完成): {video.name}"), depth=3, enabled=True)
            logger.debug(f"Skipping completed video: {video.name} (watchState=1)")
            return

        # 获取学习令牌；网页端从 learnTimeSec（上次播放位置）续播，
        # ev 里的「累计秒」是 studyTotalTime 往上加（抓包：位置 00:03:00 时累计 863）
        token_id, studied_total = self._prelearning_note(rac_id, video_id, ctx)
        played_time = self._resume_position(video.video_sec)
        total_base = max(int(studied_total), int(video.study_total_time))

        # 获取弹窗题目
        questions = self._load_questions(rac_id, video_id, ctx)
        # 过滤已答题目
        questions = [q for q in questions if q.time_sec > played_time]
        questions.sort(key=lambda q: q.time_sec, reverse=True)

        logger.debug(
            "popup queue: videoId={} played={:.1f}s pending={} timeSec={}",
            video_id,
            played_time,
            len(questions),
            [q.time_sec for q in questions],
        )

        # 计算结束时间
        end_time = max(video.video_sec * self.end_threshold, 1.0)
        if questions:
            end_time = max(questions[-1].time_sec, end_time)

        # 时间限制检查
        real_end_time = end_time  # 保存真实结束时间，用于进度条显示
        if self._time_limit > 0:
            speed = self._speed or DEFAULT_ZHIDAO_SPEED
            remaining = self._time_limit - ctx.fucked_time
            if remaining <= 0:
                logger.info(f"Time limit reached, skipping {video.name}")
                self._print_with_progress(msg_skip(f"跳过(时间限制): {video.name}"), depth=3, enabled=True)
                return
            # remaining 是真实秒数，视频以 speed 倍速前进，所以视频可前进 remaining * speed 秒
            end_time = min(end_time, played_time + remaining * speed)
            if end_time - played_time < 10:
                logger.warning(
                    f"Time limit nearly exhausted for {video.name}: "
                    f"remaining={remaining:.0f}s (real), video_advance={remaining * speed:.0f}s, "
                    f"played={played_time:.1f}s, end={end_time:.1f}s"
                )
                self._print_with_progress(
                    msg_warn(f"时间不足: {video.name} (剩余{remaining:.0f}s)"),
                    depth=3,
                    enabled=True,
                )

        # 开播预检：立即上报一次零进度心跳（与服务端风控评估的常规心跳同格式），
        # 提前发现验证码(-12)/时长上限(-9)，避免进入观看循环后白等首个心跳(~30s)才发现
        self._precheck(rac_id, video_id, ctx, played_time, token_id, total_base)

        # 启动视频流请求（反检测）
        self._start_watch_thread(video.video_id)

        # 三维课件请求
        self._three_dimensional_course_ware(video.video_id)

        # 进入主循环
        reported = self._main_loop(
            rac_id, video_id, ctx, played_time, end_time, real_end_time, token_id, questions, total_base
        )
        if not reported:
            raise ApiError(-1, "进度上报全部失败，本视频未计入进度")

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
        total_base: int = 0,
    ) -> int:
        """视频播放主循环，返回成功上报进度的次数

        played_time 是播放位置（HH:MM:SS 与弹题时间都按它算）；
        累计学习秒数 = total_base + 本次已播放的秒数，单独随 ev 上报。

        心跳节奏与网页端一致（抓包）：
        - saveDatabaseIntervalTimeV2 约每 CLASSIC_DB_INTERVAL 秒一次，弹题时立即补一次；
        - saveCacheIntervalTimeV2 约每 CLASSIC_CACHE_INTERVAL 秒一次，触发时机与 Database 各自计时；
        - 两种上报共用一条增量链（last_submit / 观看轨迹点）：服务端把两者的本段秒都累加，
          网页抓包 Cache+180、DB+120、Cache+60、DB+65 依次累加为 863→983→1043→1108；
        - 每秒播放位置前进 speed 秒，默认 1.0，即上报的学习秒数等于真实经过的秒数。
        """
        from zhs.zhidao.quiz import ZhidaoQuizzer

        video = ctx.videos[video_id]
        speed = self._speed or DEFAULT_ZHIDAO_SPEED
        start_position = played_time
        watched = 0.0  # 本次累计观看秒数（位置前进量之和，含倍速）
        last_submit = played_time  # 两种上报共用的增量基准
        elapsed_time = 0
        db_next = _jittered(CLASSIC_DB_INTERVAL)
        cache_next = _jittered(CLASSIC_CACHE_INTERVAL)
        answer_delay: int | None = None
        current_question: PopupQuestion | None = None
        report_now = False
        reported = 0
        wp = WatchPoint()
        # 跟踪本循环内已打印的最大行宽，用于填充空格覆盖残留字符
        prev_len = len(self._progress_line) if self._progress_line else 0

        while played_time < end_time:
            time.sleep(1)
            ctx.fucked_time += 1
            elapsed_time += 1
            # 答题期间网页播放器暂停，播放位置不前进
            if answer_delay is None:
                step = min(speed, end_time - played_time)
                played_time += step
                watched += step

            if elapsed_time % 30 == 0:
                logger.debug(
                    f"Main loop: elapsed={elapsed_time}, played_time={played_time:.1f}, "
                    f"last_submit={last_submit:.1f}, "
                    f"questions={len(questions)}, answer_delay={answer_delay}"
                )

            # 观看轨迹点（每 2 秒）
            if not elapsed_time % 2:
                wp.add(int(played_time))

            # 检查弹窗题目
            if questions and played_time >= questions[-1].time_sec:
                q_point = questions.pop()
                logger.debug(
                    "popup triggered: videoId={} timeSec={} played={:.1f}s questionIds={} pending={}",
                    video_id,
                    q_point.time_sec,
                    played_time,
                    q_point.question_ids,
                    len(questions),
                )
                try:
                    quizzer = ZhidaoQuizzer(self._session)
                    current_question = quizzer.get_popup_exam(
                        rac_id,
                        video_id,
                        q_point.question_ids,
                        lesson_id=video.lesson_id,
                        lesson_video_id=video.id,
                    )
                    answer_delay = 2
                    # 网页端弹题时会立即补一次 Database 上报
                    report_now = True
                    logger.debug(
                        "popup question loaded: questionId={} options={}",
                        current_question.question_id,
                        len(current_question.question_options),
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
                        quizzer.save_answer(
                            rac_id,
                            video_id,
                            current_question.question_id,
                            answer,
                            lesson_id=video.lesson_id,
                            lesson_video_id=video.id,
                            recruit_id=ctx.course.recruit_id or 0,
                            course_id=ctx.course_id,
                        )
                        current_question = None
                else:
                    answer_delay -= 1

            finished = played_time >= end_time

            due_db = elapsed_time >= db_next or finished or report_now
            # Cache 上报：同一秒 Database 也要报时让给 Database（结尾那次只报 Database，计入进度）
            if elapsed_time >= cache_next and not due_db:
                wp.add(int(played_time))
                if self._report_cache_progress(
                    video_id, ctx, played_time, last_submit, wp.get(), token_id, total_base + int(watched)
                ):
                    last_submit = played_time
                    wp.reset(int(played_time))
                cache_next = elapsed_time + _jittered(CLASSIC_CACHE_INTERVAL)

            # Database 上报
            if due_db:
                report_now = False
                wp.add(int(played_time))
                server_total, success = self._report_progress_v2(
                    rac_id,
                    video_id,
                    ctx,
                    played_time,
                    last_submit,
                    wp.get(),
                    token_id,
                    initial=False,
                    total=total_base + int(watched),
                )
                if success:
                    reported += 1
                    # -8 同步后服务器累计时长更高：以服务器为准，后续累计从它接着加
                    if server_total > total_base + int(watched):
                        total_base = int(server_total) - int(watched)
                    last_submit = played_time
                    wp.reset(int(played_time))
                else:
                    # 上报失败：不更新 last_submit，下次上报时增量照样完整
                    logger.warning(f"Progress report failed, will retry with delta={played_time - last_submit:.1f}s")
                db_next = elapsed_time + _jittered(CLASSIC_DB_INTERVAL)

            # 显示进度条（始终相对于真实结束时间，不受时间限制影响）
            action = "answering" if answer_delay is not None else f"playing {video.video_id}"
            line = f"{action} {progress_bar(played_time, real_end_time)}"
            self._progress_line = line
            # 填充空格至已打印的最大行宽，避免变短时旧字符残留
            padded = line.ljust(prev_len)
            prev_len = len(padded)
            print(f"\r{padded}", end="", flush=True)

        # 显示最终进度（保留进度条在底部，不换行不清除）
        logger.debug(f"Main loop done: position {start_position:.0f}->{played_time:.0f}s, watched={watched:.0f}s")
        final_line = f"playing {video.video_id} {progress_bar(end_time, real_end_time)}"
        self._progress_line = final_line
        print(f"\r{final_line.ljust(prev_len)}", end="", flush=True)
        return reported

    def _prelearning_note(self, rac_id: str, video_id: int, ctx: "ZhidaoContext") -> tuple[str, int]:
        """获取学习令牌（base64 编码的 token_id）和服务器累计学习时长（studyTotalTime）

        studyTotalTime 是累计观看秒数，重看会一直往上加，可以大于视频时长；
        播放位置是另一个字段 learnTimeSec（见 _resume_position）。两者不能混用。
        """
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
        dto = result.get("data", {}).get("studiedLessonDto", {}) or {}
        self._last_note = dto
        token_id = dto.get("id", 0)
        server_time = dto.get("studyTotalTime", 0)
        return b64encode(str(token_id).encode()).decode(), server_time

    def _resume_position(self, video_sec: int) -> float:
        """上次 prelearningNote 返回的续播位置（learnTimeSec），夹在视频时长内"""
        position = (self._last_note or {}).get("learnTimeSec") or 0
        try:
            return float(min(max(int(position), 0), video_sec))
        except (TypeError, ValueError):
            return 0.0

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
        played_time: float,
        last_submit: float,
        watch_point: str,
        token_id: str,
        total: int | None = None,
    ) -> bool:
        """上报缓存进度（saveCacheIntervalTimeV2），返回是否成功

        网页端 Cache 与 Database 的 ev 字段顺序不同（抓包）：
        recruitId;chapterId;courseId;lessonId;HH:MM:SS;累计秒;videoId;lessonVideoId;本段秒;uuid+"zhs"
        本段秒按「自上次任意上报以来」计算（与 Database 共用基准）。Cache 上报失败不影响主流程。
        """
        url = f"{self._session.urls.study}/gateway/t/v1/learning/saveCacheIntervalTimeV2"
        video = ctx.videos[video_id]
        course_info = ctx.course.course_info
        raw_ev: list[int | str] = [
            ctx.course.recruit_id or 0,
            video.chapter_id,
            course_info.course_id if course_info else 0,
            video.lesson_id,
            _hms(min(video.video_sec, int(played_time))),
            int(played_time) if total is None else int(total),
            video.video_id,
            video.id,
            int(played_time - last_submit),
            (self._session.uuid or "") + "zhs",
        ]
        data: dict[str, Any] = {
            "ewssw": watch_point,
            "sdsew": encode_ev(raw_ev, self._session.crypto.ev_key),
            "zwsds": token_id,
        }
        try:
            self._session.zhidao_query(url, data)
        except CaptchaRequired:
            raise
        except Exception as exc:
            logger.debug(f"Cache progress report failed (ignored): {exc}")
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
    ) -> None:
        """开播前预检上报：delta=0 的常规心跳格式，提前发现验证码/时长上限

        实测：服务端风控仅在常规心跳（initial=False）上评估，
        initial=True 补报不返回 -12/-9，故用 last_submit=played_time 的
        零进度心跳预检，不虚报进度。

        Raises:
            CaptchaRequired: 服务端要求验证码（code -12）
            TimeLimitExceeded: 学习时长已达上限（code -9）
        """
        watch_point = WatchPoint()
        watch_point.add(int(played_time))
        self._report_progress_v2(
            rac_id, video_id, ctx, played_time, played_time, watch_point.get(), token_id, initial=False, total=total
        )

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
        total: int | None = None,
    ) -> tuple[float, bool]:
        """上报进度 V2，返回 (累计学习秒数, 是否上报成功)

        ev 里有三个时间字段，抓包对照：本段秒 = 位置差，累计秒 = studyTotalTime 往上加，
        HH:MM:SS = 播放位置。total 为 None 时退化为旧行为（累计秒取播放位置）。
        """
        total_seconds = int(played_time) if total is None else int(total)
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
                _hms(min(video.video_sec, int(played_time))),
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
                total_seconds,
                _hms(min(video.video_sec, int(played_time))),
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
                    if server_time > total_seconds:
                        # 「学习总时长下降了」只说明累计秒低于服务端记录：
                        # 本段秒与播放位置照旧，累计秒改为 服务端记录 + 本段秒
                        new_total = int(server_time) + int(played_time - last_submit)
                        raw_ev[7] = new_total
                        data["sdsew"] = encode_ev(raw_ev, self._session.crypto.ev_key)
                        data["zwsds"] = new_token
                        self._session.zhidao_query(url, data)
                        logger.info(
                            f"Progress report succeeded after -8 sync (server={server_time}s, total={new_total}s)"
                        )
                        return float(new_total), True
                except Exception as retry_exc:
                    logger.error(f"Progress report failed after -8 retry: {retry_exc}")
            else:
                logger.error(f"Failed to report progress: {exc}")
        return played_time, False

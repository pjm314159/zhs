"""polymas 智慧课程视频播放器

播放循环对齐 zhidao/hike 反检测策略（随机速度/偶发暂停/随机上报间隔），
进度以服务端 resource/detail（endWatchTime/completePercentage）为准，
上报走 record/report 区间报文（F9 未实测，字段按 PR #168 占位）。
"""

from __future__ import annotations

import time
from datetime import datetime
from random import randint, random, uniform
from typing import TYPE_CHECKING, Any

from loguru import logger

from zhs.config import PolymasConfig
from zhs.exceptions import TimeLimitExceeded
from zhs.polymas.models import PolymasCourse, PolymasVideoNode
from zhs.session import ZhsSession
from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, progress_bar, tree_print, wipe_line

if TYPE_CHECKING:
    from zhs.polymas.course import PolymasCourseManager

_DETAIL_PATH = "/student-course/study/student/resource/detail"
_REPORT_PATH = "/student-course/study/student/record/report"

_TIME_FMT = "%Y-%m-%d %H:%M:%S"
_CLIENT_TYPE = "Windows"  # TODO(F9/R3): PR 用 "1"，实测后校正


class PolymasVideoPlayer:
    """polymas 智慧课程视频播放器"""

    def __init__(
        self,
        session: ZhsSession,
        config: PolymasConfig,
        end_threshold: float = 0.91,
        time_limit: int = 0,
    ) -> None:
        self._session = session
        self._cfg = config
        self._end_threshold = end_threshold
        self._time_limit = time_limit
        self._fucked_time = 0

    def play_course(self, course: PolymasCourse, mgr: PolymasCourseManager) -> None:
        """播放整个课程（单视频失败不中断，TimeLimitExceeded 冒泡）"""
        begin_time = time.time()
        tree_print(f"{course_tag('polymas')} 课程: {course.course_name}", enabled=True)
        try:
            videos = mgr.get_video_nodes(course)
            if not videos:
                tree_print(msg_warn("无可播放视频节点"), depth=1, enabled=True)
                return
            for node in videos:
                try:
                    self.play_video(course, node, mgr)
                except TimeLimitExceeded:
                    raise
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    tree_print(msg_error(f"!! 视频失败: {node.title} - {exc}"), depth=1, enabled=True)
        except KeyboardInterrupt:
            tree_print(msg_warn("!! 用户中断"), enabled=True)
        cost = time.time() - begin_time
        tree_print(msg_done(f"完成课程: {course.course_name} ({cost:.1f}s)"), depth=1, enabled=True)

    def play_video(self, course: PolymasCourse, node: PolymasVideoNode, mgr: PolymasCourseManager) -> None:
        """播放单个视频：查服务端进度 → 跳过已完成 → 主循环上报"""
        detail = self._resource_detail(course, node, mgr)
        duration = float(detail.get("duration") or node.duration)
        played = float(detail.get("endWatchTime") or 0)
        finished = detail.get("isFinished")
        pct = detail.get("completePercentage")
        if pct is None:
            pct = node.complete_percentage

        # 完成判断：isFinished 优先，其次百分比阈值（0-100 语义，TODO: F10 校正）
        if finished or (pct is not None and float(pct) / 100 >= self._end_threshold):
            tree_print(msg_skip(f"跳过(已完成): {node.title}"), depth=1, enabled=True)
            return

        end_time = max(duration * self._end_threshold, 1.0)
        if played >= end_time:
            tree_print(msg_skip(f"跳过(进度已达阈值): {node.title}"), depth=1, enabled=True)
            return

        tree_print(f"视频: {node.chapter}/{node.title}", depth=1, enabled=True)
        self._main_loop(course, node, played, end_time)
        # 人类延迟
        time.sleep(random() + 1)
        logger.info(f"Finished polymas video {node.resource_id} of course {course.course_id}")

    def _main_loop(self, course: PolymasCourse, node: PolymasVideoNode, played_time: float, end_time: float) -> None:
        """播放主循环：随机速度前进 + 随机间隔上报"""
        cfg = self._cfg
        speed = cfg.base_speed + uniform(-cfg.speed_jitter, cfg.speed_jitter)
        last_submit = played_time
        segment_start = datetime.now()
        elapsed = 0
        db_interval = self._next_interval()
        pause = 0
        prev_len = 0

        while played_time < end_time:
            time.sleep(1)
            self._fucked_time += 1
            elapsed += 1
            played_time = min(played_time + speed, end_time)

            # 时间限制
            if self._time_limit > 0 and self._fucked_time >= self._time_limit:
                raise TimeLimitExceeded(f"时间限制已达 {self._time_limit}s，停止课程 {course.course_name}")

            # 偶发暂停（模拟人类离开，暂停期间不前进）
            pause = pause or int(random() < cfg.pause_prob) * cfg.pause_duration
            if pause:
                pause -= 1
                played_time = last_submit

            # 随机间隔上报（到达阈值时补最后一次）
            if elapsed % db_interval == 0 or played_time >= end_time:
                try:
                    self._report(course, node, int(last_submit), int(played_time), segment_start)
                except Exception as exc:
                    # 上报失败：不更新 last_submit，下次重试区间正确
                    logger.warning(f"Progress report failed: {exc}")
                else:
                    last_submit = played_time
                    segment_start = datetime.now()
                    db_interval = self._next_interval()
                    speed = cfg.base_speed + uniform(-cfg.speed_jitter, cfg.speed_jitter)

            # 进度条
            line = f"playing {node.title} {progress_bar(played_time, end_time)}"
            padded = line.ljust(prev_len)
            prev_len = len(padded)
            print(f"\r{padded}", end="", flush=True)

        wipe_line()

    def _next_interval(self) -> int:
        """随机上报间隔：interval ± jitter（randint 区间）"""
        return randint(
            self._cfg.report_interval - self._cfg.report_jitter,
            self._cfg.report_interval + self._cfg.report_jitter,
        )

    def _resource_detail(
        self, course: PolymasCourse, node: PolymasVideoNode, mgr: PolymasCourseManager
    ) -> dict[str, Any]:
        """资源详情（只读，刷新服务端进度视图）"""
        body = self._session.polymas_query(
            f"{self._session.urls.polymas_api}{_DETAIL_PATH}",
            {
                "courseId": course.course_id,
                "libraryFolderId": mgr.library_folder_id(course),
                "resourceId": node.resource_id,
                "term": int(course.term),
            },
        )
        data: dict[str, Any] = body.get("data") or {}
        return data

    def _report(
        self,
        course: PolymasCourse,
        node: PolymasVideoNode,
        start: int,
        end: int,
        segment_start: datetime,
    ) -> None:
        """上报学习进度（record/report 区间报文）

        TODO(F9/R3): 报文字段按 PR #168/probe 占位，真实 hikeAiCourse 实测后校正。
        """
        body: dict[str, object] = {
            "startWatchTime": start,
            "endWatchTime": end,
            "startDate": segment_start.strftime(_TIME_FMT),
            "endDate": datetime.now().strftime(_TIME_FMT),
            "studyTotalTime": end - start,
            "courseId": course.course_id,
            "resourceId": node.resource_id,
            "clientType": _CLIENT_TYPE,
            "term": int(course.term),
        }
        self._session.polymas_query(f"{self._session.urls.polymas_api}{_REPORT_PATH}", body)

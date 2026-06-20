"""Hike 职教云视频播放"""

import time
from random import random
from threading import Thread

import httpx
from loguru import logger

from zhs.exceptions import CaptchaRequired, TimeLimitExceeded
from zhs.hike.models import FileInfo, ResourceNode
from zhs.session import ZhsSession
from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, progress_bar, tree_print, wipe_line


class HikeVideoPlayer:
    """Hike 视频播放器"""

    def __init__(
        self,
        session: ZhsSession,
        speed: float | None = None,
        end_threshold: float = 0.91,
        time_limit: int = 0,
    ) -> None:
        self._session = session
        self._speed = speed
        self._end_threshold = end_threshold
        self._time_limit = time_limit
        self._fucked_time = 0

    @property
    def speed(self) -> float:
        return self._speed or 1.25

    def play_course(self, course_id: str, root: list[ResourceNode]) -> None:
        """播放整个 Hike 课程"""
        begin_time = time.time()
        tree_print(f"{course_tag('hike')} 课程: {course_id} ({len(root)} 个根章节)", enabled=True)
        try:
            for chapter in root:
                self._traverse(course_id, chapter)
        except KeyboardInterrupt:
            tree_print(msg_warn("!! 用户中断"), enabled=True)
        cost = time.time() - begin_time
        tree_print(msg_done(f"完成课程: {course_id} ({cost:.1f}s)"), depth=1, enabled=True)

    def _traverse(self, course_id: str, node: ResourceNode, depth: int = 0) -> None:
        """递归遍历资源树"""
        depth += 1
        tv = True

        if node.child_list is not None:
            # 章节节点：递归遍历子节点
            tree_print(f"章节: {node.name}", depth=depth, enabled=tv)
            for child in node.child_list:
                self._traverse(course_id, child, depth)
            return

        # 叶子节点
        study_time = node.study_time or 0
        total_time = node.total_time or 0

        # 已完成跳过
        if total_time > 0 and study_time >= total_time * self._end_threshold:
            tree_print(msg_skip(f"跳过(已完成): {node.name}"), depth=depth, enabled=tv)
            return

        try:
            if node.data_type == 3:
                # 视频
                file_id = node.file_id or node.id
                tree_print(f"视频: {node.name}", depth=depth, enabled=tv)
                self.play_video(course_id, file_id, study_time)
            elif node.data_type is None:
                if node.file_id is not None:
                    tree_print(f"文件: {node.name}", depth=depth, enabled=tv)
                    self.play_file(course_id, node.file_id)
                else:
                    tree_print(msg_skip(f"跳过(测验/讨论): {node.name}"), depth=depth, enabled=tv)
            else:
                # 其他类型：有 file_id 且 file_name 非空则 play_file
                if node.file_id is not None and node.file_name:
                    tree_print(f"文件: {node.name}", depth=depth, enabled=tv)
                    self.play_file(course_id, node.file_id)
                else:
                    tree_print(msg_skip(f"跳过(data_type={node.data_type}): {node.name}"), depth=depth, enabled=tv)
        except TimeLimitExceeded:
            raise
        except CaptchaRequired:
            raise
        except Exception as exc:
            tree_print(msg_error(f"!! 处理失败: {node.name} - {exc}"), depth=depth, enabled=tv)

    def play_video(self, course_id: str, file_id: int, prev_time: int = 0) -> None:
        """播放单个视频"""
        logger.info(f"Playing Hike video {file_id} of course {course_id}")

        # 获取视频信息
        file_info = self._stu_view_file(course_id, file_id)
        if file_info is None:
            logger.error(f"Failed to get video info for {file_id}")
            return

        # 模拟视频播放（在新线程中请求视频流）
        self._watch_video(file_info.data_id)

        # 主循环
        total_time = file_info.total_time
        speed = self.speed
        start_date = int(time.time() * 1000)
        end_time = max(total_time * self._end_threshold, 1.0)
        played_time = float(prev_time)
        interval = 30

        while played_time <= end_time:
            time.sleep(1)
            self._fucked_time += 1
            played_time = min(played_time + speed, end_time)

            # 时间限制检查
            if self._time_limit > 0 and self._fucked_time >= self._time_limit:
                raise TimeLimitExceeded(f"Time limit reached for course {course_id}")

            # 上报进度
            if played_time >= end_time or not (int(played_time - prev_time) % interval):
                try:
                    ret_time = self.save_stu_study_record(course_id, file_id, played_time, prev_time, start_date)
                    prev_time = ret_time
                    # 只在服务器时间更大时才更新 played_time，防止进度回退
                    if ret_time > played_time:
                        played_time = float(ret_time)
                except Exception as exc:
                    # 上报失败：不更新 prev_time，下次重试时增量正确
                    logger.warning(f"Failed to save study record for {file_id}: {exc}")

            # 显示进度条
            bar_str = progress_bar(int(played_time), int(end_time))
            print(f"\rplaying {file_id} {bar_str}", end="", flush=True)

        wipe_line()

        # 人类延迟
        time.sleep(random() + 1)
        logger.info(f"Finished Hike video {file_id}")

    def play_file(self, course_id: str, file_id: int) -> None:
        """标记文件已查看"""
        try:
            self._stu_view_file(course_id, file_id)
        except Exception as exc:
            logger.error(f"Failed to view file {file_id}: {exc}")
            return
        time.sleep(random() * 2 + 1)

    def save_stu_study_record(
        self,
        course_id: str,
        file_id: int,
        played_time: float,
        prev_time: float,
        start_date: int,
    ) -> int:
        """上报学习进度，返回服务器确认的学习时间"""
        url = "https://hike-teaching.zhihuishu.com/stuStudy/saveStuStudyRecord"
        params = {
            "uuid": self._session.uuid or "",
            "courseId": course_id,
            "fileId": file_id,
            "studyTotalTime": int(played_time - prev_time),
            "startWatchTime": int(prev_time),
            "endWatchTime": int(played_time),
            "startDate": start_date,
            "endDate": int(time.time() * 1000),
        }
        result = self._session.hike_query(url, params, sig=True)
        rt = result.get("rt")
        if rt is None:
            raise Exception("Failed to save study record")
        return int(rt)

    def _stu_view_file(self, course_id: str, file_id: int) -> FileInfo | None:
        """获取文件/视频信息"""
        url = "https://studyresources.zhihuishu.com/studyResources/stuResouce/stuViewFile"
        params = {"courseId": course_id, "fileId": file_id}
        result = self._session.hike_query(url, params)
        rt = result.get("rt")
        if rt is None:
            return None
        try:
            return FileInfo.model_validate(rt)
        except Exception as exc:
            logger.error(f"Failed to parse file info: {exc}")
            return None

    def _watch_video(self, data_id: int) -> None:
        """在新线程中请求视频流"""

        def _watch() -> None:
            try:
                with httpx.Client(timeout=30) as client:
                    client.get(
                        f"{self._session.urls.newbase}/video/initVideo",
                        params={
                            "jsonpCallBack": "result",
                            "videoID": str(data_id),
                            "_": int(time.time() * 1000),
                        },
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                                " AppleWebKit/537.36 (KHTML, like Gecko)"
                                " Chrome/101.0.4951.64 Safari/537.36"
                            ),
                            "Referer": "https://hike.zhihuishu.com/",
                        },
                    )
            except Exception as exc:
                logger.error(f"Failed to watch video {data_id}: {exc}")

        thread = Thread(target=_watch, daemon=True)
        thread.start()

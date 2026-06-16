"""AI 视频播放器

从 AiCourseManager 中提取的视频播放逻辑，
负责 AI 课程视频的进度上报和模拟播放。
"""

import time
from typing import Any

from loguru import logger

from zhs.session import ZhsSession


class AiVideoPlayer:
    """AI 视频播放器

    管理 AI 课程视频的播放进度上报和视频流请求。
    """

    def __init__(self, session: ZhsSession, speed: float = 1.5) -> None:
        self._session = session
        self._speed = speed

    def _ai_query(self, url: str, data: dict[str, Any], content_type: str = "json") -> dict[str, Any]:
        """AI 课程 API 查询（使用 ai_key，默认 JSON）"""
        return self._session.zhidao_query(
            url, data, key=self._session.crypto.key_bytes("ai_key"), ok_code=200, content_type=content_type
        )

    def play_video(
        self,
        course_id: int,
        class_id: int,
        file_id: int,
        knowledge_id: int,
        start_at: int = 0,
        speed: float | None = None,
    ) -> None:
        """播放 AI 视频（speed*2, 2s 间隔）"""
        play_speed = speed if speed is not None else self._speed

        # 获取视频长度
        url = f"{self._session.urls.ai}/run/gateway/t/stu/resources-lab/get-video-time"
        data = {"courseId": course_id, "classId": class_id, "videoIdList": [file_id]}
        result = self._ai_query(url, data)
        video_length = result["data"][0]["time"]

        # 模拟真实播放（请求视频链接）
        self._watch_video(file_id)

        played_time = start_at

        while played_time < video_length:
            played_time = min(int(round(played_time + play_speed * 2)), video_length)
            self._report_video_progress(course_id, class_id, file_id, knowledge_id, played_time)
            time.sleep(2)

    def _watch_video(self, file_id: int) -> None:
        """模拟真实视频播放请求（独立线程）"""
        import threading

        def _request() -> None:
            try:
                import httpx

                url = f"{self._session.urls.newbase}/video/initVideo"
                client = httpx.Client(timeout=30.0)
                client.get(url, params={"fileId": file_id})
                client.close()
            except Exception as e:
                logger.debug(f"watchVideo 请求失败（可忽略）: {e}")

        t = threading.Thread(target=_request, daemon=True)
        t.start()

    def _report_video_progress(
        self,
        course_id: int,
        class_id: int,
        file_id: int,
        knowledge_id: int,
        last_watch_time: int,
    ) -> bool:
        """上报视频进度"""
        url = f"{self._session.urls.ai}/run/gateway/t/stu/studyRecord/report"
        data = {
            "courseId": course_id,
            "classId": class_id,
            "fileId": file_id,
            "knowledgeId": knowledge_id,
            "lastWatchTime": last_watch_time,
            "studyTotalTime": 10,
            "shareCourseId": "",
            "nodeType": 0,
            "watchUId": 1,
            "dateFormate": int(time.time() * 1000),
        }
        try:
            self._ai_query(url, data)
            return True
        except Exception as e:
            logger.error(f"上报视频进度失败: {e}")
            return False

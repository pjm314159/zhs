"""知到课程管理

ZhidaoCourseManager 提供课程列表获取、上下文构建等功能。
所有 URL 从 UrlConfig 获取，密钥从 CryptoConfig 获取。
"""

import contextlib
import math
from typing import Any

from loguru import logger

from zhs.session import ZhsSession
from zhs.zhidao.models import (
    CourseInfo,
    VideoChapter,
    VideoSmallLesson,
    ZhidaoContext,
    ZhidaoCourse,
)


class ZhidaoCourseManager:
    """知到课程管理"""

    def __init__(self, session: ZhsSession) -> None:
        self._session = session
        self._context_cache: dict[str, ZhidaoContext] = {}

    def get_course_list(self) -> list[ZhidaoCourse]:
        """获取知到共享课程列表（分页）"""
        url = f"{self._session.urls.base}/gateway/t/v1/student/course/share/queryShareCourseInfo"
        page = 1
        page_size = 5
        data: dict[str, Any] = {"status": 0, "pageNo": page, "pageSize": page_size}
        result = self._session.zhidao_query(url, data, key=self._session.crypto.key_bytes("home_key"), ok_code=200)
        total = result.get("result", {}).get("totalCount", 0)
        courses_data = result.get("result", {}).get("courseOpenDtos") or []
        courses = [ZhidaoCourse.model_validate(c) for c in courses_data]

        # 分页获取剩余课程
        total_pages = math.ceil(total / page_size)
        for p in range(2, total_pages + 1):
            data["pageNo"] = p
            result = self._session.zhidao_query(url, data, key=self._session.crypto.key_bytes("home_key"), ok_code=200)
            more = result.get("result", {}).get("courseOpenDtos") or []
            courses.extend(ZhidaoCourse.model_validate(c) for c in more)

        return courses

    def get_context(self, rac_id: str, force: bool = False) -> ZhidaoContext:
        """获取知到课程上下文

        Args:
            rac_id: recruitAndCourseId
            force: 强制更新缓存
        """
        if rac_id in self._context_cache and not force:
            return self._context_cache[rac_id]

        logger.info(f"Getting context for {rac_id}")

        # 1. 跨站登录
        self.gologin(rac_id)

        # 2. 获取课程信息
        course_data = self.query_course(rac_id)
        recruit_id: int = course_data.get("recruitId", 0)
        course_info_data = course_data.get("courseInfo", {})
        course_info = CourseInfo.model_validate(course_info_data) if course_info_data else None

        # 3. 获取章节/视频列表
        chapters_data = self.video_list(rac_id)
        course_id: int = chapters_data.get("courseId", 0)

        # 4. 处理章节树，构建视频字典
        chapters: list[VideoChapter] = []
        videos: dict[int, VideoSmallLesson] = {}
        lesson_ids: list[int] = []

        for ch_data in chapters_data.get("videoChapterDtos", []):
            chapter = VideoChapter.model_validate(ch_data)
            chapters.append(chapter)

            for lesson in chapter.video_lessons:
                lesson_ids.append(lesson.id)

                # 单视频课时：有 videoId 但没有 videoSmallLessons
                if lesson.video_id and not lesson.video_small_lessons:
                    small = VideoSmallLesson(
                        video_id=lesson.video_id,
                        id=0,
                        name=lesson.name,
                        lesson_id=lesson.id,
                        chapter_id=chapter.id,
                        video_sec=lesson.video_sec,
                    )
                    lesson.video_small_lessons = [small]

                for v in lesson.video_small_lessons:
                    v.chapter_id = chapter.id
                    videos[v.video_id] = v

        logger.info(f"{len(lesson_ids)} lessons, {len(videos)} videos")

        # 5. 获取学习状态
        video_ids = [v.id for v in videos.values() if v.id]
        if lesson_ids or video_ids:
            states = self.query_study_info(lesson_ids, video_ids, recruit_id)
            lv_states = states.get("lv", {})
            lesson_states = states.get("lesson", {})
            for v in videos.values():
                state = lv_states.get(str(v.id)) or lesson_states.get(str(v.lesson_id))
                if state:
                    v.watch_state = state.get("watchState", 0)
                    v.study_total_time = state.get("studyTotalTime", 0)

        # 6. 获取最近观看视频（非必须）
        self.query_user_recruit_id_last_video_id(recruit_id)

        # 7. 构建上下文
        course = ZhidaoCourse(
            secret=rac_id,
            course_name=course_info.name if course_info else "",
            course_info=course_info,
            recruit_id=recruit_id,
        )
        ctx = ZhidaoContext(
            course=course,
            chapters=chapters,
            videos=videos,
            course_id=course_id,
        )
        self._context_cache[rac_id] = ctx
        return ctx

    def gologin(self, rac_id: str) -> None:
        """跨站登录（返回 HTML，不解析 JSON）"""
        url = f"{self._session.urls.study}/login/gologin"
        params = {"fromurl": f"https://studyh5.zhihuishu.com/videoStudy.html#/studyVideo?recruitAndCourseId={rac_id}"}
        client = self._session._get_client()
        client.get(url, params=params)

    def query_course(self, rac_id: str) -> dict[str, Any]:
        """查询课程信息，返回原始 data（含 recruitId、courseInfo 等）"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryCourse"
        result = self._session.zhidao_query(url, {"recruitAndCourseId": rac_id})
        data: dict[str, Any] = result["data"]
        return data

    def video_list(self, rac_id: str) -> dict[str, Any]:
        """获取章节/视频列表"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/videolist"
        result = self._session.zhidao_query(url, {"recruitAndCourseId": rac_id})
        data: dict[str, Any] = result["data"]
        return data

    def query_study_info(self, lesson_ids: list[int], video_ids: list[int], recruit_id: int) -> dict[str, Any]:
        """查询学习状态"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryStuyInfo"
        data = {"lessonIds": lesson_ids, "lessonVideoIds": video_ids, "recruitId": recruit_id}
        result = self._session.zhidao_query(url, data)
        resp: dict[str, Any] = result["data"]
        return resp

    def query_user_recruit_id_last_video_id(self, recruit_id: int) -> None:
        """获取最近观看视频"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryUserRecruitIdLastVideoId"
        with contextlib.suppress(Exception):
            self._session.zhidao_query(url, {"recruitId": recruit_id})

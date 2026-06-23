"""Hike 职教云课程管理"""

from datetime import UTC, datetime

from loguru import logger

from zhs.hike.models import HikeCourse, ResourceNode
from zhs.session import ZhsSession


class HikeCourseManager:
    """Hike 课程管理器"""

    def __init__(self, session: ZhsSession) -> None:
        self._session = session
        self._courses: list[HikeCourse] | None = None
        self._context_cache: dict[str, list[ResourceNode]] = {}

    def get_course_list(self) -> list[HikeCourse]:
        """获取 Hike 课程列表"""
        if self._courses is not None:
            return self._courses

        url = "https://hikeservice.zhihuishu.com/student/course/aided/getMyCourseList"
        now = datetime.now(UTC)
        params = {
            "uuid": self._session.uuid or "",
            "data": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        }
        result = self._session.hike_query(url, params, ok_code=0)
        raw_list = result.get("result", {}).get("startInngcourseList") or []
        self._courses = [HikeCourse.model_validate(c) for c in raw_list]
        logger.info(f"Got {len(self._courses)} Hike courses")
        return self._courses

    def get_context(self, course_id: str, force: bool = False) -> list[ResourceNode]:
        """获取课程资源树上下文"""
        if course_id in self._context_cache and not force:
            return self._context_cache[course_id]

        root = self.query_resource_menu_tree(course_id)
        self._context_cache[course_id] = root
        return root

    def query_resource_menu_tree(self, course_id: str) -> list[ResourceNode]:
        """获取资源菜单树"""
        url = "https://studyresources.zhihuishu.com/studyResources/stuResouce/queryResourceMenuTree"
        params = {"courseId": course_id}
        result = self._session.hike_query(url, params)
        raw_list = result.get("rt") or []
        nodes = [ResourceNode.model_validate(n) for n in raw_list]
        logger.info(f"Got resource tree for course {course_id}: {len(nodes)} root nodes")
        return nodes

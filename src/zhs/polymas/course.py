"""polymas 智慧课程（hikeAiCourse）管理器

信息获取分层（见 .temp/polymas_dev.md §3.2）：
- 会话级：get-current-user-detail 查 1 次缓存（school_nid/school_id/zhs_uid...）
- 列表级：queryStudentCourse 分页拉全，courseType 严格过滤 hikeAiCourse
- 兜底：顶层 classId 为 null 时 classList 查 1 次
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from zhs.exceptions import ZhsError
from zhs.polymas.models import PolymasCourse, PolymasNode, PolymasVideoNode
from zhs.session import ZhsSession

_USER_DETAIL_PATH = "/user/user/v2/get-current-user-detail"
_COURSE_LIST_PATH = "/student-course/student/index/queryStudentCourse"
_CLASS_LIST_PATH = "/student-course/student/classList"
_LIBRARY_PATH = "/teacher-course/library/course/findStudyLibraryByCourseId"
_TREE_PATH = "/student-course/study/student/resource/queryTree"

_PAGE_SIZE = 16


class PolymasCourseManager:
    """polymas 智慧课程列表/信息管理器

    Args:
        session: ZhsSession（使用其 polymas_query 与 urls.polymas_api）
    """

    def __init__(self, session: ZhsSession) -> None:
        self._session = session
        self._user_detail: dict[str, Any] | None = None
        self._library_cache: dict[str, str] = {}

    # --- 会话级（查 1 次，整会话复用）---

    def get_user_detail(self) -> dict[str, Any]:
        """当前用户详情（get-current-user-detail），会话级缓存

        Returns:
            data 字段（含 schoolInfo.nid / schoolInfo.schoolId / zhsUid / zhsUuid）
        """
        if self._user_detail is None:
            # 真实接口仅支持 POST（GET 返回 code=100000 系统异常）
            body = self._session.polymas_query(f"{self._session.urls.polymas_api}{_USER_DETAIL_PATH}", {})
            self._user_detail = body.get("data") or {}
        return self._user_detail

    @property
    def school_nid(self) -> str:
        """polymas schoolId（schoolInfo.nid，如 "oeL1v3eiRe"）"""
        info = self.get_user_detail().get("schoolInfo") or {}
        return str(info.get("nid") or "")

    @property
    def school_id(self) -> str:
        """知到体系数字学校 ID（schoolInfo.schoolId，如 "625"）"""
        info = self.get_user_detail().get("schoolInfo") or {}
        sid = info.get("schoolId")
        return "" if sid is None else str(sid)

    # --- 列表级 ---

    def get_course_list(self) -> list[PolymasCourse]:
        """获取 hikeAiCourse 课程列表

        - 分页拉全 queryStudentCourse（status=2 对齐网页端）
        - courseType 严格过滤：只收 hikeAiCourse
          （shareCourse/mapCourse 分别由知到/AI 模块输出，避免重复课程）
        - 顶层 classId 为 null 时 classList 兜底查询

        Raises:
            ApiError: 任一请求失败（失败即停，不产生不完整列表）
        """
        base = self._session.urls.polymas_api
        courses: list[PolymasCourse] = []
        fetched = 0
        page = 1
        while True:
            body = self._session.polymas_query(
                f"{base}{_COURSE_LIST_PATH}",
                {
                    "keyword": "",
                    "term": "",
                    "schoolId": self.school_nid,
                    "status": 2,
                    "page": page,
                    "size": _PAGE_SIZE,
                },
            )
            data = body.get("data") or {}
            items = data.get("list") or []
            for item in items:
                if item.get("courseType") != "hikeAiCourse":
                    continue
                course = PolymasCourse.model_validate(item)
                if course.class_id is None:
                    # PR #168 链：顶层 classId → studentClasses[0].classId → classList 兜底
                    course.class_id = course.student_class_id() or self._fetch_class_id(course)
                courses.append(course)
            fetched += len(items)
            total = int(data.get("total") or 0)
            if not items or fetched >= total:
                break
            page += 1
        return courses

    def _fetch_class_id(self, course: PolymasCourse) -> str | None:
        """classList 兜底：取第一个班级 ID（无班级返回 None，播放时校验）"""
        body = self._session.polymas_query(
            f"{self._session.urls.polymas_api}{_CLASS_LIST_PATH}",
            {"courseId": course.course_id, "term": course.term},
        )
        classes = body.get("data") or []
        for item in classes:
            cid = item.get("classId")
            if cid:
                return str(cid)
        return None

    # --- 资源级（每课查 1 次拉全）---

    def library_folder_id(self, course: PolymasCourse) -> str:
        """学习库 ID（findStudyLibraryByCourseId，course_id 维度懒加载缓存）"""
        if course.course_id not in self._library_cache:
            body = self._session.polymas_query(
                f"{self._session.urls.polymas_api}{_LIBRARY_PATH}",
                {"courseId": course.course_id, "term": course.term},
                method="GET",
            )
            self._library_cache[course.course_id] = str(body.get("data") or "")
        return self._library_cache[course.course_id]

    def get_resource_tree(self, course: PolymasCourse) -> list[PolymasNode]:
        """获取课程资源树（queryTree），classId/term 缺失时失败即停

        Raises:
            ZhsError: classId 为 None 或 terms 为空（无法构造必需参数）
        """
        if course.class_id is None:
            raise ZhsError(f"课程 {course.course_name} 缺少 classId，无法拉取资源树")
        if not course.term:
            raise ZhsError(f"课程 {course.course_name} 缺少 term，无法拉取资源树")
        base = self._session.urls.polymas_api
        body = self._session.polymas_query(
            f"{base}{_TREE_PATH}",
            {
                "libraryFolderId": self.library_folder_id(course),
                "classId": course.class_id,
                "courseId": course.course_id,
                "term": int(course.term),
            },
        )
        data = body.get("data") or []
        return [PolymasNode.model_validate(n) for n in data]

    def get_video_nodes(self, course: PolymasCourse) -> list[PolymasVideoNode]:
        """获取可播放视频节点（树展平 + 过滤无 ossUrl/时长为 0 的非视频资源）"""
        tree = self.get_resource_tree(course)
        videos: list[PolymasVideoNode] = []
        for node in tree:
            for v in node.flatten_videos():
                if not v.oss_url or v.duration <= 0:
                    logger.warning(f"跳过非视频资源: {v.chapter}/{v.title}（无 ossUrl 或时长为 0）")
                    continue
                videos.append(v)
        return videos


__all__ = ["PolymasCourseManager"]

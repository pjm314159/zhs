"""polymas 智慧课程（hikeAiCourse）课程管理器测试

fixture 基于 2026-09-28 真实抓包（.temp/hike-new/out/*.json，字段结构一致、数据精简）。
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from zhs.exceptions import ApiError, ZhsError
from zhs.polymas.course import PolymasCourseManager
from zhs.polymas.models import PolymasCourse, PolymasNode


def _user_detail_body() -> dict[str, Any]:
    """get-current-user-detail 真实响应（精简）"""
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "userNid": "QwXcQbkosb",
            "realName": "测试用户",
            "schoolCertificationNid": "oeL1v3eiRe",
            "schoolInfo": {"nid": "oeL1v3eiRe", "schoolName": "测试大学", "schoolId": 625},
            "zhsUid": "892074277",
            "zhsUuid": "Xe6arnRO",
        },
    }


def _course_item(
    course_id: int = 2036787923612635136,
    name: str = "大一体育理论体育与健康",
    course_type: str = "mapCourse",
    class_id: str | None = "203843",
    student_classes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """queryStudentCourse 条目（字段结构照真实响应）"""
    return {
        "courseId": course_id,
        "courseName": name,
        "courseType": course_type,
        "terms": [20271],
        "classId": class_id,
        "studentClasses": student_classes,
        "courseStatus": None,
        "status": 3,
        "newFlag": True,
        "linkUrl": "https://ai-smart-course-student-pro.zhihuishu.com/singleCourse",
        "origenParam": None,
    }


def _course_list_body(items: list[dict[str, Any]], total: int = 2) -> dict[str, Any]:
    return {"code": 200, "msg": "success", "data": {"list": items, "total": total}}


def _class_list_body() -> dict[str, Any]:
    return {"code": 200, "msg": "success", "data": [{"classId": "203843", "term": 20271}]}


@pytest.fixture
def mock_session() -> MagicMock:
    """mock ZhsSession：只需 polymas_query 与 urls"""
    session = MagicMock()
    session.urls.polymas_api = "https://cloudapi.polymas.com"
    session.urls.polymas_origin = "https://hike-teaching-center.polymas.com"
    return session


class TestPolymasCourseModel:
    def test_parses_real_payload(self) -> None:
        """数字 courseId/term 自动转 str（pydantic v2 不做 int→str 隐式转换）"""
        c = PolymasCourse.model_validate(_course_item())
        assert c.course_id == "2036787923612635136"
        assert c.course_name == "大一体育理论体育与健康"
        assert c.course_type == "mapCourse"
        assert c.terms == ["20271"]
        assert c.class_id == "203843"

    def test_null_class_id(self) -> None:
        """classId=null → None，等待 studentClasses/classList 兜底"""
        c = PolymasCourse.model_validate(_course_item(class_id=None))
        assert c.class_id is None

    def test_student_classes_parsed(self) -> None:
        """PR #168 班级来源：studentClasses[0].classId 可解析"""
        c = PolymasCourse.model_validate(
            _course_item(class_id=None, student_classes=[{"classId": "sc9", "name": "1班"}])
        )
        assert c.student_classes == [{"classId": "sc9", "name": "1班"}]
        assert c.student_class_id() == "sc9"

    def test_student_classes_empty_or_null(self) -> None:
        """studentClasses 为 null/空/无 classId → student_class_id 返回 None"""
        c_null = PolymasCourse.model_validate(_course_item(class_id=None))
        assert c_null.student_class_id() is None
        c_empty = PolymasCourse.model_validate(_course_item(class_id=None, student_classes=[]))
        assert c_empty.student_class_id() is None
        c_bad = PolymasCourse.model_validate(_course_item(class_id=None, student_classes=[{"foo": 1}]))
        assert c_bad.student_class_id() is None

    def test_term_property(self) -> None:
        """term = terms[0]"""
        c = PolymasCourse.model_validate(_course_item())
        assert c.term == "20271"

    def test_term_empty(self) -> None:
        """terms 为空时 term 返回空串"""
        c = PolymasCourse.model_validate(_course_item())
        c.terms = []
        assert c.term == ""


class TestPolymasCourseManager:
    def test_user_detail_cached(self, mock_session: MagicMock) -> None:
        """会话级用户详情只请求 1 次（school_nid 连续取两次）"""
        mock_session.polymas_query.return_value = _user_detail_body()
        mgr = PolymasCourseManager(mock_session)
        assert mgr.school_nid == "oeL1v3eiRe"
        assert mgr.school_nid == "oeL1v3eiRe"
        assert mock_session.polymas_query.call_count == 1
        # 真实接口仅支持 POST（GET 返回 code=100000 系统异常，见 probe 实测）
        first_call = mock_session.polymas_query.call_args_list[0]
        assert "get-current-user-detail" in first_call.args[0]
        assert first_call.kwargs.get("method", "POST") == "POST"
        assert first_call.args[1] == {}

    def test_filter_hike_ai_course_only(self, mock_session: MagicMock) -> None:
        """只收 courseType==hikeAiCourse，shareCourse/mapCourse 剔除防重复"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            _course_list_body(
                [
                    _course_item(course_id=1, name="知到课", course_type="shareCourse"),
                    _course_item(course_id=2, name="AI课", course_type="mapCourse"),
                    _course_item(course_id=3, name="智慧课", course_type="hikeAiCourse"),
                ],
                total=3,
            ),
        ]
        courses = PolymasCourseManager(mock_session).get_course_list()
        assert [c.course_name for c in courses] == ["智慧课"]
        assert courses[0].course_id == "3"
        assert courses[0].class_id == "203843"

    def test_classlist_fallback(self, mock_session: MagicMock) -> None:
        """classId=null 的 hikeAiCourse → classList 兜底查一次"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            _course_list_body([_course_item(course_type="hikeAiCourse", class_id=None)], total=1),
            _class_list_body(),
        ]
        courses = PolymasCourseManager(mock_session).get_course_list()
        assert len(courses) == 1
        assert courses[0].class_id == "203843"
        # 第三次请求是 classList
        third_call = mock_session.polymas_query.call_args_list[2]
        assert "classList" in third_call.args[0]
        assert third_call.args[1] == {"courseId": "2036787923612635136", "term": "20271"}

    def test_classlist_empty_keeps_none(self, mock_session: MagicMock) -> None:
        """classList 返回空数组 → class_id 保持 None（不报错，播放时校验）"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            _course_list_body([_course_item(course_type="hikeAiCourse", class_id=None)], total=1),
            {"code": 200, "msg": "success", "data": []},
        ]
        courses = PolymasCourseManager(mock_session).get_course_list()
        assert courses[0].class_id is None

    def test_student_classes_used_before_classlist(self, mock_session: MagicMock) -> None:
        """PR #168 流程：顶层 classId 为空但 studentClasses 有值 → 直接取用，不打 classList"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            _course_list_body(
                [
                    _course_item(
                        course_type="hikeAiCourse",
                        class_id=None,
                        student_classes=[{"classId": "sc1", "name": "1班"}],
                    )
                ],
                total=1,
            ),
        ]
        courses = PolymasCourseManager(mock_session).get_course_list()
        assert len(courses) == 1
        assert courses[0].class_id == "sc1"
        # 只有 user-detail + 课程列表两次请求，无 classList
        assert mock_session.polymas_query.call_count == 2

    def test_pagination(self, mock_session: MagicMock) -> None:
        """total 超过单页 → 翻页拉全"""
        page1 = _course_list_body(
            [
                _course_item(course_type="hikeAiCourse", course_id=1 + 2036787923612635136),
                _course_item(course_type="hikeAiCourse", course_id=2 + 2036787923612635136),
            ],
            total=3,
        )
        page2 = _course_list_body(
            [_course_item(course_type="hikeAiCourse", course_id=3 + 2036787923612635136)], total=3
        )
        mock_session.polymas_query.side_effect = [_user_detail_body(), page1, page2]
        courses = PolymasCourseManager(mock_session).get_course_list()
        assert len(courses) == 3
        # 分页参数递增
        second_call = mock_session.polymas_query.call_args_list[2]
        assert second_call.args[1]["page"] == 2

    def test_query_body_carries_school_nid(self, mock_session: MagicMock) -> None:
        """queryStudentCourse 使用 schoolInfo.nid 作为 schoolId"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            _course_list_body([], total=0),
        ]
        PolymasCourseManager(mock_session).get_course_list()
        list_call = mock_session.polymas_query.call_args_list[1]
        assert list_call.args[1]["schoolId"] == "oeL1v3eiRe"

    def test_api_error_propagates(self, mock_session: MagicMock) -> None:
        """polymas_query 抛 ApiError → 直接传播（失败即停）"""
        mock_session.polymas_query.side_effect = [
            _user_detail_body(),
            ApiError(code=401, message="未登录"),
        ]
        with pytest.raises(ApiError):
            PolymasCourseManager(mock_session).get_course_list()


def _tree_file(
    node_id: int,
    title: str,
    oss_url: str | None = "https://oss.example.com/v.mp4",
    duration: int = 600,
) -> dict[str, Any]:
    """queryTree 视频 file 节点（结构照 probe walk 反推）"""
    ext = f'{{"ossUrl": "{oss_url}", "duration": {duration}}}' if oss_url is not None else "{}"
    return {"nodeId": node_id, "detail": {"classify": "file", "title": title, "ext": ext}, "children": None}


def _tree_folder(node_id: int, title: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    """queryTree 章节 folder 节点"""
    return {"nodeId": node_id, "detail": {"classify": "folder", "title": title}, "children": children}


def _tree_body(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"code": 200, "msg": "success", "data": nodes}


def _hike_course(class_id: str | None = "203843") -> PolymasCourse:
    """hikeAiCourse 条目（带 classId 与学期）"""
    return PolymasCourse.model_validate(_course_item(course_type="hikeAiCourse", class_id=class_id))


class TestResourceTree:
    """library 懒加载 + queryTree 资源树 + 视频节点过滤"""

    def test_library_folder_id_lazy_cached(self, mock_session: MagicMock) -> None:
        """library 懒加载：首次请求后缓存（course_id 维度），二次访问不再请求"""
        mock_session.polymas_query.return_value = {"code": 200, "msg": "success", "data": "ashq8p9iZT"}
        mgr = PolymasCourseManager(mock_session)
        course = _hike_course()
        assert mgr.library_folder_id(course) == "ashq8p9iZT"
        assert mgr.library_folder_id(course) == "ashq8p9iZT"
        assert mock_session.polymas_query.call_count == 1

    def test_library_get_with_params(self, mock_session: MagicMock) -> None:
        """findStudyLibraryByCourseId 走 GET + {courseId, term} query params"""
        mock_session.polymas_query.return_value = {"code": 200, "msg": "success", "data": "lib1"}
        mgr = PolymasCourseManager(mock_session)
        mgr.library_folder_id(_hike_course())
        call = mock_session.polymas_query.call_args_list[0]
        assert "findStudyLibraryByCourseId" in call.args[0]
        assert call.kwargs.get("method") == "GET"
        assert call.args[1] == {"courseId": "2036787923612635136", "term": "20271"}

    def test_get_resource_tree_body(self, mock_session: MagicMock) -> None:
        """queryTree POST body 携带 libraryFolderId/classId/courseId/term(int)"""
        mock_session.polymas_query.side_effect = [
            {"code": 200, "msg": "success", "data": "lib1"},
            _tree_body([]),
        ]
        mgr = PolymasCourseManager(mock_session)
        mgr.get_resource_tree(_hike_course())
        call = mock_session.polymas_query.call_args_list[1]
        assert "queryTree" in call.args[0]
        assert call.args[1] == {
            "libraryFolderId": "lib1",
            "classId": "203843",
            "courseId": "2036787923612635136",
            "term": 20271,
        }

    def test_get_resource_tree_returns_nodes(self, mock_session: MagicMock) -> None:
        """queryTree data 数组 → list[PolymasNode]"""
        mock_session.polymas_query.side_effect = [
            {"code": 200, "msg": "success", "data": "lib1"},
            _tree_body([_tree_folder(1, "第一章", [_tree_file(2, "视频1")])]),
        ]
        nodes = PolymasCourseManager(mock_session).get_resource_tree(_hike_course())
        assert isinstance(nodes[0], PolymasNode)
        assert nodes[0].title == "第一章"

    def test_tree_class_id_none_raises_without_request(self, mock_session: MagicMock) -> None:
        """classId 兜底后仍为 None → ZhsError 失败即停，不发任何请求"""
        mgr = PolymasCourseManager(mock_session)
        with pytest.raises(ZhsError, match="classId"):
            mgr.get_resource_tree(_hike_course(class_id=None))
        mock_session.polymas_query.assert_not_called()

    def test_term_empty_raises(self, mock_session: MagicMock) -> None:
        """terms 为空（term 无法确定）→ ZhsError 失败即停"""
        course = _hike_course()
        course.terms = []
        mgr = PolymasCourseManager(mock_session)
        with pytest.raises(ZhsError, match="term"):
            mgr.get_resource_tree(course)
        mock_session.polymas_query.assert_not_called()

    def test_get_video_nodes_filters_non_video(self, mock_session: MagicMock) -> None:
        """无 ossUrl 或 duration<=0 的 file 节点剔除"""
        tree = _tree_body(
            [
                _tree_folder(
                    1,
                    "第一章",
                    [
                        _tree_file(2, "好视频", duration=600),
                        _tree_file(3, "无地址", oss_url=None),
                        _tree_file(4, "零时长", duration=0),
                    ],
                )
            ]
        )
        mock_session.polymas_query.side_effect = [
            {"code": 200, "msg": "success", "data": "lib1"},
            tree,
        ]
        videos = PolymasCourseManager(mock_session).get_video_nodes(_hike_course())
        assert [v.resource_id for v in videos] == ["2"]

    def test_get_video_nodes_caches_library(self, mock_session: MagicMock) -> None:
        """get_video_nodes 两次调用（不同调用间）library 只请求一次"""
        tree = _tree_body([_tree_folder(1, "第一章", [_tree_file(2, "视频1")])])
        mock_session.polymas_query.side_effect = [
            {"code": 200, "msg": "success", "data": "lib1"},
            tree,
            tree,
        ]
        mgr = PolymasCourseManager(mock_session)
        course = _hike_course()
        mgr.get_video_nodes(course)
        mgr.get_video_nodes(course)
        assert mock_session.polymas_query.call_count == 3

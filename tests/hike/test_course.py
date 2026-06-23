"""Task 4.2 — hike/course.py TDD"""

from unittest.mock import MagicMock

import pytest

from zhs.hike.course import HikeCourseManager
from zhs.session import ZhsSession


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock(spec=ZhsSession)
    session.uuid = "test-uuid-123"
    session.urls = MagicMock()
    session.urls.hike = "https://hike.zhihuishu.com"
    session.crypto = MagicMock()
    session.crypto.hike_salt = "o6xpt3b#Qy$Z"
    return session


class TestGetCourseList:
    """get_course_list 返回课程列表"""

    def test_returns_hike_courses(self, mock_session: MagicMock) -> None:
        """API 返回课程列表，正确解析"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "result": {
                "startInngcourseList": [
                    {"courseId": 100, "courseName": "Hike 课程1"},
                    {"courseId": 200, "courseName": "Hike 课程2"},
                ]
            },
        }
        manager = HikeCourseManager(mock_session)
        courses = manager.get_course_list()
        assert len(courses) == 2
        assert courses[0].course_id == 100
        assert courses[1].course_name == "Hike 课程2"

    def test_empty_course_list(self, mock_session: MagicMock) -> None:
        """API 返回空列表"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "result": {"startInngcourseList": None},
        }
        manager = HikeCourseManager(mock_session)
        courses = manager.get_course_list()
        assert courses == []

    def test_api_url_and_params(self, mock_session: MagicMock) -> None:
        """验证 API 调用参数"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "result": {"startInngcourseList": []},
        }
        manager = HikeCourseManager(mock_session)
        manager.get_course_list()
        mock_session.hike_query.assert_called_once()
        call_args = mock_session.hike_query.call_args
        url = call_args[0][0]
        assert "getMyCourseList" in url
        params = call_args[0][1]
        assert "uuid" in params
        assert params["uuid"] == "test-uuid-123"


class TestGetContext:
    """get_context 返回资源树"""

    def test_returns_resource_tree(self, mock_session: MagicMock) -> None:
        """获取课程资源树"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "rt": [
                {
                    "id": 1,
                    "name": "第一章",
                    "childList": [
                        {"id": 2, "name": "视频1", "dataType": 3, "totalTime": 600},
                    ],
                }
            ],
        }
        manager = HikeCourseManager(mock_session)
        root = manager.get_context("100")
        assert len(root) == 1
        assert root[0].name == "第一章"
        assert root[0].child_list is not None
        assert root[0].child_list[0].data_type == 3

    def test_caches_context(self, mock_session: MagicMock) -> None:
        """重复调用使用缓存"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "rt": [{"id": 1, "name": "根"}],
        }
        manager = HikeCourseManager(mock_session)
        manager.get_context("100")
        manager.get_context("100")
        # 只调用一次 hike_query（第二次用缓存）
        assert mock_session.hike_query.call_count == 1

    def test_force_refresh(self, mock_session: MagicMock) -> None:
        """force=True 强制刷新"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "rt": [{"id": 1, "name": "根"}],
        }
        manager = HikeCourseManager(mock_session)
        manager.get_context("100")
        manager.get_context("100", force=True)
        assert mock_session.hike_query.call_count == 2


class TestQueryResourceMenuTree:
    """query_resource_menu_tree 返回资源树"""

    def test_api_url_and_params(self, mock_session: MagicMock) -> None:
        """验证 API 调用参数"""
        mock_session.hike_query.return_value = {
            "status": 200,
            "rt": [],
        }
        manager = HikeCourseManager(mock_session)
        manager.query_resource_menu_tree("100")
        call_args = mock_session.hike_query.call_args
        url = call_args[0][0]
        assert "queryResourceMenuTree" in url
        params = call_args[0][1]
        assert params["courseId"] == "100"

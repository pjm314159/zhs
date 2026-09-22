"""Zhidao course 测试

Task 3.2 — zhidao/course.py
TDD 步骤:
1. get_course_list() 返回课程列表
2. get_context() 返回 ZhidaoContext
3. get_context() 已看完课程 → end_threshold 检查
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.models import ZhidaoContext


@pytest.fixture
def mock_config() -> AppConfig:
    """带测试配置的 AppConfig"""
    return AppConfig()


@pytest.fixture
def mock_session(mock_config: AppConfig) -> Iterator[ZhsSession]:
    """带 respx mock 的 session"""
    with respx.mock:
        session = ZhsSession(mock_config)
        yield session


def _make_course_list_response(courses: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """构造课程列表 API 响应"""
    if courses is None:
        courses = [
            {
                "recruitAndCourseId": "ABC123_456",
                "courseName": "马克思主义基本原理",
                "courseInfo": {"courseId": 456, "name": "马克思主义基本原理", "enName": "Marxism"},
                "recruitId": 789,
            }
        ]
    return {"code": 200, "result": {"courseOpenDtos": courses, "totalCount": len(courses)}}


def _make_query_course_response() -> dict[str, Any]:
    """构造 queryCourse API 响应"""
    return {
        "code": 0,
        "data": {
            "recruitId": 789,
            "courseInfo": {"courseId": 456, "name": "马克思主义基本原理"},
        },
    }


def _make_video_list_response() -> dict[str, Any]:
    """构造 videolist API 响应"""
    return {
        "code": 0,
        "data": {
            "courseId": 456,
            "videoChapterDtos": [
                {
                    "id": 1,
                    "name": "第一章",
                    "videoLessons": [
                        {
                            "id": 10,
                            "name": "1.1 导论",
                            "videoId": 100,
                            "videoSmallLessons": [
                                {
                                    "videoId": 100,
                                    "id": 200,
                                    "name": "1.1 导论",
                                    "lessonId": 10,
                                    "videoSec": 1800,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    }


def _make_study_info_response() -> dict[str, Any]:
    """构造 queryStuyInfo API 响应"""
    return {
        "code": 0,
        "data": {
            "lv": {"200": {"watchState": 0, "studyTotalTime": 0}},
            "lesson": {"10": {"watchState": 0, "studyTotalTime": 0}},
        },
    }


class TestGetCourseList:
    """get_course_list 测试"""

    def test_returns_course_list(self, mock_session: ZhsSession) -> None:
        """get_course_list() 返回课程列表"""
        respx.post(
            "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"
        ).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)
        courses = manager.get_course_list()
        assert len(courses) == 1
        assert courses[0].secret == "ABC123_456"
        assert courses[0].course_name == "马克思主义基本原理"

    def test_empty_course_list(self, mock_session: ZhsSession) -> None:
        """空课程列表"""
        respx.post(
            "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"
        ).mock(return_value=httpx.Response(200, json=_make_course_list_response([])))
        manager = ZhidaoCourseManager(mock_session)
        courses = manager.get_course_list()
        assert courses == []

    def test_course_list_cached(self, mock_session: ZhsSession) -> None:
        """get_course_list 默认走实例缓存，只请求一次"""
        route = respx.post(
            "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"
        ).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)

        first = manager.get_course_list()
        second = manager.get_course_list()

        assert first == second
        assert route.call_count == 1

    def test_course_list_force_refresh(self, mock_session: ZhsSession) -> None:
        """force=True 强制刷新，重新请求"""
        route = respx.post(
            "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"
        ).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)

        manager.get_course_list()
        manager.get_course_list(force=True)

        assert route.call_count == 2

    def test_pagination(self, mock_session: ZhsSession) -> None:
        """分页获取课程"""
        page1 = [{"recruitAndCourseId": "A1", "courseName": "课程1"}]
        page2 = [{"recruitAndCourseId": "A2", "courseName": "课程2"}]

        route = respx.post(
            "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"
        )

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"code": 200, "result": {"courseOpenDtos": page1, "totalCount": 7}})
            else:
                return httpx.Response(200, json={"code": 200, "result": {"courseOpenDtos": page2, "totalCount": 7}})

        route.mock(side_effect=side_effect)
        manager = ZhidaoCourseManager(mock_session)
        courses = manager.get_course_list()
        assert len(courses) == 2


class TestFindCourse:
    """find_course 测试"""

    URL = "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo"

    def test_matches_by_course_id(self, mock_session: ZhsSession) -> None:
        """按数字 courseId 匹配（courseInfo.courseId 回退）"""
        respx.post(self.URL).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)

        course = manager.find_course(456)
        assert course is not None
        assert course.secret == "ABC123_456"

    def test_returns_none_when_not_found(self, mock_session: ZhsSession) -> None:
        """未命中返回 None"""
        respx.post(self.URL).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)

        assert manager.find_course(999) is None

    def test_non_positive_returns_none_without_request(self, mock_session: ZhsSession) -> None:
        """courseId <= 0 直接返回 None，不触发任何请求"""
        route = respx.post(self.URL).mock(return_value=httpx.Response(200, json=_make_course_list_response()))
        manager = ZhidaoCourseManager(mock_session)

        assert manager.find_course(0) is None
        assert route.call_count == 0

    def test_require_recruit_id_skips_courses_without_recruit_id(self, mock_session: ZhsSession) -> None:
        """require_recruit_id=True 时跳过没有 recruitId 的课程"""
        respx.post(self.URL).mock(
            return_value=httpx.Response(
                200,
                json=_make_course_list_response(
                    [
                        {
                            "recruitAndCourseId": "A1",
                            "courseName": "无 recruitId 课程",
                            "courseInfo": {"courseId": 456, "name": "无 recruitId 课程"},
                        }
                    ]
                ),
            )
        )
        manager = ZhidaoCourseManager(mock_session)

        assert manager.find_course(456, require_recruit_id=True) is None
        assert manager.find_course(456) is not None


class TestGetContext:
    """get_context 测试"""

    def test_returns_zhidao_context(self, mock_session: ZhsSession) -> None:
        """get_context() 返回 ZhidaoContext"""
        # Mock gologin
        respx.get("https://studyservice-api.zhihuishu.com/login/gologin").mock(
            return_value=httpx.Response(200, text="<html>ok</html>")
        )
        # Mock queryCourse
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_make_query_course_response())
        )
        # Mock videolist
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(200, json=_make_video_list_response())
        )
        # Mock queryStuyInfo
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryStuyInfo").mock(
            return_value=httpx.Response(200, json=_make_study_info_response())
        )
        # Mock queryUserRecruitIdLastVideoId
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryUserRecruitIdLastVideoId").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )

        manager = ZhidaoCourseManager(mock_session)
        ctx = manager.get_context("ABC123_456")
        assert isinstance(ctx, ZhidaoContext)
        assert ctx.course.secret == "ABC123_456"
        assert len(ctx.chapters) == 1
        assert 100 in ctx.videos

    def test_single_video_lesson_creates_small_lesson(self, mock_session: ZhsSession) -> None:
        """单视频课时（有 videoId 但无 videoSmallLessons）自动构造子视频"""
        respx.get("https://studyservice-api.zhihuishu.com/login/gologin").mock(
            return_value=httpx.Response(200, text="<html>ok</html>")
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_make_query_course_response())
        )
        # 课时有 videoId 但没有 videoSmallLessons
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "courseId": 456,
                        "videoChapterDtos": [
                            {
                                "id": 1,
                                "name": "第一章",
                                "videoLessons": [
                                    {
                                        "id": 10,
                                        "name": "1.1 导论",
                                        "videoId": 100,
                                        # 没有 videoSmallLessons
                                    }
                                ],
                            }
                        ],
                    },
                },
            )
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryStuyInfo").mock(
            return_value=httpx.Response(200, json=_make_study_info_response())
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryUserRecruitIdLastVideoId").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )

        manager = ZhidaoCourseManager(mock_session)
        ctx = manager.get_context("ABC123_456")
        # 应自动构造子视频
        assert 100 in ctx.videos
        assert ctx.videos[100].lesson_id == 10  # lessonId = 原课时 id

    def test_already_watched_course(self, mock_session: ZhsSession) -> None:
        """已看完课程 → end_threshold 检查（watch_state=1）"""
        respx.get("https://studyservice-api.zhihuishu.com/login/gologin").mock(
            return_value=httpx.Response(200, text="<html>ok</html>")
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_make_query_course_response())
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(200, json=_make_video_list_response())
        )
        # watchState=1 表示已看完
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryStuyInfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "lv": {"200": {"watchState": 1, "studyTotalTime": 1800}},
                        "lesson": {"10": {"watchState": 1, "studyTotalTime": 1800}},
                    },
                },
            )
        )
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/learning/queryUserRecruitIdLastVideoId").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )

        manager = ZhidaoCourseManager(mock_session)
        ctx = manager.get_context("ABC123_456")
        # 已看完的视频 watch_state 应为 1
        assert ctx.videos[100].watch_state == 1

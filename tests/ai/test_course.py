"""Task 6.4 — ai/course.py TDD"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.course import AiCourseManager
from zhs.ai.models import (
    AiCourseInfo,
    ExamInfo,
    Resource,
    ResourceDetail,
)
from zhs.config import AIConfig


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.ai_key = b"hw2fdlwcj4cs1mx7"
    session.crypto.key_bytes = MagicMock(return_value=b"hw2fdlwcj4cs1mx7")
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.base = "https://onlineservice-api.zhihuishu.com"
    session.speed = 1.25
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """AI 配置"""
    return AIConfig(api_key="test-key", model="gpt-4o-mini")


@pytest.fixture
def manager(mock_session: MagicMock) -> AiCourseManager:
    """创建 AiCourseManager 实例"""
    return AiCourseManager(mock_session)


class TestGetKnowledgePoints:
    """获取知识点"""

    def test_returns_course_info(self, manager: AiCourseManager) -> None:
        """返回 AiCourseInfo"""
        mock_data = {
            "data": {
                "courseName": "Python入门",
                "cakeThemeList": [
                    {
                        "themeName": "第一章",
                        "knowledgeList": [
                            {"knowledgeId": 1, "knowledgeName": "变量", "studyProgress": 0},
                        ],
                    }
                ],
            }
        }
        with patch.object(manager, "_ai_query", return_value=mock_data):
            result = manager.get_knowledge_points(100, 200)
            assert isinstance(result, AiCourseInfo)
            assert result.course_name == "Python入门"
            assert len(result.cake_theme_list) == 1


class TestListKnowledgeResources:
    """获取知识点资源列表"""

    def test_returns_resource_list(self, manager: AiCourseManager) -> None:
        """返回资源列表"""
        mock_data = {
            "data": {
                "resourceList": [
                    {
                        "studyStatus": 0,
                        "resourcesDetail": {
                            "resourcesUid": 1,
                            "resourcesName": "课件1",
                            "resourcesType": 2,
                            "resourcesDistributeType": 1,
                        },
                    }
                ]
            }
        }
        with patch.object(manager, "_ai_query", return_value=mock_data):
            result = manager.list_knowledge_resources(100, 200, 1)
            assert len(result) == 1
            assert result[0].resources_detail.resources_name == "课件1"


class TestCompleteResource:
    """完成资源"""

    def test_calls_api(self, manager: AiCourseManager) -> None:
        """调用完成资源 API"""
        with patch.object(manager, "_ai_query", return_value={"data": {}}) as mock_query:
            manager.complete_resource(100, 200, 1, 10)
            mock_query.assert_called_once()
            call_data = mock_query.call_args[0][1]
            assert call_data["resourcesUid"] == 10


class TestResourceTypeRouting:
    """资源类型路由"""

    def test_text_resource_completes(self, manager: AiCourseManager) -> None:
        """(2,1) 文本 → complete_resource"""
        detail = ResourceDetail(resources_uid=1, resources_name="文本", resources_type=2, resources_distribute_type=1)
        resource = Resource(study_status=0, resources_detail=detail)
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource)
            mock_complete.assert_called_once()

    def test_ppt_resource_completes_and_collects_url(self, manager: AiCourseManager) -> None:
        """(1,4) PPT → complete_resource + 收集 URL"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="PPT",
            resources_type=1,
            resources_distribute_type=4,
            resources_url="https://example.com/ppt.pptx",
        )
        resource = Resource(study_status=0, resources_detail=detail)
        ppts: list[dict[str, str]] = []
        with patch.object(manager, "complete_resource"):
            manager._process_resource(100, 200, 1, resource, ppts=ppts)
            assert len(ppts) == 1
            assert ppts[0]["url"] == "https://example.com/ppt.pptx"

    def test_video_resource_plays_video(self, manager: AiCourseManager) -> None:
        """(1,3) 视频 → play_video"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="视频",
            resources_type=1,
            resources_distribute_type=3,
            resources_file_id=500,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        with patch.object(manager, "play_video") as mock_play:
            manager._process_resource(100, 200, 1, resource)
            mock_play.assert_called_once()

    def test_course_video_plays_video(self, manager: AiCourseManager) -> None:
        """(2,2) 课程视频 → play_video"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="课程视频",
            resources_type=2,
            resources_distribute_type=2,
            resources_file_id=600,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        with patch.object(manager, "play_video") as mock_play:
            manager._process_resource(100, 200, 1, resource)
            mock_play.assert_called_once()

    def test_other_resource_completes(self, manager: AiCourseManager) -> None:
        """其他类型 → complete_resource"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="其他",
            resources_type=3,
            resources_distribute_type=5,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource)
            mock_complete.assert_called_once()

    def test_completed_ppt_still_collects_url(self, manager: AiCourseManager) -> None:
        """已完成的 PPT 仍收集 URL"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="PPT",
            resources_type=1,
            resources_distribute_type=4,
            resources_url="https://example.com/ppt.pptx",
        )
        resource = Resource(study_status=1, resources_detail=detail)
        ppts: list[dict[str, str]] = []
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource, ppts=ppts)
            mock_complete.assert_not_called()  # 已完成不调用
            assert len(ppts) == 1  # 但仍收集 URL


class TestExamLoop:
    """考试循环"""

    def test_mastery_score_above_90_exits(self, manager: AiCourseManager) -> None:
        """mastery_score > 90 → 退出"""
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=95)
        with patch.object(manager, "query_ai_exam", return_value=exam):
            result = manager._should_take_exam(exam, tried=0, no_exam=False)
            assert result is False

    def test_mastery_score_below_30_tried_over_4_gives_up(self, manager: AiCourseManager) -> None:
        """mastery_score < 30 且 tried > 4 → 放弃"""
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=20)
        result = manager._should_take_exam(exam, tried=5, no_exam=False)
        assert result is False

    def test_no_exam_flag_skips(self, manager: AiCourseManager) -> None:
        """no_exam=True 跳过考试"""
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=50)
        result = manager._should_take_exam(exam, tried=0, no_exam=True)
        assert result is False

    def test_should_take_exam(self, manager: AiCourseManager) -> None:
        """mastery_score 30-90 且 tried <= 4 → 应考试"""
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=50)
        result = manager._should_take_exam(exam, tried=0, no_exam=False)
        assert result is True

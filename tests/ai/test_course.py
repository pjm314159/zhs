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
from zhs.config import AIConfig, HomeworkConfig


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.ai_key = b"hw2fdlwcj4cs1mx7"
    session.crypto.key_bytes = MagicMock(return_value=b"hw2fdlwcj4cs1mx7")
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.ai_task = "https://kg-run-student.zhihuishu.com"
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


class TestGetExamTasks:
    """获取考试任务列表（taskList）"""

    def test_returns_task_list(self, manager: AiCourseManager) -> None:
        """返回未完成的考试任务列表"""
        mock_data = {
            "code": 200,
            "data": [
                {
                    "id": 416884,
                    "taskName": "大一期末作业",
                    "courseId": "7123456789012345678",
                    "classId": 203843,
                    "examId": 3056052,
                    "examTestId": 2786542,
                    "examPaperId": 270661609,
                    "taskType": 1,
                    "status": 1,
                }
            ],
        }
        with patch.object(manager._session, "ai_task_query", return_value=mock_data) as mock_query:
            tasks = manager.get_exam_tasks("7123456789012345678")
            assert len(tasks) == 1
            assert tasks[0]["examTestId"] == 2786542
            assert tasks[0]["examPaperId"] == 270661609
            mock_query.assert_called_once()

    def test_filters_unfinished_tasks(self, manager: AiCourseManager) -> None:
        """只返回 taskType=1 的任务（请求参数 status=0 已筛选未完成，响应中 status=1 也是未完成）"""
        mock_data = {
            "code": 200,
            "data": [
                {"examTestId": 1, "examPaperId": 1, "taskType": 1, "status": 1},
                {"examTestId": 2, "examPaperId": 2, "taskType": 4, "status": 0},
            ],
        }
        with patch.object(manager._session, "ai_task_query", return_value=mock_data):
            tasks = manager.get_exam_tasks("123")
            assert len(tasks) == 1
            assert tasks[0]["examTestId"] == 1

    def test_empty_data(self, manager: AiCourseManager) -> None:
        """空数据返回空列表"""
        mock_data = {"code": 200, "data": []}
        with patch.object(manager._session, "ai_task_query", return_value=mock_data):
            tasks = manager.get_exam_tasks("123")
            assert tasks == []

    def test_error_returns_empty(self, manager: AiCourseManager) -> None:
        """异常时返回空列表"""
        with patch.object(manager._session, "ai_task_query", side_effect=Exception("network error")):
            tasks = manager.get_exam_tasks("123")
            assert tasks == []


class TestResourceTypeRouting:
    """资源类型路由"""

    def test_text_resource_completes(self, manager: AiCourseManager) -> None:
        """(2,1) 文本 → complete_resource"""
        detail = ResourceDetail(resources_uid=1, resources_name="文本", resources_type=2, resources_distribute_type=1)
        resource = Resource(study_status=0, resources_detail=detail)
        video_player = MagicMock()
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource, video_player)
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
        video_player = MagicMock()
        with patch.object(manager, "complete_resource"):
            manager._process_resource(100, 200, 1, resource, video_player, ppts=ppts)
            assert len(ppts) == 1
            assert ppts[0]["url"] == "https://example.com/ppt.pptx"

    def test_video_resource_plays_video(self, manager: AiCourseManager) -> None:
        """(1,3) 视频 → video_player.play_video"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="视频",
            resources_type=1,
            resources_distribute_type=3,
            resources_file_id=500,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        video_player = MagicMock()
        manager._process_resource(100, 200, 1, resource, video_player)
        video_player.play_video.assert_called_once()

    def test_course_video_plays_video(self, manager: AiCourseManager) -> None:
        """(2,2) 课程视频 → video_player.play_video"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="课程视频",
            resources_type=2,
            resources_distribute_type=2,
            resources_file_id=600,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        video_player = MagicMock()
        manager._process_resource(100, 200, 1, resource, video_player)
        video_player.play_video.assert_called_once()

    def test_other_resource_completes(self, manager: AiCourseManager) -> None:
        """其他类型 → complete_resource"""
        detail = ResourceDetail(
            resources_uid=1,
            resources_name="其他",
            resources_type=3,
            resources_distribute_type=5,
        )
        resource = Resource(study_status=0, resources_detail=detail)
        video_player = MagicMock()
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource, video_player)
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
        video_player = MagicMock()
        with patch.object(manager, "complete_resource") as mock_complete:
            manager._process_resource(100, 200, 1, resource, video_player, ppts=ppts)
            mock_complete.assert_not_called()  # 已完成不调用
            assert len(ppts) == 1  # 但仍收集 URL


class TestHomeworkLoop:
    """作业循环"""

    def test_mastery_score_above_90_exits(self, manager: AiCourseManager) -> None:
        """mastery_score > 90 → 退出"""
        homework_config = HomeworkConfig(ai_homework_threshold=90)
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=95)
        result = manager._should_do_homework(exam, tried=0, no_homework=False, homework_config=homework_config)
        assert result is False

    def test_mastery_score_below_30_tried_over_4_gives_up(self, manager: AiCourseManager) -> None:
        """mastery_score < 30 且 tried > 4 → 放弃"""
        homework_config = HomeworkConfig(ai_homework_threshold=90)
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=20)
        result = manager._should_do_homework(exam, tried=5, no_homework=False, homework_config=homework_config)
        assert result is False

    def test_no_homework_flag_skips(self, manager: AiCourseManager) -> None:
        """no_homework=True 跳过作业"""
        homework_config = HomeworkConfig(ai_homework_threshold=90)
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=50)
        result = manager._should_do_homework(exam, tried=0, no_homework=True, homework_config=homework_config)
        assert result is False

    def test_should_do_homework(self, manager: AiCourseManager) -> None:
        """mastery_score 30-90 且 tried <= 4 → 应做作业"""
        homework_config = HomeworkConfig(ai_homework_threshold=90)
        exam = ExamInfo(exam_test_id=1, paper_id=2, mastery_score=50)
        result = manager._should_do_homework(exam, tried=0, no_homework=False, homework_config=homework_config)
        assert result is True

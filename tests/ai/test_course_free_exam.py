"""阶段 3 — AI 课程作业免考知识点跳过配置"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.course import AiCourseManager
from zhs.ai.models import AiCourseInfo, KnowledgePoint, KnowledgeTarget, Theme
from zhs.config import AIConfig, HomeworkConfig


@pytest.fixture
def reporter() -> MagicMock:
    """mock 报告器，便于断言跳过提示"""
    return MagicMock()


@pytest.fixture
def manager(reporter: MagicMock) -> AiCourseManager:
    """构造不触发真实请求的管理器"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.urls = MagicMock()
    session.speed = 1.25
    return AiCourseManager(session, reporter=reporter)


@pytest.fixture
def course_info() -> AiCourseInfo:
    """一个普通知识点 + 一个免考知识点"""
    return AiCourseInfo(
        course_name="测试课程",
        cake_theme_list=[
            Theme(
                theme_name="主题A",
                knowledge_list=[
                    KnowledgePoint(knowledge_id=1, knowledge_name="普通知识点", free_exam=0),
                    KnowledgePoint(knowledge_id=2, knowledge_name="免考知识点", free_exam=1),
                ],
            )
        ],
    )


class TestShouldSkipAiFreeExam:
    """跳过谓词"""

    @pytest.mark.parametrize("free_exam", [0, 1])
    def test_disabled_never_skips(self, manager: AiCourseManager, free_exam: int) -> None:
        """关闭开关时任何知识点都不跳过"""
        target = KnowledgeTarget("主题A", KnowledgePoint(knowledge_id=1, knowledge_name="x", free_exam=free_exam))
        assert manager._should_skip_ai_free_exam(target, HomeworkConfig(skip_ai_free_exam=False)) is False

    def test_enabled_skips_only_free_exam(self, manager: AiCourseManager) -> None:
        """开启开关时只跳过 freeExam=1"""
        cfg = HomeworkConfig(skip_ai_free_exam=True)
        free = KnowledgeTarget("主题A", KnowledgePoint(knowledge_id=2, knowledge_name="免考", free_exam=1))
        normal = KnowledgeTarget("主题A", KnowledgePoint(knowledge_id=1, knowledge_name="普通", free_exam=0))
        assert manager._should_skip_ai_free_exam(free, cfg) is True
        assert manager._should_skip_ai_free_exam(normal, cfg) is False


class TestRunCourseSkipAiFreeExam:
    """统一循环里的跳过行为"""

    @staticmethod
    def _skip_messages(reporter: MagicMock) -> list[str]:
        return [str(call.args[0]) for call in reporter.tree_print.call_args_list]

    def test_scan_mode_skips_free_exam_by_default(
        self, manager: AiCourseManager, course_info: AiCourseInfo, reporter: MagicMock
    ) -> None:
        """扫描模式默认只处理非免考知识点，并打印跳过提示"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(100, 200, AIConfig(api_key="k"), HomeworkConfig(), no_homework=False)

        mock_hw.assert_called_once()
        assert mock_hw.call_args[0][2].knowledge.knowledge_id == 1
        assert any("跳过(免考)" in msg for msg in self._skip_messages(reporter))

    def test_scan_mode_keeps_free_exam_when_disabled(
        self, manager: AiCourseManager, course_info: AiCourseInfo, reporter: MagicMock
    ) -> None:
        """关闭开关后两个知识点都进入作业流程"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(
                100, 200, AIConfig(api_key="k"), HomeworkConfig(skip_ai_free_exam=False), no_homework=False
            )

        assert [call.args[2].knowledge.knowledge_id for call in mock_hw.call_args_list] == [1, 2]
        assert not any("跳过(免考)" in msg for msg in self._skip_messages(reporter))

    def test_direct_mode_skips_free_exam(
        self, manager: AiCourseManager, course_info: AiCourseInfo, reporter: MagicMock
    ) -> None:
        """直接模式命中免考知识点时同样跳过"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(100, 200, AIConfig(api_key="k"), HomeworkConfig(), no_homework=False, node_uid=2)

        mock_hw.assert_not_called()
        assert any("跳过(免考)" in msg for msg in self._skip_messages(reporter))

    def test_direct_mode_keeps_free_exam_when_disabled(
        self, manager: AiCourseManager, course_info: AiCourseInfo
    ) -> None:
        """关闭开关后直接模式仍处理免考知识点"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(
                100,
                200,
                AIConfig(api_key="k"),
                HomeworkConfig(skip_ai_free_exam=False),
                no_homework=False,
                node_uid=2,
            )

        mock_hw.assert_called_once()
        assert mock_hw.call_args[0][2].knowledge.knowledge_id == 2

    def test_play_mode_ignores_free_exam(
        self, manager: AiCourseManager, course_info: AiCourseInfo, reporter: MagicMock
    ) -> None:
        """play 模式不受免考开关影响"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_play_only") as mock_play,
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(100, 200, AIConfig(api_key="k"), HomeworkConfig(), no_homework=True)

        assert [call.args[2].knowledge_id for call in mock_play.call_args_list] == [1, 2]
        mock_hw.assert_not_called()
        assert not any("跳过(免考)" in msg for msg in self._skip_messages(reporter))

    def test_skipped_free_exam_does_not_query_homework(
        self, manager: AiCourseManager, course_info: AiCourseInfo
    ) -> None:
        """跳过发生在作业查询之前，不产生额外请求与 LLM 调用"""
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "query_homework") as mock_query,
            patch.object(manager, "_run_homework_only") as mock_hw,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(100, 200, AIConfig(api_key="k"), HomeworkConfig(), no_homework=False, node_uid=2)

        mock_query.assert_not_called()
        mock_hw.assert_not_called()

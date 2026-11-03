"""AI 课程免考知识点跳过与直接模式主题反查

覆盖：
- homework 模式下 freeExam=1 的知识点跳过（扫描模式 / 直接模式）
- play 模式不受免考标记影响，仍需完成资源任务
- _find_theme_name 按知识点反查所属主题（直接模式 theme 为 None 的修复）
"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.course import AiCourseManager
from zhs.ai.models import AiCourseInfo, KnowledgePoint, Theme
from zhs.config import AIConfig, HomeworkConfig, VideoConfig


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
def reporter() -> MagicMock:
    """进度输出替身，避免测试污染终端"""
    return MagicMock()


@pytest.fixture
def manager(mock_session: MagicMock, reporter: MagicMock) -> AiCourseManager:
    """创建 AiCourseManager 实例"""
    return AiCourseManager(mock_session, reporter)


def build_course(*knowledge_points: KnowledgePoint, theme_name: str = "主题1") -> AiCourseInfo:
    """构造只含一个主题的课程信息"""
    return AiCourseInfo(
        course_name="测试课程",
        cake_theme_list=[Theme(theme_name=theme_name, knowledge_list=list(knowledge_points))],
    )


class TestFreeExamSkip:
    """免考知识点在作业模式下跳过"""

    def test_scan_mode_skips_free_exam_knowledge(self, manager: AiCourseManager) -> None:
        """扫描模式下免考知识点不进入作业流程"""
        course_info = build_course(
            KnowledgePoint(knowledge_id=1, knowledge_name="免考点", free_exam=1),
            KnowledgePoint(knowledge_id=2, knowledge_name="必考点", free_exam=0),
        )
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
                HomeworkConfig(),
                video_config=VideoConfig(),
            )

        mock_hw.assert_called_once()
        assert mock_hw.call_args.args[2].knowledge_name == "必考点"

    def test_scan_mode_all_free_exam_skips_everything(self, manager: AiCourseManager) -> None:
        """全部免考时不产生任何作业调用"""
        course_info = build_course(
            KnowledgePoint(knowledge_id=1, knowledge_name="免考点1", free_exam=1),
            KnowledgePoint(knowledge_id=2, knowledge_name="免考点2", free_exam=1),
        )
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
                HomeworkConfig(),
                video_config=VideoConfig(),
            )

        mock_hw.assert_not_called()

    def test_direct_mode_skips_free_exam_knowledge(self, manager: AiCourseManager) -> None:
        """直接模式下免考知识点同样跳过"""
        course_info = build_course(KnowledgePoint(knowledge_id=7, knowledge_name="免考点", free_exam=1))
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_homework_only") as mock_hw,
        ):
            manager.run_course(
                100,
                200,
                AIConfig(api_key="k"),
                HomeworkConfig(),
                node_uid=7,
            )

        mock_hw.assert_not_called()

    def test_play_mode_still_processes_free_exam_knowledge(self, manager: AiCourseManager) -> None:
        """play 模式下免考知识点仍需完成资源任务"""
        course_info = build_course(KnowledgePoint(knowledge_id=1, knowledge_name="免考点", free_exam=1))
        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "_run_play_only") as mock_play,
            patch("zhs.ai.course.time.sleep"),
            patch("zhs.ai.course.AiVideoPlayer"),
        ):
            manager.run_course(
                100,
                200,
                AIConfig(api_key="k"),
                HomeworkConfig(),
                video_config=VideoConfig(),
                no_homework=True,
            )

        mock_play.assert_called_once()


class TestFindThemeName:
    """直接模式下的主题反查"""

    def test_returns_matched_theme_name(self, manager: AiCourseManager) -> None:
        """命中知识点时返回所属主题名"""
        course_info = build_course(KnowledgePoint(knowledge_id=5, knowledge_name="A"), theme_name="第一章")
        knowledge = course_info.cake_theme_list[0].knowledge_list[0]

        assert manager._find_theme_name(course_info, knowledge) == "第一章"

    def test_returns_empty_when_knowledge_missing(self, manager: AiCourseManager) -> None:
        """知识点不在课程内时返回空字符串"""
        course_info = build_course(KnowledgePoint(knowledge_id=5, knowledge_name="A"))
        other = KnowledgePoint(knowledge_id=99, knowledge_name="不存在")

        assert manager._find_theme_name(course_info, other) == ""

    def test_searches_across_multiple_themes(self, manager: AiCourseManager) -> None:
        """跨多个主题查找"""
        course_info = AiCourseInfo(
            course_name="测试课程",
            cake_theme_list=[
                Theme(theme_name="主题甲", knowledge_list=[KnowledgePoint(knowledge_id=11, knowledge_name="KP1")]),
                Theme(theme_name="主题乙", knowledge_list=[KnowledgePoint(knowledge_id=12, knowledge_name="KP2")]),
            ],
        )
        knowledge = course_info.cake_theme_list[1].knowledge_list[0]

        assert manager._find_theme_name(course_info, knowledge) == "主题乙"

    def test_direct_mode_op_extra_uses_resolved_theme(self, manager: AiCourseManager) -> None:
        """直接模式作业上下文中的 theme 取反查结果而非空值"""
        course_info = AiCourseInfo(
            course_name="测试课程",
            cake_theme_list=[
                Theme(theme_name="主题甲", knowledge_list=[KnowledgePoint(knowledge_id=11, knowledge_name="KP1")]),
                Theme(theme_name="主题乙", knowledge_list=[KnowledgePoint(knowledge_id=12, knowledge_name="KP2")]),
            ],
        )
        # 首轮未达标（进入作答），次轮达标（跳出循环）
        exam_todo = MagicMock(paper_id=9, exam_test_id=8, mastery_score=0)
        exam_done = MagicMock(paper_id=9, exam_test_id=8, mastery_score=100)

        with (
            patch.object(manager, "get_knowledge_points", return_value=course_info),
            patch.object(manager, "query_homework", side_effect=[exam_todo, exam_done]),
            patch.object(manager, "_collect_completed_ppts"),
            patch("zhs.ai.homework.HomeworkCtx") as mock_ctx,
            patch("zhs.ai.course.time.sleep"),
        ):
            mock_ctx.return_value.start.return_value = (False, 0, 6)
            manager.run_course(
                100,
                200,
                AIConfig(api_key="k"),
                HomeworkConfig(),
                node_uid=12,
            )

        op_extra = mock_ctx.call_args.kwargs["op_extra"]
        assert op_extra["theme"] == "主题乙"
        assert op_extra["knowledgePoint"] == "KP2"

"""cli/services/exam_service.py 单元测试

覆盖 run_ai_exam。
"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.services.exam_service import run_ai_exam


def _make_config() -> MagicMock:
    """创建 mock 配置"""
    config = MagicMock()
    config.ai = MagicMock()
    config.exam = MagicMock()
    return config


class TestRunAiExam:
    """run_ai_exam"""

    @patch("zhs.ai.course.AiCourseManager")
    def test_no_courses_prints_zero(self, mock_mgr_cls: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """无课程时打印 0"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = []

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)

        captured = capsys.readouterr()
        assert "发现 0 门课程" in captured.out
        assert "共完成 0 个考试" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    def test_explicit_course_and_class(self, mock_mgr_cls: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """显式指定 ai_course + ai_class 时构造单课程列表"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_exam_tasks.return_value = []

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=100, ai_class=200, submit=False)

        # 不应调用 get_ai_course_list
        mock_mgr.get_ai_course_list.assert_not_called()
        captured = capsys.readouterr()
        assert "发现 1 门课程" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    def test_course_without_course_id_skipped(self, mock_mgr_cls: MagicMock) -> None:
        """课程缺少 courseId 跳过"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [
            {"courseName": "测试课程", "classId": "200"}  # 缺少 courseId
        ]

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        # 不应调用 get_exam_tasks
        mock_mgr.get_exam_tasks.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    def test_no_exam_tasks_prints_no_exams(self, mock_mgr_cls: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """无未完成考试时打印提示"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = []

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        captured = capsys.readouterr()
        assert "无未完成考试" in captured.out

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_task_missing_ids_skipped(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
    ) -> None:
        """考试任务缺少 examTestId 或 examPaperId 跳过"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {"taskName": "考试1", "examTestId": "", "examPaperId": "100"},  # 缺 examTestId
            {"taskName": "考试2", "examTestId": "100", "examPaperId": ""},  # 缺 examPaperId
        ]

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        # ExamCtx 不应被实例化
        mock_exam_ctx_cls.assert_not_called()

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_success_no_submit(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """考试成功（不提交）"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {
                "taskName": "考试1",
                "examTestId": "100",
                "examPaperId": "200",
                "id": "300",
                "userId": 400,
            }
        ]

        mock_ctx = MagicMock()
        mock_exam_ctx_cls.return_value = mock_ctx
        mock_ctx.start.return_value = (True, 5, 5)

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        captured = capsys.readouterr()
        assert "答题完成（未提交）" in captured.out
        assert "共完成 1 个考试" in captured.out

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_submit_all_correct(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """提交模式 + 全对"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {
                "taskName": "考试1",
                "examTestId": "100",
                "examPaperId": "200",
                "id": "300",
                "userId": 400,
            }
        ]

        mock_ctx = MagicMock()
        mock_exam_ctx_cls.return_value = mock_ctx
        mock_ctx.start.return_value = (True, 5, 5)

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=True)
        captured = capsys.readouterr()
        assert "全对" in captured.out
        mock_ctx.start.assert_called_once_with(submit=True)

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_submit_zero_correct(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """提交模式 + 0 题正确"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {
                "taskName": "考试1",
                "examTestId": "100",
                "examPaperId": "200",
                "id": "300",
                "userId": 400,
            }
        ]

        mock_ctx = MagicMock()
        mock_exam_ctx_cls.return_value = mock_ctx
        mock_ctx.start.return_value = (False, 0, 5)

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=True)
        captured = capsys.readouterr()
        assert "无法查看答案" in captured.out

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_submit_partial_correct(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """提交模式 + 部分正确"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {
                "taskName": "考试1",
                "examTestId": "100",
                "examPaperId": "200",
                "id": "300",
                "userId": 400,
            }
        ]

        mock_ctx = MagicMock()
        mock_exam_ctx_cls.return_value = mock_ctx
        mock_ctx.start.return_value = (False, 3, 5)

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=True)
        captured = capsys.readouterr()
        assert "3/5" in captured.out
        assert "正确" in captured.out

    @patch("zhs.ai.exam.ExamCtx")
    @patch("zhs.ai.course.AiCourseManager")
    def test_exam_exception_handled(
        self,
        mock_mgr_cls: MagicMock,
        mock_exam_ctx_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """考试异常被捕获"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.return_value = [
            {
                "taskName": "考试1",
                "examTestId": "100",
                "examPaperId": "200",
                "id": "300",
                "userId": 400,
            }
        ]

        mock_ctx = MagicMock()
        mock_exam_ctx_cls.return_value = mock_ctx
        mock_ctx.start.side_effect = Exception("network error")

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        captured = capsys.readouterr()
        assert "处理失败" in captured.out
        assert "共完成 0 个考试" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    def test_get_exam_tasks_exception_handled(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """get_exam_tasks 抛异常被捕获"""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_ai_course_list.return_value = [{"courseId": "100", "classId": "200", "courseName": "测试课程"}]
        mock_mgr.get_exam_tasks.side_effect = Exception("network error")

        config = _make_config()
        session = MagicMock()

        run_ai_exam(session, config, ai_course=None, ai_class=None, submit=False)
        captured = capsys.readouterr()
        assert "考试处理失败" in captured.out

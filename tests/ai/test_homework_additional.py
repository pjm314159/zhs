"""ai/homework.py 补充测试

覆盖 _open / _get_sheet_content / _get_question_content / _save_answer / _submit / _finish 等方法。
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.homework import HomeworkCtx
from zhs.ai.models import OptionVo, QuestionContent, QuestionSheet
from zhs.config import AIConfig
from zhs.exceptions import ZhsError


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.exam_key = b"onbfhdyvz8x7otrp"
    session.crypto.ai_key = b"hw2fdlwcj4cs1mx7"
    session.crypto.key_bytes = MagicMock(side_effect=lambda name: getattr(session.crypto, name))
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.exam = "https://studentexamtest.zhihuishu.com"
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """AI 配置"""
    return AIConfig(api_key="test-key", model="gpt-4o-mini")


@pytest.fixture
def homework_ctx(mock_session: MagicMock, ai_config: AIConfig) -> HomeworkCtx:
    """创建 HomeworkCtx 实例"""
    return HomeworkCtx(
        session=mock_session,
        course_id=100,
        knowledge_id=200,
        exam_test_id=300,
        exam_paper_id=400,
        ai_config=ai_config,
    )


class TestOpen:
    """_open"""

    def test_open_success(self, homework_ctx: HomeworkCtx) -> None:
        """openExam 成功"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            homework_ctx._open()
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        # 验证 URL
        assert "openExam" in call_args[0][0]
        # 验证 data
        data = call_args[0][1]
        assert data["examTestId"] == 300
        assert data["examPaperId"] == 400
        assert data["courseId"] == 100

    def test_open_retries_on_failure(self, homework_ctx: HomeworkCtx) -> None:
        """openExam 失败重试 3 次"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            mock_api.side_effect = Exception("Network error")
            with pytest.raises(ZhsError, match="openExam"):
                homework_ctx._open()
        assert mock_api.call_count == 3

    def test_open_success_on_second_attempt(self, homework_ctx: HomeworkCtx) -> None:
        """openExam 第二次成功"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            mock_api.side_effect = [Exception("err"), {"code": 0}]
            homework_ctx._open()
        assert mock_api.call_count == 2


class TestGetSheetContent:
    """_get_sheet_content"""

    def test_returns_sheet_content(self, homework_ctx: HomeworkCtx) -> None:
        """返回试卷内容"""
        mock_data: dict[str, Any] = {
            "data": {
                "partSheetVos": [
                    {
                        "questionSheetVos": [
                            {"questionId": 1, "version": 1},
                            {"questionId": 2, "version": 1},
                        ]
                    }
                ]
            }
        }
        with patch.object(homework_ctx, "_api_query", return_value=mock_data):
            result = homework_ctx._get_sheet_content()
        assert len(result) == 2
        assert result[0].question_id == 1

    def test_uses_get_method(self, homework_ctx: HomeworkCtx) -> None:
        """使用 GET 方法"""
        mock_data: dict[str, Any] = {"data": {"partSheetVos": [{"questionSheetVos": []}]}}
        with patch.object(homework_ctx, "_api_query", return_value=mock_data) as mock_api:
            homework_ctx._get_sheet_content()
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs["method"] == "GET"

    def test_cached_content_returned(self, homework_ctx: HomeworkCtx) -> None:
        """已缓存的 content 直接返回（不重复请求）"""
        # 模拟已缓存
        cached = [QuestionSheet(question_id=999, version=1)]
        homework_ctx._sheet_content = cached

        with patch.object(homework_ctx, "_api_query") as mock_api:
            result = homework_ctx._get_sheet_content()

        assert result is cached
        mock_api.assert_not_called()

    def test_retries_on_failure(self, homework_ctx: HomeworkCtx) -> None:
        """失败重试 3 次"""
        with patch.object(homework_ctx, "_api_query", side_effect=Exception("err")) as mock_api:
            with pytest.raises(ZhsError, match="getSheetContent"):
                homework_ctx._get_sheet_content()
            # 应该重试 3 次
            assert mock_api.call_count == 3

    def test_success_on_retry(self, homework_ctx: HomeworkCtx) -> None:
        """重试后成功"""
        mock_data: dict[str, Any] = {"data": {"partSheetVos": [{"questionSheetVos": []}]}}
        with patch.object(homework_ctx, "_api_query", side_effect=[Exception("err"), mock_data]) as mock_api:
            result = homework_ctx._get_sheet_content()
            assert result == []
            assert mock_api.call_count == 2


class TestGetQuestionContent:
    """_get_question_content"""

    def test_returns_question_content(self, homework_ctx: HomeworkCtx) -> None:
        """返回题目内容"""
        mock_data: dict[str, Any] = {
            "data": {
                "id": 1,
                "content": "题目内容",
                "questionType": 1,
                "optionVos": [{"id": 10, "content": "选项A"}],
            }
        }
        with patch.object(homework_ctx, "_api_query", return_value=mock_data):
            result = homework_ctx._get_question_content(1, 1)
        assert result is not None
        assert result.id == 1
        assert result.content == "题目内容"

    def test_uses_get_method(self, homework_ctx: HomeworkCtx) -> None:
        """使用 GET 方法"""
        mock_data: dict[str, Any] = {"data": {"id": 1, "content": "x", "questionType": 1, "optionVos": []}}
        with patch.object(homework_ctx, "_api_query", return_value=mock_data) as mock_api:
            homework_ctx._get_question_content(1, 1)
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs["method"] == "GET"

    def test_returns_none_after_3_retries(self, homework_ctx: HomeworkCtx) -> None:
        """3 次重试后返回 None"""
        with patch.object(homework_ctx, "_api_query", side_effect=Exception("err")) as mock_api:
            result = homework_ctx._get_question_content(1, 1)
            assert result is None
            assert mock_api.call_count == 3

    def test_success_on_retry(self, homework_ctx: HomeworkCtx) -> None:
        """重试后成功"""
        mock_data: dict[str, Any] = {"data": {"id": 1, "content": "x", "questionType": 1, "optionVos": []}}
        with patch.object(homework_ctx, "_api_query", side_effect=[Exception("err"), mock_data]) as mock_api:
            result = homework_ctx._get_question_content(1, 1)
            assert result is not None
            assert mock_api.call_count == 2

    def test_data_includes_question_id_and_version(self, homework_ctx: HomeworkCtx) -> None:
        """请求数据包含 questionId 和 version"""
        mock_data: dict[str, Any] = {"data": {"id": 1, "content": "x", "questionType": 1, "optionVos": []}}
        with patch.object(homework_ctx, "_api_query", return_value=mock_data) as mock_api:
            homework_ctx._get_question_content(123, 2)
        call_args = mock_api.call_args
        data = call_args[0][1]
        assert data["questionId"] == 123
        assert data["version"] == 2


class TestSaveAnswer:
    """_save_answer"""

    def test_save_success(self, homework_ctx: HomeworkCtx) -> None:
        """保存成功"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            result = homework_ctx._save_answer(1, ["A", "B"])
        assert result is True
        mock_api.assert_called_once()

    def test_empty_answers_returns_false(self, homework_ctx: HomeworkCtx) -> None:
        """空答案返回 False"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            result = homework_ctx._save_answer(1, [])
        assert result is False
        mock_api.assert_not_called()

    def test_answer_joined_with_separator(self, homework_ctx: HomeworkCtx) -> None:
        """答案用 #@# 分隔"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            homework_ctx._save_answer(1, ["A", "B", "C"])
        call_args = mock_api.call_args
        data = call_args[0][1]
        assert data["answer"] == "A#@#B#@#C"

    def test_single_answer_no_separator(self, homework_ctx: HomeworkCtx) -> None:
        """单个答案无分隔符"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            homework_ctx._save_answer(1, ["A"])
        call_args = mock_api.call_args
        data = call_args[0][1]
        assert data["answer"] == "A"

    def test_failure_returns_false(self, homework_ctx: HomeworkCtx) -> None:
        """异常时返回 False"""
        with patch.object(homework_ctx, "_api_query", side_effect=Exception("err")):
            result = homework_ctx._save_answer(1, ["A"])
        assert result is False

    def test_data_includes_required_fields(self, homework_ctx: HomeworkCtx) -> None:
        """数据包含必要字段"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            homework_ctx._save_answer(123, ["A"])
        call_args = mock_api.call_args
        data = call_args[0][1]
        assert data["questionId"] == 123
        assert data["examTestId"] == 300
        assert data["examPaperId"] == 400
        assert data["recruitId"] == 100  # course_id 作为 recruitId
        assert data["dataVos"] is None


class TestSubmit:
    """_submit"""

    def test_submit_success(self, homework_ctx: HomeworkCtx) -> None:
        """提交成功"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            homework_ctx._submit()
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        data = call_args[0][1]
        assert data["courseType"] == 8
        assert data["aiKnlowledgeId"] == 200  # knowledge_id

    def test_submit_sets_stopped_flag(self, homework_ctx: HomeworkCtx) -> None:
        """提交后设置 _stopped=True（finally 块）"""
        homework_ctx._stopped = False
        with patch.object(homework_ctx, "_api_query"):
            homework_ctx._submit()
        assert homework_ctx._stopped is True

    def test_submit_failure_still_sets_stopped(self, homework_ctx: HomeworkCtx) -> None:
        """提交失败也设置 _stopped=True（finally 块）"""
        homework_ctx._stopped = False
        with (
            patch.object(homework_ctx, "_api_query", side_effect=Exception("err")),
            pytest.raises(ZhsError, match="submitExam"),
        ):
            homework_ctx._submit()
        # 即使失败，_stopped 也应为 True
        assert homework_ctx._stopped is True

    def test_submit_retries_on_failure(self, homework_ctx: HomeworkCtx) -> None:
        """失败重试 3 次"""
        with patch.object(homework_ctx, "_api_query", side_effect=Exception("err")) as mock_api:
            with pytest.raises(ZhsError, match="submitExam"):
                homework_ctx._submit()
            assert mock_api.call_count == 3


class TestFinish:
    """_finish"""

    def test_finish_returns_all_correct(self, homework_ctx: HomeworkCtx) -> None:
        """全对时返回 (True, n, n)"""
        sheets = [QuestionSheet(question_id=1, version=1), QuestionSheet(question_id=2, version=1)]
        with (
            patch.object(homework_ctx, "_submit") as mock_submit,
            patch.object(homework_ctx, "_check_results", return_value=(2, 2)),
        ):
            result = homework_ctx._finish(submit=True, sheets=sheets)
        mock_submit.assert_called_once_with(True)
        assert result == (True, 2, 2)

    def test_finish_returns_partial_correct(self, homework_ctx: HomeworkCtx) -> None:
        """部分正确返回 (False, correct, total)"""
        sheets = [QuestionSheet(question_id=1, version=1), QuestionSheet(question_id=2, version=1)]
        with (
            patch.object(homework_ctx, "_submit"),
            patch.object(homework_ctx, "_check_results", return_value=(1, 2)),
        ):
            result = homework_ctx._finish(submit=False, sheets=sheets)
        assert result == (False, 1, 2)

    def test_finish_returns_zero_correct(self, homework_ctx: HomeworkCtx) -> None:
        """全错返回 (False, 0, total)"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        with (
            patch.object(homework_ctx, "_submit"),
            patch.object(homework_ctx, "_check_results", return_value=(0, 1)),
        ):
            result = homework_ctx._finish(submit=True, sheets=sheets)
        assert result == (False, 0, 1)


class TestAnswerQuestions:
    """_answer_questions"""

    def test_processes_all_sheets(self, homework_ctx: HomeworkCtx) -> None:
        """处理所有题目"""
        sheets = [
            QuestionSheet(question_id=1, version=1),
            QuestionSheet(question_id=2, version=1),
            QuestionSheet(question_id=3, version=1),
        ]
        with (
            patch.object(homework_ctx, "_process_question") as mock_process,
            patch("zhs.ai.homework.time.sleep"),
        ):
            homework_ctx._answer_questions(sheets)
        assert mock_process.call_count == 3

    def test_empty_sheets_does_nothing(self, homework_ctx: HomeworkCtx) -> None:
        """空列表不处理"""
        with patch.object(homework_ctx, "_process_question") as mock_process:
            homework_ctx._answer_questions([])
        mock_process.assert_not_called()


class TestProcessQuestionErrorHandling:
    """_process_question 错误处理"""

    def test_get_question_failure_increments_progress(self, homework_ctx: HomeworkCtx) -> None:
        """获取题目失败时增加进度并标记 error"""
        sheet = QuestionSheet(question_id=1, version=1)
        with (
            patch.object(homework_ctx, "_get_question_content", return_value=None),
            patch.object(homework_ctx, "_update_progress") as mock_update,
            patch("zhs.ai.homework.time.sleep"),
        ):
            initial = homework_ctx._progress_current
            homework_ctx._process_question(sheet)
        assert homework_ctx._progress_current == initial + 1
        mock_update.assert_called_with("error")

    def test_successful_question_saves_answer(self, homework_ctx: HomeworkCtx) -> None:
        """成功获取题目后保存答案"""
        sheet = QuestionSheet(question_id=1, version=1)
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=1, content="A"), OptionVo(id=2, content="B")],
        )
        with (
            patch.object(homework_ctx, "_get_question_content", return_value=question),
            patch.object(homework_ctx, "_get_answer", return_value=(["1"], "cached")),
            patch.object(homework_ctx, "_save_answer") as mock_save,
            patch.object(homework_ctx, "_update_progress"),
            patch("zhs.ai.homework.time.sleep"),
        ):
            homework_ctx._process_question(sheet)
        mock_save.assert_called_once_with(1, ["1"])


class TestStartMethod:
    """start 方法"""

    def test_start_calls_super_with_submit_true(self, homework_ctx: HomeworkCtx) -> None:
        """start 默认 submit=True"""
        with patch("zhs.ai.exam_base.AiExamBase.start", return_value=(True, 5, 5)) as mock_super:
            homework_ctx.start()
        mock_super.assert_called_once()
        call_kwargs = mock_super.call_args.kwargs
        assert call_kwargs["submit"] is True

    def test_start_with_reference_materials(self, homework_ctx: HomeworkCtx) -> None:
        """start 传递 reference_materials（作为位置参数）"""
        refs = [{"name": "PPT1", "url": "http://example.com/ppt.pptx", "content": "text"}]
        with patch("zhs.ai.exam_base.AiExamBase.start", return_value=(True, 5, 5)) as mock_super:
            homework_ctx.start(reference_materials=refs)
        # super().start(reference_materials, submit=submit) - reference_materials 是第一个位置参数
        call_args = mock_super.call_args
        assert call_args[0][0] == refs

    def test_start_with_submit_false(self, homework_ctx: HomeworkCtx) -> None:
        """start 显式 submit=False"""
        with patch("zhs.ai.exam_base.AiExamBase.start", return_value=(True, 5, 5)) as mock_super:
            homework_ctx.start(submit=False)
        call_kwargs = mock_super.call_args.kwargs
        assert call_kwargs["submit"] is False


class TestExamBaseUrl:
    """_exam_base_url"""

    def test_returns_session_exam_url(self, homework_ctx: HomeworkCtx) -> None:
        """返回 session.urls.exam"""
        assert homework_ctx._exam_base_url == "https://studentexamtest.zhihuishu.com"


class TestApiQuery:
    """_api_query"""

    def test_calls_session_ai_exam_query(self, homework_ctx: HomeworkCtx) -> None:
        """调用 session.ai_exam_query"""
        url = "https://example.com/api"
        data = {"foo": "bar"}
        with patch.object(homework_ctx._session, "ai_exam_query", return_value={"code": 0}) as mock_query:
            homework_ctx._api_query(url, data)
        mock_query.assert_called_once_with(url, data, method="POST")

    def test_passes_method_parameter(self, homework_ctx: HomeworkCtx) -> None:
        """传递 method 参数"""
        with patch.object(homework_ctx._session, "ai_exam_query", return_value={"code": 0}) as mock_query:
            homework_ctx._api_query("url", {}, method="GET")
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["method"] == "GET"

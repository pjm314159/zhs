"""ai/exam.py ExamCtx 测试"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.exam import ExamCtx
from zhs.ai.models import OptionVo, QuestionContent, QuestionSheet
from zhs.config import AIConfig, ExamConfig


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.exam_key = b"onbfhdyvz8x7otrp"
    session.crypto.ai_key = b"hw2fdlwcj4cs1mx7"
    session.crypto.key_bytes = MagicMock(side_effect=lambda name: getattr(session.crypto, name))
    session.urls = MagicMock()
    session.urls.exam = "https://studentexamtest.zhihuishu.com"
    session.urls.ai = "https://kg-run-student.zhihuishu.com"
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """AI 配置"""
    return AIConfig(api_key="test-key", model="gpt-4o-mini")


@pytest.fixture
def exam_config() -> ExamConfig:
    """考试配置"""
    return ExamConfig(save_nums=2, delay_min=0.0, delay_max=0.0)


@pytest.fixture
def exam_ctx(
    mock_session: MagicMock,
    ai_config: AIConfig,
    exam_config: ExamConfig,
) -> ExamCtx:
    """创建 ExamCtx 实例"""
    return ExamCtx(
        session=mock_session,
        course_id="7123456789012345678",
        class_id="523456",
        exam_test_id="1890123",
        exam_paper_id="867890123",
        ai_config=ai_config,
        exam_config=exam_config,
    )


class TestExamCtxInit:
    """ExamCtx 初始化"""

    def test_basic_init(self, exam_ctx: ExamCtx) -> None:
        """基本初始化"""
        assert exam_ctx._course_id == "7123456789012345678"
        assert exam_ctx._class_id == "523456"
        assert exam_ctx._exam_test_id == "1890123"
        assert exam_ctx._exam_paper_id == "867890123"

    def test_save_nums_from_config(self, exam_ctx: ExamCtx) -> None:
        """save_nums 从 ExamConfig 获取"""
        assert exam_ctx._save_nums == 2

    def test_heartbeat_thread_attribute(self, exam_ctx: ExamCtx) -> None:
        """心跳线程属性初始化为 None"""
        assert exam_ctx._heartbeat_thread is None

    def test_stopped_flag(self, exam_ctx: ExamCtx) -> None:
        """stopped 标志初始化为 False"""
        assert exam_ctx._stopped is False


class TestAnswerFormat:
    """答案格式化"""

    def test_single_choice_format(self, exam_ctx: ExamCtx) -> None:
        """单选题 answer 为单个选项 ID"""
        answers = ["739511831"]
        result = "#@#".join(str(a) for a in answers)
        assert result == "739511831"

    def test_multiple_choice_format(self, exam_ctx: ExamCtx) -> None:
        """多选题 answer 用 #@# 分隔"""
        answers = ["739511830", "739511831"]
        result = "#@#".join(str(a) for a in answers)
        assert result == "739511830#@#739511831"

    def test_fill_blank_format(self, exam_ctx: ExamCtx) -> None:
        """填空题 answer 用 / 分隔"""
        answers = ["答案1", "答案2"]
        result = "/".join(str(a) for a in answers)
        assert result == "答案1/答案2"


class TestGetAnswer:
    """答案获取策略"""

    def test_cache_hit(self, exam_ctx: ExamCtx) -> None:
        """缓存命中返回答案"""
        exam_ctx._all_answer_cache = {"123": {"answer": "456#@#789"}}
        result = exam_ctx._get_cached_answer(123)
        assert result is not None
        assert result == ["456", "789"]

    def test_cache_miss(self, exam_ctx: ExamCtx) -> None:
        """缓存未命中返回 None"""
        result = exam_ctx._get_cached_answer(999)
        assert result is None

    def test_fill_blank_cache_not_split(self, exam_ctx: ExamCtx) -> None:
        """填空题 answer 含 / 不拆分，返回单元素列表"""
        exam_ctx._all_answer_cache = {"123": {"answer": "身体健康/心理健康"}}
        result = exam_ctx._get_cached_answer(123)
        assert result is not None
        assert result == ["身体健康/心理健康"]


class TestGetAnswerStrategy:
    """答案获取三级策略"""

    def test_fewer_than_two_options_select_first(self, exam_ctx: ExamCtx) -> None:
        """选项少于 2 个且非填空 → 选第一个"""
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="唯一选项")],
        )
        answers, source = exam_ctx._get_answer(question)
        assert answers == ["10"]
        assert source == "cached"

    def test_fill_blank_fewer_than_two_options(self, exam_ctx: ExamCtx) -> None:
        """填空题选项少于 2 个不选第一个"""
        question = QuestionContent(
            id=1,
            content="填空___",
            question_type=3,
            option_vos=[OptionVo(id=10, content="答案")],
        )
        answers, source = exam_ctx._get_answer(question)
        assert source == "random"


class TestSaveBatchAnswer:
    """批量保存答案"""

    def test_save_batch_calls_api(self, exam_ctx: ExamCtx) -> None:
        """saveBatchAnswer 调用 API"""
        with patch.object(exam_ctx, "_api_query") as mock_api:
            mock_api.return_value = {"code": 0}
            exam_ctx._save_batch_answer(
                [
                    {
                        "questionId": 7123456789,
                        "answer": "739511831",
                        "questionType": 1,
                    }
                ]
            )
            mock_api.assert_called_once()
            call_data = mock_api.call_args[0][1]
            assert "answerList" in call_data
            assert len(call_data["answerList"]) == 1
            assert call_data["answerList"][0]["answer"] == "739511831"

    def test_save_batch_multiple_answers(self, exam_ctx: ExamCtx) -> None:
        """批量保存多个答案"""
        with patch.object(exam_ctx, "_api_query") as mock_api:
            mock_api.return_value = {"code": 0}
            exam_ctx._save_batch_answer(
                [
                    {"questionId": 1, "answer": "100", "questionType": 1},
                    {"questionId": 2, "answer": "200#@#201", "questionType": 2},
                ]
            )
            call_data = mock_api.call_args[0][1]
            assert len(call_data["answerList"]) == 2

    def test_save_batch_includes_recruit_id(self, exam_ctx: ExamCtx) -> None:
        """saveBatchAnswer 包含 recruitId（courseId）"""
        with patch.object(exam_ctx, "_api_query") as mock_api:
            mock_api.return_value = {"code": 0}
            exam_ctx._save_batch_answer([{"questionId": 1, "answer": "100", "questionType": 1}])
            call_data = mock_api.call_args[0][1]
            assert call_data["recruitId"] == "7123456789012345678"
            assert call_data["answerList"][0]["recruitId"] == "7123456789012345678"


class TestProcessQuestions:
    """题目处理（批量保存）"""

    def test_batch_save_when_reaching_save_nums(self, exam_ctx: ExamCtx) -> None:
        """达到 save_nums 题时触发批量保存"""
        # save_nums=2，处理 2 题应触发 1 次保存
        sheets = [
            QuestionSheet(question_id=1, version=1),
            QuestionSheet(question_id=2, version=1),
        ]
        with (
            patch.object(exam_ctx, "_get_question_content") as mock_get_qc,
            patch.object(exam_ctx, "_save_batch_answer") as mock_save,
            patch("zhs.ai.exam.time.sleep"),
            patch("zhs.ai.exam.random.uniform", return_value=0.0),
        ):
            mock_get_qc.return_value = QuestionContent(
                id=1,
                content="test",
                question_type=1,
                option_vos=[OptionVo(id=10, content="A"), OptionVo(id=11, content="B")],
            )
            exam_ctx._process_questions(sheets)
            mock_save.assert_called_once()

    def test_remaining_saved_after_loop(self, exam_ctx: ExamCtx) -> None:
        """不足 save_nums 的剩余题目在循环结束后保存"""
        # save_nums=2，处理 3 题应触发 2 次保存（2+1）
        sheets = [
            QuestionSheet(question_id=1, version=1),
            QuestionSheet(question_id=2, version=1),
            QuestionSheet(question_id=3, version=1),
        ]
        with (
            patch.object(exam_ctx, "_get_question_content") as mock_get_qc,
            patch.object(exam_ctx, "_save_batch_answer") as mock_save,
            patch("zhs.ai.exam.time.sleep"),
            patch("zhs.ai.exam.random.uniform", return_value=0.0),
        ):
            mock_get_qc.return_value = QuestionContent(
                id=1,
                content="test",
                question_type=1,
                option_vos=[OptionVo(id=10, content="A"), OptionVo(id=11, content="B")],
            )
            exam_ctx._process_questions(sheets)
            assert mock_save.call_count == 2


class TestHeartbeat:
    """心跳"""

    def test_heartbeat_data(self, exam_ctx: ExamCtx) -> None:
        """心跳数据包含 examTestId, examPaperId, heartbeatTime"""
        with patch.object(exam_ctx, "_api_query") as mock_api:
            mock_api.return_value = {"code": 0}
            exam_ctx._heartbeat_once()
            mock_api.assert_called_once()
            call_data = mock_api.call_args[0][1]
            assert call_data["examTestId"] == "1890123"
            assert call_data["examPaperId"] == "867890123"
            assert "heartbeatTime" in call_data


class TestSubmit:
    """提交考试"""

    def test_submit_calls_session_method(self, exam_ctx: ExamCtx) -> None:
        """submit 调用 session.ai_exam_submit"""
        with patch.object(exam_ctx._session, "ai_exam_submit") as mock_submit:
            mock_submit.return_value = True
            exam_ctx._submit()
            mock_submit.assert_called_once()
            call_args = mock_submit.call_args
            url = call_args[0][0]
            data = call_args[0][1]
            assert "submit" in url
            assert data["examTestId"] == "1890123"
            assert data["recruitId"] == "7123456789012345678"
            assert data["examPaperId"] == "867890123"

    def test_submit_raises_on_failure(self, exam_ctx: ExamCtx) -> None:
        """submit 失败抛出 ZhsError"""
        from zhs.exceptions import ZhsError

        with patch.object(exam_ctx._session, "ai_exam_submit") as mock_submit:
            mock_submit.side_effect = Exception("network error")
            with pytest.raises(ZhsError, match="submit"):
                exam_ctx._submit()


class TestOpenExamDetail:
    """获取考试详情"""

    def test_open_exam_detail_calls_ai_task_query(self, exam_ctx: ExamCtx) -> None:
        """openExamDetail 调用 session.ai_task_query（ai_key）"""
        exam_ctx._student_id = 978901234
        exam_ctx._task_id = "634567"
        with patch.object(exam_ctx._session, "ai_task_query") as mock_query:
            mock_query.return_value = {
                "code": 200,
                "data": {"isLookAnswer": 1, "isAllowShowDetail": 1, "score": 136},
            }
            detail = exam_ctx._open_exam_detail()
            mock_query.assert_called_once()
            call_args = mock_query.call_args
            url = call_args[0][0]
            data = call_args[0][1]
            assert "openExamDetail" in url
            assert data["classId"] == "523456"
            assert data["courseId"] == "7123456789012345678"
            assert data["examTestId"] == "1890123"
            assert data["examPaperId"] == "867890123"
            assert data["examId"] == "867890123"
            assert data["studentId"] == 978901234
            assert data["taskId"] == "634567"
            assert data["taskType"] is None
            assert detail["isLookAnswer"] == 1
            assert detail["score"] == 136

    def test_open_exam_detail_returns_empty_on_failure(self, exam_ctx: ExamCtx) -> None:
        """openExamDetail 失败返回空字典"""
        exam_ctx._student_id = 978901234
        exam_ctx._task_id = "634567"
        with patch.object(exam_ctx._session, "ai_task_query") as mock_query:
            mock_query.side_effect = Exception("network error")
            detail = exam_ctx._open_exam_detail()
            assert detail == {}


class TestStartWithSubmit:
    """start() 方法 submit 流程"""

    @pytest.fixture
    def exam_ctx_with_ids(
        self,
        mock_session: MagicMock,
        ai_config: AIConfig,
        exam_config: ExamConfig,
    ) -> ExamCtx:
        """带 student_id 和 task_id 的 ExamCtx"""
        return ExamCtx(
            session=mock_session,
            course_id="7123456789012345678",
            class_id="523456",
            exam_test_id="1890123",
            exam_paper_id="867890123",
            ai_config=ai_config,
            exam_config=exam_config,
            student_id=978901234,
            task_id="634567",
        )

    def test_submit_false_skips_submit_and_check(self, exam_ctx_with_ids: ExamCtx) -> None:
        """submit=False 不调用 submit 和 _check_results"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        with (
            patch.object(exam_ctx_with_ids, "_load_cache"),
            patch.object(exam_ctx_with_ids, "_open_exam"),
            patch.object(exam_ctx_with_ids, "_heartbeat"),
            patch.object(exam_ctx_with_ids, "_get_sheet_content", return_value=sheets),
            patch.object(exam_ctx_with_ids, "_process_questions"),
            patch.object(exam_ctx_with_ids, "_submit") as mock_submit,
            patch.object(exam_ctx_with_ids, "_open_exam_detail") as mock_detail,
            patch.object(exam_ctx_with_ids, "_check_results") as mock_check,
        ):
            all_correct, correct, total = exam_ctx_with_ids.start(submit=False)
            mock_submit.assert_not_called()
            mock_detail.assert_not_called()
            mock_check.assert_not_called()
            assert total == 1
            assert correct == 0
            assert all_correct is False

    def test_submit_true_calls_submit_and_check(self, exam_ctx_with_ids: ExamCtx) -> None:
        """submit=True 且可查看答案时调用 submit 和 _check_results"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        with (
            patch.object(exam_ctx_with_ids, "_load_cache"),
            patch.object(exam_ctx_with_ids, "_open_exam"),
            patch.object(exam_ctx_with_ids, "_heartbeat"),
            patch.object(exam_ctx_with_ids, "_get_sheet_content", return_value=sheets),
            patch.object(exam_ctx_with_ids, "_process_questions"),
            patch.object(exam_ctx_with_ids, "_submit") as mock_submit,
            patch.object(exam_ctx_with_ids, "_open_exam_detail", return_value={"isLookAnswer": 1, "score": 136}),
            patch.object(exam_ctx_with_ids, "_check_results", return_value=(1, 1)) as mock_check,
        ):
            all_correct, correct, total = exam_ctx_with_ids.start(submit=True)
            mock_submit.assert_called_once()
            mock_check.assert_called_once()
            assert total == 1
            assert correct == 1
            assert all_correct is True

    def test_submit_true_cannot_see_answers_skips_check(self, exam_ctx_with_ids: ExamCtx) -> None:
        """submit=True 但无法查看答案时跳过 _check_results"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        detail = {"isLookAnswer": 0, "isAllowShowDetail": 0}
        with (
            patch.object(exam_ctx_with_ids, "_load_cache"),
            patch.object(exam_ctx_with_ids, "_open_exam"),
            patch.object(exam_ctx_with_ids, "_heartbeat"),
            patch.object(exam_ctx_with_ids, "_get_sheet_content", return_value=sheets),
            patch.object(exam_ctx_with_ids, "_process_questions"),
            patch.object(exam_ctx_with_ids, "_submit"),
            patch.object(exam_ctx_with_ids, "_open_exam_detail", return_value=detail),
            patch.object(exam_ctx_with_ids, "_check_results") as mock_check,
        ):
            all_correct, correct, total = exam_ctx_with_ids.start(submit=True)
            mock_check.assert_not_called()
            assert total == 1
            assert correct == 0
            assert all_correct is False

    def test_submit_true_is_allow_show_detail_also_triggers_check(self, exam_ctx_with_ids: ExamCtx) -> None:
        """isAllowShowDetail=1 也可触发 _check_results"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        detail = {"isLookAnswer": 0, "isAllowShowDetail": 1}
        with (
            patch.object(exam_ctx_with_ids, "_load_cache"),
            patch.object(exam_ctx_with_ids, "_open_exam"),
            patch.object(exam_ctx_with_ids, "_heartbeat"),
            patch.object(exam_ctx_with_ids, "_get_sheet_content", return_value=sheets),
            patch.object(exam_ctx_with_ids, "_process_questions"),
            patch.object(exam_ctx_with_ids, "_submit"),
            patch.object(exam_ctx_with_ids, "_open_exam_detail", return_value=detail),
            patch.object(exam_ctx_with_ids, "_check_results", return_value=(0, 1)) as mock_check,
        ):
            all_correct, correct, total = exam_ctx_with_ids.start(submit=True)
            mock_check.assert_called_once()
            assert correct == 0
            assert all_correct is False

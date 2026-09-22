"""知到考试做题器测试

覆盖 ExamWorker 的核心流程：
- run_exam: doExam → 生成答案 → saveStudentAnswer → [可选] submit
- _save_answer: 使用 exam_save_answer（examType=1, source=1）
- _submit_exam: 使用 exam_submit（submit=True 时调用）
- 源感知延迟：仅缓存/随机答案延迟，LLM 不延迟
- 默认不提交（submit=False），仅当 --submit 时自动提交
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.config import AppConfig, ExamConfig
from zhs.session import ZhsSession
from zhs.zhidao.exam.models import ExamInfo
from zhs.zhidao.exam.worker import ExamWorker
from zhs.zhidao.homework.models import (
    HomeworkQuestion,
    HomeworkQuestionOption,
)


def _make_mock_session() -> MagicMock:
    """创建 mock session"""
    session = MagicMock(spec=ZhsSession)
    session.urls.homework = "https://studentexam-api.zhihuishu.com"
    session.urls.taurusexam = "https://taurusexam-api.zhihuishu.com"
    session.ai_analysis_run.return_value = ""
    return session


def _make_config() -> AppConfig:
    """创建测试配置"""
    return AppConfig(exam=ExamConfig(delay_min=3.0, delay_max=5.0))


def _make_cache(tmp_path: Path | None = None) -> ZhidaoHomeworkCache:
    """创建测试缓存"""
    import tempfile

    cache_dir = tmp_path if tmp_path else Path(tempfile.mkdtemp(prefix="zhs_test_"))
    return ZhidaoHomeworkCache(cache_dir=cache_dir)


def _make_exam(**overrides: object) -> ExamInfo:
    """创建测试考试项"""
    data: dict[str, object] = {
        "id": "edJddjZE",
        "state": 1,
        "score": None,
        "achieveCount": 0,
        "achieve": 0,
        "faStudentExamRemainCount": 1,
        "courseId": 1000083416,
        "courseName": "思想道德与法治",
        "examId": "eAqdKONe",
        "examName": "思想道德与法治教程考试",
        "problemNum": 2,
        "totalScore": "100",
        "limitTime": 90,
        "startTime": "2026-07-01 00:00:00",
        "endDate": "2026-07-10 23:59:59",
    }
    data.update(overrides)
    return ExamInfo.from_api(data)


def _make_question(
    eid: str | None = "abc123==",
    qid: int | None = None,
    question_type_id: int = 1,
    options: list[dict[str, object]] | None = None,
) -> HomeworkQuestion:
    """创建测试题目（复用 HomeworkQuestion 模型）"""
    if options is None:
        options = [
            {"id": 101, "content": "选项A"},
            {"id": 102, "content": "选项B"},
            {"id": 103, "content": "选项C"},
            {"id": 104, "content": "选项D"},
        ]
    return HomeworkQuestion(
        eid=eid,
        id=qid,
        name="测试题目",
        questionType=question_type_id,
        questionOptions=[HomeworkQuestionOption.model_validate(o) for o in options],
        questionScore="2",
    )


def _make_do_exam_response(questions: list[HomeworkQuestion]) -> dict[str, object]:
    """构造 doExam API 响应（session.exam_do 返回 rt 对象，与 doHomework 返回完整响应不同）

    do_exam 在 API 层已提取 result["rt"]，故 mock 返回 rt 对象本身（含 examBase）。
    结构与 doHomework 的 rt 一致：rt.examBase.workExamParts[].questionDtos[]
    """
    question_dtos = []
    for q in questions:
        q_dict: dict[str, object] = {
            "eid": q.eid,
            "id": q.id,
            "name": q.name,
            "questionType": {"id": q.question_type_id, "name": "单选题"},
            "questionOptions": [{"id": o.id, "content": o.content} for o in q.question_options],
            "questionScore": q.question_score,
            "result": None,
        }
        question_dtos.append(q_dict)

    return {
        "examBase": {
            "id": "eAqdKONe",
            "name": "思想道德与法治教程试卷",
            "courseName": "思想道德与法治",
            "toChapter": None,
            "problemNum": len(questions),
            "totalScore": "100",
            "workExamParts": [
                {
                    "startSort": 1,
                    "questionCount": len(questions),
                    "questionDtos": question_dtos,
                }
            ],
        },
        "score": None,
        "state": None,
    }


# ---------------------------------------------------------------------------
# _save_answer 测试
# ---------------------------------------------------------------------------


class TestExamWorkerSaveAnswer:
    """保存答案测试"""

    def test_save_answer_calls_exam_save_answer(self) -> None:
        """保存答案调用 session.exam_save_answer（而非 homework_save_answer）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = ExamWorker(session, config, cache)

        exam = _make_exam()
        question = _make_question()

        worker._save_answer(question, 103, exam, "394787", "625")

        session.exam_save_answer.assert_called_once()
        session.homework_save_answer.assert_not_called()

    def test_save_answer_exam_type_is_1(self) -> None:
        """考试 saveStudentAnswer 的 examType=1（整数，非空字符串）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = ExamWorker(session, config, cache)

        exam = _make_exam()
        question = _make_question()

        worker._save_answer(question, 103, exam, "394787", "625")

        call_args = session.exam_save_answer.call_args
        answer_item = call_args[0][0]
        assert answer_item["examType"] == 1

    def test_save_answer_includes_exam_fields(self) -> None:
        """保存答案包含 examId/stuExamId/eid/schoolId 等字段"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = ExamWorker(session, config, cache)

        exam = _make_exam()
        question = _make_question()

        worker._save_answer(question, 103, exam, "394787", "625")

        call_args = session.exam_save_answer.call_args
        answer_item = call_args[0][0]
        assert answer_item["examId"] == "eAqdKONe"
        assert answer_item["stuExamId"] == "edJddjZE"
        assert answer_item["eid"] == "abc123=="
        assert answer_item["schoolId"] == "625"
        assert answer_item["recruitId"] == "394787"
        assert answer_item["answer"] == 103
        assert answer_item["questionType"] == 1
        assert answer_item["fromType"] == 3

    def test_save_answer_no_eid_raises(self) -> None:
        """题目无 eid 时抛出异常"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = ExamWorker(session, config, cache)

        from zhs.exceptions import ZhsError

        exam = _make_exam()
        question = _make_question(eid=None, qid=123)

        with pytest.raises(ZhsError):
            worker._save_answer(question, 103, exam, "394787", "625")


# ---------------------------------------------------------------------------
# run_exam 完整流程测试
# ---------------------------------------------------------------------------


class TestRunExam:
    """考试做题完整流程测试"""

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_full_flow(self, mock_sleep: MagicMock) -> None:
        """完整考试流程：doExam → 生成答案 → saveStudentAnswer（不提交）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        session.exam_do.assert_called_once()
        session.exam_save_answer.assert_called_once()
        # 考试不提交
        session.homework_submit.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_no_questions(self, mock_sleep: MagicMock) -> None:
        """无题目时不保存答案"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        session.exam_do.return_value = _make_do_exam_response([])

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        session.exam_save_answer.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_multiple_questions(self, mock_sleep: MagicMock) -> None:
        """多题考试：每题都保存"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        q1 = _make_question(eid="eid1==")
        q2 = _make_question(eid="eid2==", question_type_id=14)  # 判断题
        session.exam_do.return_value = _make_do_exam_response([q1, q2])
        session.exam_save_answer.return_value = {"statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        assert session.exam_save_answer.call_count == 2

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_save_fails_continues(self, mock_sleep: MagicMock) -> None:
        """保存答案失败继续下一题"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        q1 = _make_question(eid="eid1==")
        q2 = _make_question(eid="eid2==")
        session.exam_do.return_value = _make_do_exam_response([q1, q2])
        session.exam_save_answer.side_effect = [Exception("save error"), {"statu": "1"}]

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        # 两题都尝试保存（第一题失败，第二题成功）
        assert session.exam_save_answer.call_count == 2

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_no_submit(self, mock_sleep: MagicMock) -> None:
        """考试不调用 homework_submit"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        session.homework_submit.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_run_exam_with_cache_correct(self, mock_sleep: MagicMock) -> None:
        """使用缓存正确选项答题"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        cache.mark_correct(1000083416, "eAqdKONe", "abc123==", [103])

        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        # 验证使用了缓存答案 103
        call_args = session.exam_save_answer.call_args
        answer_item = call_args[0][0]
        assert answer_item["answer"] == 103


# ---------------------------------------------------------------------------
# 源感知延迟测试
# ---------------------------------------------------------------------------


class TestSourceAwareSleep:
    """源感知延迟：仅缓存/随机答案延迟，LLM 不延迟"""

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_cache_answer_sleeps(self, mock_sleep: MagicMock) -> None:
        """缓存答案触发延迟（避免 API 限流）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        cache.mark_correct(1000083416, "eAqdKONe", "abc123==", [103])

        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        # 缓存答案应该触发 sleep
        assert mock_sleep.called

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_llm_answer_no_sleep(self, mock_sleep: MagicMock) -> None:
        """LLM 答案不触发延迟（LLM API 本身已有延迟）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        # 模拟 LLM
        mock_llm = MagicMock()
        mock_llm.single_choice.return_value = [103]
        worker = ExamWorker(session, config, cache, llm=mock_llm)

        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        # LLM 答案不应该触发 sleep
        mock_sleep.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_no_llm_random_answer_sleeps(self, mock_sleep: MagicMock) -> None:
        """无 LLM 时随机答案触发延迟"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}

        # 不传 LLM，使用随机答题
        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")

        # 随机答案应该触发 sleep
        assert mock_sleep.called


class TestExamWorkerSubmit:
    """考试提交测试（submit）"""

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_submit_true_calls_exam_submit(self, mock_sleep: MagicMock) -> None:
        """submit=True 时调用 session.exam_submit"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}
        session.exam_submit.return_value = {"msg": "提交成功", "statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625", submit=True)

        session.exam_submit.assert_called_once()
        call_kwargs = session.exam_submit.call_args.kwargs
        assert call_kwargs["recruit_id"] == "394787"
        assert call_kwargs["exam_id"] == "eAqdKONe"
        assert call_kwargs["stu_exam_id"] == "edJddjZE"
        assert call_kwargs["achieve_count"] == "1"  # 1 题已答

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_submit_false_does_not_call_exam_submit(self, mock_sleep: MagicMock) -> None:
        """submit=False（默认）不调用 session.exam_submit"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}
        session.exam_submit.return_value = {"msg": "提交成功", "statu": "1"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625")  # 默认 submit=False

        session.exam_submit.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_submit_with_zero_answers_does_not_submit(self, mock_sleep: MagicMock) -> None:
        """submit=True 但 0 题已答时不提交"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        # 无题目 → answer_count=0
        session.exam_do.return_value = _make_do_exam_response([])

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        worker.run_exam(exam, "394787", "625", submit=True)

        session.exam_submit.assert_not_called()

    @patch("zhs.zhidao.exam.worker.time.sleep")
    def test_submit_failure_does_not_raise(self, mock_sleep: MagicMock) -> None:
        """提交失败时不抛出异常（仅记录错误，提示手动提交）"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.exam_do.return_value = _make_do_exam_response([question])
        session.exam_save_answer.return_value = {"statu": "1"}
        session.exam_submit.side_effect = Exception("submit error")

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()
        # 不应抛出异常
        result = worker.run_exam(exam, "394787", "625", submit=True)
        assert result == 1  # 答案仍已保存

    def test_submit_exam_raises_on_bad_statu(self) -> None:
        """_submit_exam 在 statu != '1' 时抛出 ZhsError"""
        from zhs.exceptions import ZhsError

        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        session.exam_submit.return_value = {"msg": "提交失败", "statu": "0"}

        worker = ExamWorker(session, config, cache)
        exam = _make_exam()

        try:
            worker._submit_exam(exam, "394787", 5)
            assert False, "Should have raised ZhsError"
        except ZhsError:
            pass

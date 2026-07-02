"""知到作业做题器测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.config import AppConfig, HomeworkConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.models import (
    HomeworkItem,
    HomeworkQuestion,
    HomeworkQuestionOption,
)
from zhs.zhidao.homework.worker import HomeworkWorker


def _make_mock_session() -> MagicMock:
    """创建 mock session"""
    session = MagicMock(spec=ZhsSession)
    session.urls.homework = "https://studentexam-api.zhihuishu.com"
    session.ai_analysis_run.return_value = ""
    return session


def _make_config(
    homework_threshold: int = 100,
    max_submit: int = 3,
) -> AppConfig:
    """创建测试配置"""
    return AppConfig(homework=HomeworkConfig(threshold=homework_threshold, max_submit=max_submit))


def _make_cache(tmp_path: Path | None = None) -> ZhidaoHomeworkCache:
    """创建测试缓存"""
    # SQLite 版需要真实路径，无 tmp_path 时用 tempfile 创建
    import tempfile

    cache_dir = tmp_path if tmp_path else Path(tempfile.mkdtemp(prefix="zhs_test_"))
    return ZhidaoHomeworkCache(cache_dir=cache_dir)


def _make_item(**overrides: object) -> HomeworkItem:
    """创建测试作业项"""
    data = {
        "id": "hw1",
        "examId": "exam1",
        "state": 1,
        "score": None,
        "isMarking": 0,
        "backNum": 3,
        "courseId": 100,
        "courseName": "测试课程",
        "examName": "第一章测试",
        "totalScore": "10",
        "problemNum": 2,
    }
    data.update(overrides)
    return HomeworkItem.model_validate(data)


def _make_question(
    eid: str | None = "abc123==",
    qid: int | None = None,
    question_type_id: int = 1,
    options: list[dict[str, object]] | None = None,
) -> HomeworkQuestion:
    """创建测试题目"""
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


def _make_do_homework_response(questions: list[HomeworkQuestion]) -> dict[str, object]:
    """构造 doHomework API 响应"""
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
        "rt": {
            "examBase": {
                "id": "exam1",
                "name": "第一章测试",
                "courseName": "测试课程",
                "toChapter": "第一章",
                "problemNum": len(questions),
                "totalScore": "10",
                "workExamParts": [
                    {
                        "startSort": 1,
                        "questionCount": len(questions),
                        "questionDtos": question_dtos,
                    }
                ],
            },
            "score": None,
            "state": 1,
        },
        "status": "200",
    }


def _make_submit_response(score: str = "8") -> dict[str, object]:
    """构造 submit API 响应"""
    return {
        "rt": {"msg": "提交成功", "score": score, "statu": "0"},
        "status": "200",
    }


def _make_look_response(questions: list[dict[str, object]]) -> dict[str, object]:
    """构造 lookHomework API 响应"""
    return {
        "rt": {
            "examBase": {
                "id": "exam1",
                "name": "第一章测试",
                "courseName": "测试课程",
                "toChapter": "第一章",
                "problemNum": len(questions),
                "totalScore": "10",
                "workExamParts": [
                    {
                        "startSort": 1,
                        "questionCount": len(questions),
                        "questionDtos": questions,
                    }
                ],
            },
            "score": "5",
            "state": 4,
        },
        "status": "200",
    }


def _setup_check_result_mocks(
    session: MagicMock,
    *,
    is_correct: bool = True,
    answer_option_id: int = 102,
) -> None:
    """设置 lookHomework + getStuAnswerInfo 的 mock 返回值

    Args:
        is_correct: 答案是否正确（isCurrent="1" 为正确）
        answer_option_id: 学生选择的选项 ID
    """
    session.homework_look.return_value = _make_look_response(
        [
            {
                "id": 1001,
                "eid": "abc123==",
                "name": "题目1",
                "questionType": {"id": 1, "name": "单选题"},
                "questionOptions": [
                    {"id": 101, "content": "A"},
                    {"id": 102, "content": "B"},
                ],
                "questionScore": "5",
                "result": None,
            },
        ]
    )
    session.homework_get_answer.return_value = {
        "rt": {
            "1001": {
                "questionId": "1001",
                "answer": str(answer_option_id),
                "isCurrent": "1" if is_correct else "0",
                "score": "5" if is_correct else "0",
                "stuExamId": "hw1",
            },
        },
        "status": "200",
    }


class TestSaveOptionsToCache:
    """_save_options_to_cache 测试（含 course_name 传递）"""

    def test_save_options_passes_course_name(self) -> None:
        """_save_options_to_cache 传 item.course_name 到 cache.save_options"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item(courseName="计算机网络")
        question = _make_question(eid="eid1==", qid=42)

        with patch.object(cache, "save_options") as mock_save:
            worker._save_options_to_cache(question, item)

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs["course_name"] == "计算机网络"

    def test_save_options_persists_course_name_to_db(self) -> None:
        """_save_options_to_cache 实际写入 DB 后 course_name 非空"""
        import sqlite3

        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item(courseName="数据结构")
        question = _make_question(eid="eid2==", qid=99)

        worker._save_options_to_cache(question, item)

        # 直接查 DB 验证 course_name
        conn = sqlite3.connect(cache._cache_dir / "questions_bank.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT course_name FROM zhidao_questions WHERE course_id=? AND eid=?",
            (item.course_id, "eid2=="),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["course_name"] == "数据结构"


class TestHomeworkWorkerSaveAnswer:
    """保存答案测试"""

    def test_save_answer_calls_session(self) -> None:
        """保存答案调用 session.homework_save_answer"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item()
        question = _make_question()

        worker._save_answer(question, 103, item, "414804", "625")

        session.homework_save_answer.assert_called_once()
        call_args = session.homework_save_answer.call_args
        answer_item = call_args[0][0]  # 第一个位置参数
        assert answer_item["eid"] == "abc123=="
        assert answer_item["answer"] == 103
        assert answer_item["questionType"] == 1
        assert answer_item["examId"] == "exam1"
        assert answer_item["stuExamId"] == "hw1"

    def test_save_answer_multi_choice_string(self) -> None:
        """多选题保存逗号分隔字符串"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item()
        question = _make_question(question_type_id=2)

        worker._save_answer(question, "101,103", item, "414804", "625")

        call_args = session.homework_save_answer.call_args
        answer_item = call_args[0][0]
        assert answer_item["answer"] == "101,103"
        assert answer_item["questionType"] == 2

    def test_save_answer_no_eid_raises(self) -> None:
        """题目无 eid 时抛出异常"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        from zhs.exceptions import ZhsError

        item = _make_item()
        question = _make_question(eid=None, qid=123)

        try:
            worker._save_answer(question, 103, item, "414804", "625")
            assert False, "Should have raised ZhsError"
        except ZhsError:
            pass


class TestHomeworkWorkerSubmit:
    """提交作业测试"""

    def test_submit_returns_score_rate(self) -> None:
        """提交返回得分率"""
        session = _make_mock_session()
        session.homework_submit.return_value = _make_submit_response("8")
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item()
        rate = worker._submit(item, "414804", 5)

        assert rate == 80.0  # 8/10 * 100

    def test_submit_zero_score(self) -> None:
        """提交零分"""
        session = _make_mock_session()
        session.homework_submit.return_value = _make_submit_response("0")
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item()
        rate = worker._submit(item, "414804", 5)

        assert rate == 0.0

    def test_submit_full_score(self) -> None:
        """提交满分"""
        session = _make_mock_session()
        session.homework_submit.return_value = _make_submit_response("10")
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        item = _make_item()
        rate = worker._submit(item, "414804", 5)

        assert rate == 100.0


class TestHomeworkWorkerDoHomework:
    """完整做作业流程测试"""

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_do_homework_full_flow(self, mock_sleep: MagicMock) -> None:
        """完整做作业流程"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("8")

        worker = HomeworkWorker(session, config, cache)
        item = _make_item()
        rate = worker.do_homework(item, "414804", "625")

        assert rate == 80.0
        session.homework_do.assert_called_once()
        session.homework_save_answer.assert_called_once()
        session.homework_submit.assert_called_once()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_do_homework_no_questions(self, mock_sleep: MagicMock) -> None:
        """无题目返回 0"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        session.homework_do.return_value = _make_do_homework_response([])

        worker = HomeworkWorker(session, config, cache)
        item = _make_item()
        rate = worker.do_homework(item, "414804", "625")

        assert rate == 0.0
        session.homework_save_answer.assert_not_called()
        session.homework_submit.assert_not_called()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_do_homework_multiple_questions(self, mock_sleep: MagicMock) -> None:
        """多题做作业"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        q1 = _make_question(eid="eid1==")
        q2 = _make_question(eid="eid2==", question_type_id=14)  # 判断题
        session.homework_do.return_value = _make_do_homework_response([q1, q2])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("10")

        worker = HomeworkWorker(session, config, cache)
        item = _make_item()
        rate = worker.do_homework(item, "414804", "625")

        assert rate == 100.0
        assert session.homework_save_answer.call_count == 2

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_do_homework_save_fails_continues(self, mock_sleep: MagicMock) -> None:
        """保存答案失败继续下一题"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        q1 = _make_question(eid="eid1==")
        q2 = _make_question(eid="eid2==")
        session.homework_do.return_value = _make_do_homework_response([q1, q2])

        # 第一题保存失败，第二题成功
        session.homework_save_answer.side_effect = [Exception("save error"), {"status": "200"}]
        session.homework_submit.return_value = _make_submit_response("2")

        worker = HomeworkWorker(session, config, cache)
        item = _make_item()
        rate = worker.do_homework(item, "414804", "625")

        # 只有第二题保存成功，提交 1 题
        assert rate == 20.0  # 2/10 * 100

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_do_homework_with_cache_correct(self, mock_sleep: MagicMock) -> None:
        """使用缓存正确选项做作业"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        question = _make_question()
        cache.mark_correct(100, "exam1", "abc123==", [103])

        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("10")

        worker = HomeworkWorker(session, config, cache)
        item = _make_item()
        worker.do_homework(item, "414804", "625")

        # 验证使用了缓存答案 103
        call_args = session.homework_save_answer.call_args
        answer_item = call_args[0][0]
        assert answer_item["answer"] == 103


class TestHomeworkWorkerRandomAnswer:
    """随机答案测试"""

    def test_random_single_choice(self) -> None:
        """单选题随机选择"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        question = _make_question()
        answer = worker._random_answer(question)
        assert answer in (101, 102, 103, 104)

    def test_random_judge(self) -> None:
        """判断题随机选择"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        question = _make_question(question_type_id=14)
        answer = worker._random_answer(question)
        assert answer in (101, 102, 103, 104)

    def test_random_multi_choice(self) -> None:
        """多选题随机选择"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        question = _make_question(question_type_id=2)
        answer = worker._random_answer(question)
        # 应为逗号分隔的字符串
        assert isinstance(answer, str)
        ids = [int(x) for x in answer.split(",")]
        assert len(ids) >= 2

    def test_random_fill_blank_returns_none(self) -> None:
        """填空题随机返回 None"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        question = _make_question(question_type_id=3, options=[])
        answer = worker._random_answer(question)
        assert answer is None

    def test_random_no_options_returns_none(self) -> None:
        """无选项返回 None"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache)

        question = _make_question(options=[])
        answer = worker._random_answer(question)
        assert answer is None


class TestQuestionBankInjection:
    """题库注入：LLM 启用时查题库作为参考"""

    def _make_worker_with_llm(self, bank: object | None = None) -> tuple[HomeworkWorker, MagicMock]:
        """创建带 mock LLM 的 worker，返回 (worker, mock_llm)"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        mock_llm = MagicMock()
        worker = HomeworkWorker(session, config, cache, llm=mock_llm)
        worker._question_bank = bank  # type: ignore[assignment]
        return worker, mock_llm

    def test_bank_none_no_injection(self) -> None:
        """question_bank=None 时 LLM extra 不含 题库参考"""
        worker, mock_llm = self._make_worker_with_llm(bank=None)
        mock_llm.single_choice.return_value = [101]
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        extra = mock_llm.single_choice.call_args.kwargs["extra"]
        assert "题库参考" not in extra

    def test_bank_hit_injects_hint(self) -> None:
        """题库命中时注入 extra["题库参考"]"""
        from zhs.question_bank.models import QuestionBankResult

        mock_bank = MagicMock()
        mock_bank.query.return_value = QuestionBankResult(answer="选项A", times=10, ai=False)
        worker, mock_llm = self._make_worker_with_llm(bank=mock_bank)
        mock_llm.single_choice.return_value = [101]
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        extra = mock_llm.single_choice.call_args.kwargs["extra"]
        assert "题库参考" in extra
        assert "选项A" in extra["题库参考"]
        mock_bank.query.assert_called_once()

    def test_bank_no_answer_no_injection(self) -> None:
        """题库无答案（返回 None）时不注入"""
        mock_bank = MagicMock()
        mock_bank.query.return_value = None
        worker, mock_llm = self._make_worker_with_llm(bank=mock_bank)
        mock_llm.single_choice.return_value = [101]
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        extra = mock_llm.single_choice.call_args.kwargs["extra"]
        assert "题库参考" not in extra

    def test_bank_error_no_injection(self) -> None:
        """题库查询异常时捕获，不注入，LLM 正常调用"""
        mock_bank = MagicMock()
        mock_bank.query.side_effect = Exception("network error")
        worker, mock_llm = self._make_worker_with_llm(bank=mock_bank)
        mock_llm.single_choice.return_value = [101]
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        extra = mock_llm.single_choice.call_args.kwargs["extra"]
        assert "题库参考" not in extra

    def test_no_llm_skips_bank(self) -> None:
        """_llm=None 时不查题库（直接随机）"""
        mock_bank = MagicMock()
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        worker = HomeworkWorker(session, config, cache, llm=None)
        worker._question_bank = mock_bank
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        mock_bank.query.assert_not_called()

    def test_bank_query_params(self) -> None:
        """题库查询参数：title=题目文本, options=选项, type=题型"""
        from zhs.question_bank.models import QuestionBankResult

        mock_bank = MagicMock()
        mock_bank.query.return_value = QuestionBankResult(answer="选项A", times=10)
        worker, _ = self._make_worker_with_llm(bank=mock_bank)
        question = _make_question()
        item = _make_item()

        worker._generate_answer_with_llm(question, item)

        call = mock_bank.query.call_args
        assert call.args[0] == "测试题目"  # title
        assert "选项A" in call.args[1]  # options
        assert call.args[2] == "single"  # qtype


class TestHomeworkWorkerRunHomework:
    """完整流程测试（做 → 提交 → 检查 → 重做循环）"""

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_achieved_first_try(self, mock_sleep: MagicMock) -> None:
        """首次做即达标，无需重做，但仍检查对错写入缓存"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("9")  # 90%

        # 提交后检查对错（首次做也检查）
        _setup_check_result_mocks(session, is_correct=True)

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # 提交后应调用 lookHomework 检查对错并写入缓存
        session.homework_look.assert_called_once()
        # 不应调用 homework_redo（达标了不需要重做）
        session.homework_redo.assert_not_called()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_redo_once(self, mock_sleep: MagicMock) -> None:
        """首次未达标，重做一次后达标"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        # 第一次提交 50%，重做后提交 90%
        session.homework_submit.side_effect = [
            _make_submit_response("5"),
            _make_submit_response("9"),
        ]

        # lookHomework + getStuAnswerInfo 返回（两次提交都检查，答错了）
        _setup_check_result_mocks(session, is_correct=False, answer_option_id=101)

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # 应调用了两次 lookHomework（首次 + 重做后各检查一次）
        assert session.homework_look.call_count == 2
        # 应调用了两次 submit
        assert session.homework_submit.call_count == 2
        # 重做时应调用 homework_redo
        session.homework_redo.assert_called_once()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_no_redo_no_backnum(self, mock_sleep: MagicMock) -> None:
        """无剩余重做次数，不重做，但仍检查对错写入缓存"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("5")  # 50%

        # 提交后检查对错
        _setup_check_result_mocks(session, is_correct=False, answer_option_id=101)

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=0, isMarking=1)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 50.0
        # 提交后应调用 lookHomework 检查对错
        session.homework_look.assert_called_once()
        session.homework_redo.assert_not_called()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_no_redo_max_submit(self, mock_sleep: MagicMock) -> None:
        """已达最大重做次数，不重做，但仍检查对错写入缓存"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80, max_submit=1)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("5")

        # 提交后检查对错
        _setup_check_result_mocks(session, is_correct=False, answer_option_id=101)

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=1)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 50.0
        # 提交后应调用 lookHomework 检查对错
        session.homework_look.assert_called_once()
        session.homework_redo.assert_not_called()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_state4_calls_redo_first(self, mock_sleep: MagicMock) -> None:
        """state=4 的已提交作业，先调用 redo 重置状态"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("9")  # 90%

        # 提交后检查对错
        _setup_check_result_mocks(session, is_correct=True)

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(state=4, backNum=3, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # state=4 时应先调用 homework_redo
        session.homework_redo.assert_called_once()
        # 提交后应调用 lookHomework 检查对错
        session.homework_look.assert_called_once()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_prints_bank_stats(self, mock_sleep: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """run_homework 结束时 print 题库使用统计"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()

        # Mock 题库 client with usage stats
        mock_bank = MagicMock()
        mock_bank.get_usage_stats.return_value = (3, 5)  # 成功 3 次，总查询 5 次

        worker = HomeworkWorker(session, config, cache, question_bank=mock_bank)
        item = _make_item()

        # Mock do_homework + check_and_cache
        worker.do_homework = MagicMock(return_value=90.0)
        worker._check_and_cache = MagicMock()

        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        captured = capsys.readouterr()
        # 验证 print 输出包含"题库使用"和统计数字
        assert "题库" in captured.out
        assert "3" in captured.out
        assert "5" in captured.out

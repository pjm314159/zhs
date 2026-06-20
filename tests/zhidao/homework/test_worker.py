"""知到作业做题器测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from zhs.config import AppConfig, HomeworkConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.cache import HomeworkCache
from zhs.zhidao.homework.models import (
    HomeworkItem,
    HomeworkQuestion,
    HomeworkQuestionOption,
)
from zhs.zhidao.homework.worker import HomeworkWorker, _strip_html


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


def _make_cache(tmp_path: Path | None = None) -> HomeworkCache:
    """创建测试缓存"""
    return HomeworkCache(cache_dir=tmp_path) if tmp_path else HomeworkCache(cache_dir=MagicMock())


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


class TestStripHtml:
    """HTML 标签移除测试"""

    def test_plain_text(self) -> None:
        assert _strip_html("hello") == "hello"

    def test_html_tags(self) -> None:
        assert _strip_html("<p>hello</p>") == "hello"

    def test_html_with_entities(self) -> None:
        # _strip_html 只移除标签，不处理 HTML entities
        assert _strip_html("<p>2026年&nbsp;&nbsp;毕业生</p>") == "2026年&nbsp;&nbsp;毕业生"


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


class TestHomeworkWorkerRunHomework:
    """完整流程测试（做 → 提交 → 检查 → 重做循环）"""

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_achieved_first_try(self, mock_sleep: MagicMock) -> None:
        """首次做即达标，无需重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("9")  # 90%

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # 不应调用 lookHomework（达标了不需要检查）
        session.homework_look.assert_not_called()
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

        # lookHomework 返回
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

        # getStuAnswerInfo 返回（答错了）
        session.homework_get_answer.return_value = {
            "rt": {
                "1001": {
                    "questionId": "1001",
                    "answer": "101",
                    "isCurrent": "0",
                    "score": "0",
                    "stuExamId": "hw1",
                },
            },
            "status": "200",
        }

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # 应调用了一次 lookHomework
        session.homework_look.assert_called_once()
        # 应调用了两次 submit
        assert session.homework_submit.call_count == 2
        # 重做时应调用 homework_redo
        session.homework_redo.assert_called_once()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_no_redo_no_backnum(self, mock_sleep: MagicMock) -> None:
        """无剩余重做次数，不重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("5")  # 50%

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=0, isMarking=1)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 50.0
        session.homework_look.assert_not_called()
        session.homework_redo.assert_not_called()

    @patch("zhs.zhidao.homework.worker.time.sleep")
    def test_run_homework_no_redo_max_submit(self, mock_sleep: MagicMock) -> None:
        """已达最大重做次数，不重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80, max_submit=1)
        cache = _make_cache()

        question = _make_question()
        session.homework_do.return_value = _make_do_homework_response([question])
        session.homework_save_answer.return_value = {"status": "200"}
        session.homework_submit.return_value = _make_submit_response("5")

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(backNum=2, isMarking=1)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 50.0
        session.homework_look.assert_not_called()
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

        worker = HomeworkWorker(session, config, cache)
        item = _make_item(state=4, backNum=3, isMarking=0)
        rate = worker.run_homework(item, "414804", "625")

        assert rate == 90.0
        # state=4 时应先调用 homework_redo
        session.homework_redo.assert_called_once()

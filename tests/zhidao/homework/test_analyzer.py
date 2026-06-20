"""知到作业错题分析器测试"""

from pathlib import Path
from unittest.mock import MagicMock

from zhs.config import AppConfig, HomeworkConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.analyzer import HomeworkAnalyzer
from zhs.zhidao.homework.cache import HomeworkCache
from zhs.zhidao.homework.models import (
    HomeworkAnswerInfo,
    HomeworkItem,
    HomeworkQuestion,
    HomeworkQuestionOption,
)


def _make_mock_session() -> MagicMock:
    """创建 mock session"""
    session = MagicMock(spec=ZhsSession)
    session.urls.homework = "https://studentexam-api.zhihuishu.com"
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
        "state": 4,
        "score": "5",
        "isMarking": 1,
        "backNum": 2,
        "courseId": 100,
        "courseName": "测试课程",
        "examName": "第一章测试",
        "totalScore": "10",
        "problemNum": 2,
    }
    data.update(overrides)
    return HomeworkItem.model_validate(data)


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


def _make_answer_info_response(answers: dict[str, dict[str, str]]) -> dict[str, object]:
    """构造 getStuAnswerInfo API 响应"""
    return {
        "rt": answers,
        "status": "200",
    }


class TestHomeworkAnalyzerCheckResult:
    """检查结果测试"""

    def test_check_result_correct_and_wrong(self) -> None:
        """检查结果包含正确和错误题目"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()

        look_resp = _make_look_response(
            [
                {
                    "id": 1001,
                    "eid": None,
                    "name": "题目1",
                    "questionType": {"id": 1, "name": "单选题"},
                    "questionOptions": [
                        {"id": 101, "content": "A"},
                        {"id": 102, "content": "B"},
                    ],
                    "questionScore": "5",
                    "result": None,
                },
                {
                    "id": 1002,
                    "eid": None,
                    "name": "题目2",
                    "questionType": {"id": 1, "name": "单选题"},
                    "questionOptions": [
                        {"id": 201, "content": "C"},
                        {"id": 202, "content": "D"},
                    ],
                    "questionScore": "5",
                    "result": None,
                },
            ]
        )

        answer_resp = _make_answer_info_response(
            {
                "1001": {
                    "score": "5",
                    "isCurrent": "1",
                    "questionId": "1001",
                    "answer": "101",
                    "stuExamId": "123",
                },
                "1002": {
                    "score": "0",
                    "isCurrent": "0",
                    "questionId": "1002",
                    "answer": "201",
                    "stuExamId": "123",
                },
            }
        )

        session.homework_look.return_value = look_resp
        session.homework_get_answer.return_value = answer_resp

        questions, answers = analyzer.check_result(item, "414804", "625")

        assert len(questions) == 2
        assert len(answers) == 2
        assert answers["1001"].is_correct
        assert answers["1002"].is_wrong

    def test_check_result_empty_questions(self) -> None:
        """无题目返回空"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        look_resp = _make_look_response([])
        session.homework_look.return_value = look_resp

        questions, answers = analyzer.check_result(item, "414804", "625")
        assert questions == []
        assert answers == {}

    def test_check_result_unanswered(self) -> None:
        """未答题目"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        look_resp = _make_look_response(
            [
                {
                    "id": 1001,
                    "eid": None,
                    "name": "题目1",
                    "questionType": {"id": 1, "name": "单选题"},
                    "questionOptions": [{"id": 101, "content": "A"}],
                    "questionScore": "5",
                    "result": None,
                },
            ]
        )
        answer_resp = _make_answer_info_response(
            {
                "1001": {
                    "score": "",
                    "isCurrent": "",
                    "questionId": "1001",
                    "answer": "",
                    "stuExamId": "123",
                },
            }
        )

        session.homework_look.return_value = look_resp
        session.homework_get_answer.return_value = answer_resp

        questions, answers = analyzer.check_result(item, "414804", "625")
        assert answers["1001"].is_unanswered


class TestHomeworkAnalyzerSaveToCache:
    """保存到缓存测试"""

    def test_save_correct_to_cache(self) -> None:
        """正确题目标记到缓存"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        questions = [
            HomeworkQuestion(
                id=1001,
                eid="eid1==",
                name="题目1",
                questionType=1,
                questionOptions=[HomeworkQuestionOption(id=101, content="A")],
                questionScore="5",
            ),
        ]
        answers = {
            "1001": HomeworkAnswerInfo(
                question_id="1001",
                answer="101",
                is_current="1",
                score="5",
                stu_exam_id="123",
            ),
        }

        analyzer.save_to_cache(item, questions, answers)

        # 验证缓存中标记了正确选项
        correct_eid = cache.get_correct_options(100, "exam1", "eid1==")
        correct_id = cache.get_correct_options(100, "exam1", "1001")
        assert 101 in correct_eid
        assert 101 in correct_id

    def test_save_wrong_to_cache(self) -> None:
        """错误题目标记到缓存"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        questions = [
            HomeworkQuestion(
                id=1001,
                eid="eid1==",
                name="题目1",
                questionType=1,
                questionOptions=[
                    HomeworkQuestionOption(id=101, content="A"),
                    HomeworkQuestionOption(id=102, content="B"),
                ],
                questionScore="5",
            ),
        ]
        answers = {
            "1001": HomeworkAnswerInfo(
                question_id="1001",
                answer="101",
                is_current="0",
                score="0",
                stu_exam_id="123",
            ),
        }

        analyzer.save_to_cache(item, questions, answers)

        # 验证缓存中标记了错误选项
        wrong_eid = cache.get_wrong_options(100, "exam1", "eid1==")
        wrong_id = cache.get_wrong_options(100, "exam1", "1001")
        assert 101 in wrong_eid
        assert 101 in wrong_id

    def test_save_unanswered_skipped(self) -> None:
        """未答题目不处理"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        questions = [
            HomeworkQuestion(
                id=1001,
                eid="eid1==",
                name="题目1",
                questionType=1,
                questionOptions=[HomeworkQuestionOption(id=101, content="A")],
                questionScore="5",
            ),
        ]
        answers = {
            "1001": HomeworkAnswerInfo(
                question_id="1001",
                answer="",
                is_current="",
                score="",
                stu_exam_id="123",
            ),
        }

        analyzer.save_to_cache(item, questions, answers)

        # 未答题目不应有缓存
        correct = cache.get_correct_options(100, "exam1", "eid1==")
        wrong = cache.get_wrong_options(100, "exam1", "eid1==")
        assert correct == []
        assert wrong == []

    def test_save_multi_choice_wrong(self) -> None:
        """多选题错误标记"""
        session = _make_mock_session()
        config = _make_config()
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item()
        questions = [
            HomeworkQuestion(
                id=1001,
                eid="eid1==",
                name="题目1",
                questionType=2,
                questionOptions=[
                    HomeworkQuestionOption(id=101, content="A"),
                    HomeworkQuestionOption(id=102, content="B"),
                    HomeworkQuestionOption(id=103, content="C"),
                ],
                questionScore="5",
            ),
        ]
        answers = {
            "1001": HomeworkAnswerInfo(
                question_id="1001",
                answer="101,102",
                is_current="0",
                score="0",
                stu_exam_id="123",
            ),
        }

        analyzer.save_to_cache(item, questions, answers)

        wrong = cache.get_wrong_options(100, "exam1", "eid1==")
        assert 101 in wrong
        assert 102 in wrong


class TestHomeworkAnalyzerShouldRedo:
    """重做判断测试"""

    def test_should_redo_low_score(self) -> None:
        """低分需要重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100)
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item(backNum=2, isMarking=1)
        assert analyzer.should_redo(item, 50.0) is True

    def test_should_not_redo_achieved(self) -> None:
        """达标不需要重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item(backNum=2, isMarking=1)
        assert analyzer.should_redo(item, 90.0) is False

    def test_should_not_redo_no_retries(self) -> None:
        """无剩余重做次数不重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100)
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item(backNum=0, isMarking=1)
        assert analyzer.should_redo(item, 50.0) is False

    def test_should_not_redo_max_submit(self) -> None:
        """已达最大重做次数不重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100, max_submit=3)
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item(backNum=2, isMarking=3)
        assert analyzer.should_redo(item, 50.0) is False

    def test_should_redo_threshold_80(self) -> None:
        """threshold=80 时 70% 未达标"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        cache = _make_cache()
        analyzer = HomeworkAnalyzer(session, config, cache)

        item = _make_item(backNum=2, isMarking=1)
        assert analyzer.should_redo(item, 70.0) is True


class TestParseAnswerOptionIds:
    """答案解析测试"""

    def test_single_option(self) -> None:
        assert HomeworkAnalyzer._parse_answer_option_ids("440703134") == [440703134]

    def test_multiple_options(self) -> None:
        assert HomeworkAnalyzer._parse_answer_option_ids("440703126,440703127") == [440703126, 440703127]

    def test_empty_string(self) -> None:
        assert HomeworkAnalyzer._parse_answer_option_ids("") == []

    def test_with_spaces(self) -> None:
        assert HomeworkAnalyzer._parse_answer_option_ids("101, 102") == [101, 102]

    def test_invalid_value_skipped(self) -> None:
        assert HomeworkAnalyzer._parse_answer_option_ids("101,abc,102") == [101, 102]

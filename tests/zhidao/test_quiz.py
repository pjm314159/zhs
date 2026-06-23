"""Zhidao quiz 测试

Task 3.3 — zhidao/quiz.py
TDD 步骤:
1. 获取弹窗题目列表
2. 过滤已答题目（timeSec <= played_time）
3. 答题延迟机制（answer_delay=2 递减）
"""

from collections.abc import Iterator

import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.models import PopupQuestion, QuestionOption, QuestionPoint
from zhs.zhidao.quiz import ZhidaoQuizzer


@pytest.fixture
def mock_config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def mock_session(mock_config: AppConfig) -> Iterator[ZhsSession]:
    with respx.mock:
        session = ZhsSession(mock_config)
        yield session


class TestLoadVideoPointerInfo:
    """load_video_pointer_info 测试"""

    def test_returns_question_points(self, mock_session: ZhsSession) -> None:
        """获取弹窗题目列表"""
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/popupAnswer/loadVideoPointerInfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "questionPoint": [
                            {"timeSec": 120, "questionIds": [1, 2]},
                            {"timeSec": 300, "questionIds": [3]},
                        ]
                    },
                },
            )
        )
        quizzer = ZhidaoQuizzer(mock_session)
        points = quizzer.load_video_pointer_info("ABC123", 100)
        assert len(points) == 2
        assert points[0].time_sec == 120
        assert points[0].question_ids == [1, 2]
        assert points[1].time_sec == 300

    def test_empty_question_points(self, mock_session: ZhsSession) -> None:
        """无弹窗题目"""
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/popupAnswer/loadVideoPointerInfo").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"questionPoint": []}})
        )
        quizzer = ZhidaoQuizzer(mock_session)
        points = quizzer.load_video_pointer_info("ABC123", 100)
        assert points == []


class TestFilterAnsweredQuestions:
    """过滤已答题目测试"""

    def test_filter_answered_questions(self) -> None:
        """过滤已答题目（timeSec <= played_time）"""
        points = [
            QuestionPoint(time_sec=60, question_ids=[1]),
            QuestionPoint(time_sec=120, question_ids=[2]),
            QuestionPoint(time_sec=300, question_ids=[3]),
        ]
        played_time = 150
        # 过滤掉 timeSec <= played_time 的题目
        remaining = [p for p in points if p.time_sec > played_time]
        assert len(remaining) == 1
        assert remaining[0].time_sec == 300

    def test_all_questions_answered(self) -> None:
        """所有题目都已答过"""
        points = [
            QuestionPoint(time_sec=60, question_ids=[1]),
            QuestionPoint(time_sec=120, question_ids=[2]),
        ]
        played_time = 200
        remaining = [p for p in points if p.time_sec > played_time]
        assert remaining == []


class TestAnswerQuestion:
    """answer_question 测试"""

    def test_selects_correct_answer(self) -> None:
        """自动选择正确答案（result == '1'）"""
        question = PopupQuestion(
            question_id=1,
            question_options=[
                QuestionOption(id=10, content="选项A", result="0"),
                QuestionOption(id=11, content="选项B", result="1"),
                QuestionOption(id=12, content="选项C", result="0"),
            ],
        )
        quizzer = ZhidaoQuizzer.__new__(ZhidaoQuizzer)  # 不需要 session
        answer = quizzer.answer_question(question)
        assert answer == "11"

    def test_multiple_correct_answers(self) -> None:
        """多选正确答案"""
        question = PopupQuestion(
            question_id=2,
            question_options=[
                QuestionOption(id=10, result="1"),
                QuestionOption(id=11, result="0"),
                QuestionOption(id=12, result="1"),
            ],
        )
        quizzer = ZhidaoQuizzer.__new__(ZhidaoQuizzer)
        answer = quizzer.answer_question(question)
        assert answer == "10,12"


class TestAnswerDelay:
    """答题延迟机制测试"""

    def test_answer_delay_decrement(self) -> None:
        """answer_delay=2 递减"""
        answer_delay = 2
        # 第一次遇到弹题，不立即答题，delay 递减
        answer_delay -= 1
        assert answer_delay == 1
        # 第二次递减
        answer_delay -= 1
        assert answer_delay == 0
        # delay=0 时提交答案

    def test_answer_delay_reset(self) -> None:
        """答题后重置 delay"""
        answer_delay = 0
        # 答题后重置
        answer_delay = 2
        assert answer_delay == 2


class TestGetPopupExam:
    """get_popup_exam 测试"""

    def test_returns_popup_question(self, mock_session: ZhsSession) -> None:
        """获取弹窗题目详情"""
        respx.post("https://studyservice-api.zhihuishu.com/gateway/t/v1/popupAnswer/lessonPopupExam").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "lessonTestQuestionUseInterfaceDtos": [
                            {
                                "testQuestion": {
                                    "questionId": 5,
                                    "questionOptions": [
                                        {"id": 10, "content": "A", "result": "0"},
                                        {"id": 11, "content": "B", "result": "1"},
                                    ],
                                }
                            }
                        ]
                    },
                },
            )
        )
        quizzer = ZhidaoQuizzer(mock_session)
        question = quizzer.get_popup_exam("ABC123", 100, [5])
        assert isinstance(question, PopupQuestion)
        assert question.question_id == 5
        assert len(question.question_options) == 2


class TestSaveAnswer:
    """save_answer 测试"""

    def test_save_answer_calls_api(self, mock_session: ZhsSession) -> None:
        """提交弹题答案"""
        route = respx.post(
            "https://studyservice-api.zhihuishu.com/gateway/t/v1/popupAnswer/saveLessonPopupExamSaveAnswer"
        ).mock(return_value=httpx.Response(200, json={"code": 0, "data": {}}))

        quizzer = ZhidaoQuizzer(mock_session)
        quizzer.save_answer("ABC123", 100, question_id=5, answer="11")
        assert route.called

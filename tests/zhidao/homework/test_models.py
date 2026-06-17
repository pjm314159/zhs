"""知到作业数据模型测试"""

import pytest

from zhs.zhidao.homework.models import (
    HomeworkAnswerInfo,
    HomeworkCacheEntry,
    HomeworkCacheOption,
    HomeworkDetail,
    HomeworkItem,
    HomeworkQuestion,
    HomeworkQuestionType,
)


class TestHomeworkQuestionType:
    """题型枚举测试"""

    def test_values(self) -> None:
        assert HomeworkQuestionType.SINGLE.value == 1
        assert HomeworkQuestionType.MULTI.value == 2
        assert HomeworkQuestionType.FILL.value == 3
        assert HomeworkQuestionType.JUDGE.value == 14

    def test_from_int(self) -> None:
        assert HomeworkQuestionType(1) == HomeworkQuestionType.SINGLE
        assert HomeworkQuestionType(14) == HomeworkQuestionType.JUDGE

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            HomeworkQuestionType(99)


class TestHomeworkItem:
    """作业列表项测试"""

    def test_from_api_data(self) -> None:
        """从 API 响应数据构造"""
        data = {
            "id": "wMqNNxQp",
            "examId": "5kNKk0qe",
            "state": 1,
            "score": None,
            "isMarking": 0,
            "backNum": 3,
            "courseId": 1000008156,
            "courseName": "形势与政策",
            "examName": "第一章单元测试",
            "cpOrderNumber": "第一章",
            "chapterId": 1001283586,
            "totalScore": "10",
            "problemNum": 5,
        }
        item = HomeworkItem.model_validate(data)
        assert item.id == "wMqNNxQp"
        assert item.exam_id == "5kNKk0qe"
        assert item.state == 1
        assert item.score is None
        assert item.course_id == 1000008156
        assert item.total_score == "10"
        assert item.back_num == 3
        assert item.is_marking == 0

    def test_submitted_item(self) -> None:
        """已提交作业"""
        data = {
            "id": "abc123",
            "examId": "exam1",
            "state": 4,
            "score": "8",
            "isMarking": 2,
            "backNum": 1,
            "courseId": 100,
            "courseName": "测试课程",
            "examName": "第二章测试",
            "totalScore": "10",
        }
        item = HomeworkItem.model_validate(data)
        assert item.state == 4
        assert item.score == "8"
        assert item.is_marking == 2


class TestHomeworkQuestion:
    """题目详情测试"""

    def test_from_dohomework(self) -> None:
        """doHomework 返回的题目（含 eid）"""
        data = {
            "id": None,
            "eid": "KSOe9/zfDihaLT7T3DBHJw==",
            "name": "<p>题目内容</p>",
            "questionType": {"id": 1, "name": "单选题"},
            "questionOptions": [
                {"id": 440703135, "content": "选项A"},
                {"id": 440703136, "content": "选项B"},
            ],
            "questionScore": "2",
            "result": None,
        }
        q = HomeworkQuestion.model_validate(data)
        assert q.eid == "KSOe9/zfDihaLT7T3DBHJw=="
        assert q.id is None
        assert len(q.question_options) == 2
        assert q.question_options[0].id == 440703135

    def test_question_type_property(self) -> None:
        """question_type 属性"""
        q = HomeworkQuestion(eid="test", questionType=1)
        assert q.question_type == HomeworkQuestionType.SINGLE

    def test_question_type_invalid(self) -> None:
        """无效题型"""
        q = HomeworkQuestion(eid="test", questionType=99)
        assert q.question_type is None


class TestHomeworkDetail:
    """doHomework/lookHomework 返回测试"""

    def test_from_api_data(self) -> None:
        data = {
            "examBase": {
                "id": "5kNKk0qe",
                "name": "第一章单元测试",
                "courseName": "形势与政策",
                "toChapter": "第一章",
                "problemNum": 5,
                "totalScore": "10",
                "workExamParts": [
                    {
                        "startSort": 1,
                        "questionCount": 5,
                        "questionDtos": [
                            {
                                "eid": "abc==",
                                "questionType": {"id": 1, "name": "单选题"},
                                "questionOptions": [
                                    {"id": 1, "content": "A"},
                                    {"id": 2, "content": "B"},
                                ],
                                "questionScore": "2",
                            }
                        ],
                    }
                ],
            },
            "score": None,
            "state": 4,
        }
        detail = HomeworkDetail.model_validate(data)
        assert detail.exam_base.id == "5kNKk0qe"
        assert len(detail.exam_base.work_exam_parts) == 1
        assert len(detail.exam_base.work_exam_parts[0].question_dtos) == 1


class TestHomeworkAnswerInfo:
    """答案信息测试"""

    def test_correct_answer(self) -> None:
        info = HomeworkAnswerInfo.model_validate({"questionId": "123", "answer": "456", "isCurrent": "1", "score": "2"})
        assert info.is_correct
        assert not info.is_wrong
        assert not info.is_unanswered

    def test_wrong_answer(self) -> None:
        info = HomeworkAnswerInfo.model_validate({"questionId": "123", "answer": "456", "isCurrent": "0", "score": "0"})
        assert not info.is_correct
        assert info.is_wrong
        assert not info.is_unanswered

    def test_unanswered(self) -> None:
        info = HomeworkAnswerInfo.model_validate({"questionId": "123", "answer": "", "isCurrent": "", "score": ""})
        assert not info.is_correct
        assert not info.is_wrong
        assert info.is_unanswered


class TestHomeworkCacheEntry:
    """缓存条目测试"""

    def test_create(self) -> None:
        entry = HomeworkCacheEntry(
            questionType=1,
            options=[HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            correctOptions=[1],
            wrongOptions=[2],
            lastUpdated="2026-06-16T12:00:00",
        )
        assert entry.question_type == 1
        assert len(entry.correct_options) == 1
        assert entry.correct_options[0] == 1
        assert len(entry.wrong_options) == 1

    def test_default_values(self) -> None:
        entry = HomeworkCacheEntry(questionType=1, lastUpdated="2026-06-16T12:00:00")
        assert entry.correct_options == []
        assert entry.wrong_options == []
        assert entry.ai_analysis is None

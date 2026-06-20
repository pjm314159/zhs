"""知到作业扫描器测试"""

from unittest.mock import MagicMock

from zhs.config import AppConfig, HomeworkConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.models import HomeworkItem
from zhs.zhidao.homework.scanner import HomeworkScanner


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


def _make_homework_response(items: list[dict[str, object]]) -> dict[str, object]:
    """构造 getStudentHomework API 响应"""
    return {
        "rt": {
            "studentHomeworkList": items,
        },
        "status": "200",
    }


# 通用作业数据
UNSUBMITTED_ITEM = {
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
    "problemNum": 5,
}

SUBMITTED_FULL_SCORE = {
    "id": "hw2",
    "examId": "exam2",
    "state": 4,
    "score": "10",
    "isMarking": 1,
    "backNum": 2,
    "courseId": 100,
    "courseName": "测试课程",
    "examName": "第二章测试",
    "totalScore": "10",
    "problemNum": 5,
}

SUBMITTED_LOW_SCORE = {
    "id": "hw3",
    "examId": "exam3",
    "state": 4,
    "score": "5",
    "isMarking": 1,
    "backNum": 2,
    "courseId": 100,
    "courseName": "测试课程",
    "examName": "第三章测试",
    "totalScore": "10",
    "problemNum": 5,
}

SUBMITTED_NO_RETRIES = {
    "id": "hw4",
    "examId": "exam4",
    "state": 4,
    "score": "5",
    "isMarking": 3,
    "backNum": 3,
    "courseId": 100,
    "courseName": "测试课程",
    "examName": "第四章测试",
    "totalScore": "10",
    "problemNum": 5,
}

SUBMITTED_MAX_SUBMIT = {
    "id": "hw5",
    "examId": "exam5",
    "state": 4,
    "score": "5",
    "isMarking": 3,
    "backNum": 5,
    "courseId": 100,
    "courseName": "测试课程",
    "examName": "第五章测试",
    "totalScore": "10",
    "problemNum": 5,
}


class TestHomeworkScanner:
    """扫描器测试"""

    def test_scan_homework(self) -> None:
        """扫描所有作业"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        unsubmitted_resp = _make_homework_response([UNSUBMITTED_ITEM])
        submitted_resp = _make_homework_response([SUBMITTED_FULL_SCORE])
        session.homework_query.side_effect = [unsubmitted_resp, submitted_resp]

        items = scanner.scan_homework("414804", 100)
        assert len(items) == 2
        assert items[0].state == 1
        assert items[1].state == 4

    def test_scan_homework_api_error(self) -> None:
        """API 错误返回空列表"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        session.homework_query.side_effect = Exception("API error")

        items = scanner.scan_homework("414804", 100)
        assert items == []

    def test_scan_homework_empty(self) -> None:
        """无作业"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        empty_resp = _make_homework_response([])
        session.homework_query.side_effect = [empty_resp, empty_resp]

        items = scanner.scan_homework("414804", 100)
        assert items == []

    def test_filter_pending_unsubmitted(self) -> None:
        """未提交作业必须做"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(UNSUBMITTED_ITEM)]
        pending = scanner.filter_pending(items)
        assert len(pending) == 1
        assert pending[0].id == "hw1"

    def test_filter_pending_full_score_skipped(self) -> None:
        """满分作业跳过"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_FULL_SCORE)]
        pending = scanner.filter_pending(items)
        assert len(pending) == 0

    def test_filter_pending_low_score_needs_redo(self) -> None:
        """低分作业需要重做"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_LOW_SCORE)]
        pending = scanner.filter_pending(items)
        assert len(pending) == 1

    def test_filter_pending_no_retries_skipped(self) -> None:
        """无剩余重做次数跳过"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_NO_RETRIES)]
        pending = scanner.filter_pending(items)
        assert len(pending) == 0

    def test_filter_pending_max_submit_skipped(self) -> None:
        """已达最大提交次数跳过"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100, max_submit=3)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_MAX_SUBMIT)]
        pending = scanner.filter_pending(items)
        assert len(pending) == 0

    def test_filter_pending_threshold_80(self) -> None:
        """homework_threshold=80 时 50% 得分率未达标"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=80)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_LOW_SCORE)]  # 5/10 = 50%
        pending = scanner.filter_pending(items)
        assert len(pending) == 1

    def test_filter_pending_threshold_50(self) -> None:
        """homework_threshold=50 时 50% 得分率达标"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=50)
        scanner = HomeworkScanner(session, config)

        items = [HomeworkItem.model_validate(SUBMITTED_LOW_SCORE)]  # 5/10 = 50%
        pending = scanner.filter_pending(items)
        assert len(pending) == 0

    def test_filter_pending_mixed(self) -> None:
        """混合筛选"""
        session = _make_mock_session()
        config = _make_config(homework_threshold=100, max_submit=3)
        scanner = HomeworkScanner(session, config)

        items = [
            HomeworkItem.model_validate(UNSUBMITTED_ITEM),  # 未提交 → 做
            HomeworkItem.model_validate(SUBMITTED_FULL_SCORE),  # 满分 → 跳过
            HomeworkItem.model_validate(SUBMITTED_LOW_SCORE),  # 低分 → 重做
            HomeworkItem.model_validate(SUBMITTED_NO_RETRIES),  # 无重做次数 → 跳过
            HomeworkItem.model_validate(SUBMITTED_MAX_SUBMIT),  # 达最大次数 → 跳过
        ]
        pending = scanner.filter_pending(items)
        assert len(pending) == 2
        assert pending[0].id == "hw1"
        assert pending[1].id == "hw3"

    def test_is_achieved_null_score(self) -> None:
        """score 为 null 时未达标"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        item = HomeworkItem.model_validate(
            {"id": "x", "examId": "y", "state": 4, "score": None, "courseId": 100, "totalScore": "10"}
        )
        assert not scanner._is_achieved(item)

    def test_is_achieved_zero_total(self) -> None:
        """totalScore 为 0 时视为达标"""
        session = _make_mock_session()
        config = _make_config()
        scanner = HomeworkScanner(session, config)

        item = HomeworkItem.model_validate(
            {"id": "x", "examId": "y", "state": 4, "score": "0", "courseId": 100, "totalScore": "0"}
        )
        assert scanner._is_achieved(item)

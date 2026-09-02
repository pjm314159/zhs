"""知到考试扫描器测试"""

from unittest.mock import MagicMock

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.exam.models import ExamInfo
from zhs.zhidao.exam.scanner import ExamScanner


def _make_mock_session() -> MagicMock:
    """创建 mock session"""
    session = MagicMock(spec=ZhsSession)
    session.urls.taurusexam = "https://taurusexam-api.zhihuishu.com"
    return session


def _make_config() -> AppConfig:
    """创建测试配置"""
    return AppConfig()


def _make_exam_dict(
    exam_id: str = "e1",
    *,
    state: int = 1,
    remain: int = 1,
    score: str | None = None,
) -> dict[str, object]:
    """构造 getStudentFinalExam API 响应元素"""
    return {
        "id": exam_id,
        "state": state,
        "score": score,
        "achieveCount": 0,
        "achieve": 0,
        "faStudentExamRemainCount": remain,
        "courseId": 1000083416,
        "courseName": "思想道德与法治",
        "examId": exam_id,
        "examName": "期末考试",
        "problemNum": 80,
        "totalScore": "100",
        "limitTime": 90,
        "startTime": "2026-07-01 00:00:00",
        "endDate": "2026-07-10 23:59:59",
        "studentStartTime": None,
        "studentEndTime": None,
        "submitTime": None,
    }


class TestScanExams:
    """扫描考试列表"""

    def test_scans_uncompleted_and_completed(self) -> None:
        """扫描未完成 + 已完成考试"""
        session = _make_mock_session()
        uncompleted = [_make_exam_dict("e1", state=1, remain=1)]
        completed = [_make_exam_dict("e2", state=1, remain=0, score="80")]

        def exam_list_side_effect(course_id: int, recruit_id: str, flag: int) -> list[dict[str, object]]:
            if flag == 1:
                return uncompleted
            return completed

        session.exam_list.side_effect = exam_list_side_effect

        scanner = ExamScanner(session, _make_config())
        result = scanner.scan_exams(recruit_id="394787", course_id=1000083416)

        assert len(result.uncompleted) == 1
        assert result.uncompleted[0].id == "e1"
        assert len(result.completed) == 1
        assert result.completed[0].id == "e2"
        assert len(result.all) == 2

    def test_scan_returns_examinfo_objects(self) -> None:
        """返回 ExamInfo 对象列表"""
        session = _make_mock_session()
        session.exam_list.side_effect = lambda cid, rid, flag: [_make_exam_dict("e1")] if flag == 1 else []

        scanner = ExamScanner(session, _make_config())
        result = scanner.scan_exams(recruit_id="394787", course_id=1000083416)

        assert isinstance(result.uncompleted[0], ExamInfo)
        assert result.uncompleted[0].exam_id == "e1"
        assert result.uncompleted[0].limit_time == 90

    def test_scan_empty_when_no_exams(self) -> None:
        """无考试时返回空列表"""
        session = _make_mock_session()
        session.exam_list.return_value = []

        scanner = ExamScanner(session, _make_config())
        result = scanner.scan_exams(recruit_id="394787", course_id=1000083416)

        assert result.uncompleted == []
        assert result.completed == []
        assert result.all == []

    def test_scan_calls_exam_list_with_correct_flags(self) -> None:
        """调用 exam_list 时使用正确的 flag 参数"""
        session = _make_mock_session()
        session.exam_list.return_value = []

        scanner = ExamScanner(session, _make_config())
        scanner.scan_exams(recruit_id="394787", course_id=1000083416)

        assert session.exam_list.call_count == 2
        # 第一次 flag=1（未完成），第二次 flag=0（已完成）
        first_call = session.exam_list.call_args_list[0]
        second_call = session.exam_list.call_args_list[1]
        # scanner 调用: exam_list(course_id, recruit_id, flag=flag)
        assert first_call.args[0] == 1000083416  # course_id
        assert first_call.args[1] == "394787"  # recruit_id
        assert first_call.kwargs["flag"] == 1
        assert second_call.kwargs["flag"] == 0

    def test_scan_handles_api_error_gracefully(self) -> None:
        """API 异常时返回空列表（不抛出）"""
        session = _make_mock_session()
        session.exam_list.side_effect = Exception("网络错误")

        scanner = ExamScanner(session, _make_config())
        result = scanner.scan_exams(recruit_id="394787", course_id=1000083416)

        assert result.uncompleted == []
        assert result.completed == []


class TestFilterPending:
    """筛选待处理考试"""

    def test_filters_pending_exams(self) -> None:
        """筛选 state in (1,2) 的考试（不限制剩余次数）"""
        from zhs.zhidao.exam.models import ExamListResult

        result = ExamListResult(
            uncompleted=[
                ExamInfo.from_api(_make_exam_dict("e1", state=1, remain=1)),  # 未开考
                ExamInfo.from_api(_make_exam_dict("e2", state=2, remain=1)),  # 已开考未提交
                ExamInfo.from_api(_make_exam_dict("e3", state=1, remain=0)),  # 无剩余次数但可做
                ExamInfo.from_api(_make_exam_dict("e4", state=4, remain=1)),  # 已提交状态
            ],
            completed=[],
        )
        pending = result.pending
        assert len(pending) == 3
        assert pending[0].id == "e1"
        assert pending[1].id == "e2"
        assert pending[2].id == "e3"

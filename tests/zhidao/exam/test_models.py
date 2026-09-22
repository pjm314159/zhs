"""知到考试数据模型测试"""

from zhs.zhidao.exam.models import ExamInfo, ExamListResult


class TestExamInfo:
    """考试列表项测试"""

    def test_from_api_data(self) -> None:
        """从 API 响应数据构造（驼峰转蛇形）"""
        data = {
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
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-01 00:00:00",
            "endDate": "2026-07-10 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
        }
        info = ExamInfo.from_api(data)
        assert info.id == "edJddjZE"
        assert info.state == 1
        assert info.score is None
        assert info.achieve_count == 0
        assert info.fa_student_exam_remain_count == 1
        assert info.course_id == 1000083416
        assert info.course_name == "思想道德与法治"
        assert info.exam_id == "eAqdKONe"
        assert info.exam_name == "思想道德与法治教程考试"
        assert info.problem_num == 80
        assert info.total_score == "100"
        assert info.limit_time == 90
        assert info.start_time == "2026-07-01 00:00:00"
        assert info.end_date == "2026-07-10 23:59:59"
        assert info.student_start_time is None
        assert info.student_end_time is None
        assert info.submit_time is None

    def test_from_api_with_score(self) -> None:
        """已提交考试（带得分）"""
        data = {
            "id": "edJddjZE",
            "state": 1,
            "score": "76",
            "achieveCount": 1,
            "achieve": 0,
            "faStudentExamRemainCount": 0,
            "courseId": 1000083416,
            "courseName": "思想道德与法治",
            "examId": "eAqdKONe",
            "examName": "思想道德与法治教程考试",
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-01 00:00:00",
            "endDate": "2026-07-10 23:59:59",
            "studentStartTime": "2026-07-02 10:00:00",
            "studentEndTime": "2026-07-02 11:30:00",
            "submitTime": "2026-07-02 11:30:00",
        }
        info = ExamInfo.from_api(data)
        assert info.score == "76"
        assert info.achieve_count == 1
        assert info.fa_student_exam_remain_count == 0
        assert info.student_start_time == "2026-07-02 10:00:00"
        assert info.submit_time == "2026-07-02 11:30:00"

    def test_from_api_defaults(self) -> None:
        """缺失可选字段时使用默认值"""
        data = {
            "id": "x1",
            "state": 1,
            "courseId": 100,
            "courseName": "课程",
            "examId": "e1",
            "examName": "考试",
            "problemNum": 10,
            "totalScore": "50",
            "limitTime": 60,
            "startTime": "2026-01-01 00:00:00",
            "endDate": "2026-12-31 23:59:59",
        }
        info = ExamInfo.from_api(data)
        assert info.score is None
        assert info.achieve_count == 0
        assert info.achieve == 0
        assert info.fa_student_exam_remain_count == 0
        assert info.student_start_time is None
        assert info.student_end_time is None
        assert info.submit_time is None

    def test_from_api_none_achieve_count(self) -> None:
        """achieveCount=null 时转为 0（API 未答题时返回 null）"""
        data = {
            "id": "y7VmgR3D",
            "state": 1,
            "score": None,
            "achieveCount": None,  # API 返回 null
            "achieve": 0,
            "faStudentExamRemainCount": 1,
            "courseId": 1000083416,
            "courseName": "思想道德与法治",
            "examId": "e9XlgxDw",
            "examName": "思想道德与法治教程考试",
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-21 00:00:00",
            "endDate": "2026-07-31 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
        }
        info = ExamInfo.from_api(data)
        assert info.achieve_count == 0  # null → 0
        assert info.id == "y7VmgR3D"
        assert info.exam_name == "思想道德与法治教程考试"

    def test_is_in_progress_by_progress_type(self) -> None:
        """progressType=2 表示已开考未提交"""
        data = {
            "id": "y7VmgR3D",
            "state": 1,
            "score": None,
            "achieveCount": 0,
            "achieve": 0,
            "faStudentExamRemainCount": 1,
            "courseId": 1000083416,
            "courseName": "思想道德与法治",
            "courseType": 1,
            "examId": "e9XlgxDw",
            "examName": "思想道德与法治教程考试",
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-21 00:00:00",
            "endDate": "2026-07-31 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
            "progressType": 2,
            "backStatus": 0,
        }
        info = ExamInfo.from_api(data)
        assert info.progress_type == 2
        assert info.is_in_progress is True

    def test_not_in_progress_by_progress_type(self) -> None:
        """progressType=0 表示未开考"""
        data = {
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
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-01 00:00:00",
            "endDate": "2026-07-10 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
            "progressType": 0,
        }
        info = ExamInfo.from_api(data)
        assert info.progress_type == 0
        assert info.is_in_progress is False

    def test_state_2_is_in_progress(self) -> None:
        """state=2 表示已开考未提交"""
        data = {
            "id": "y7VmgR3D",
            "state": 2,
            "score": None,
            "achieveCount": 0,
            "achieve": 0,
            "faStudentExamRemainCount": 1,
            "courseId": 1000083416,
            "courseName": "思想道德与法治",
            "examId": "e9XlgxDw",
            "examName": "思想道德与法治教程考试",
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-21 00:00:00",
            "endDate": "2026-07-31 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
            "progressType": 0,
        }
        info = ExamInfo.from_api(data)
        assert info.state == 2
        assert info.is_in_progress is True

    def test_is_started_by_student_start_time(self) -> None:
        """studentStartTime 不为空表示已开考"""
        data = {
            "id": "y7VmgR3D",
            "state": 1,
            "score": None,
            "achieveCount": 0,
            "achieve": 0,
            "faStudentExamRemainCount": 1,
            "courseId": 1000083416,
            "courseName": "思想道德与法治",
            "examId": "e9XlgxDw",
            "examName": "思想道德与法治教程考试",
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-21 00:00:00",
            "endDate": "2026-07-31 23:59:59",
            "studentStartTime": "2026-07-21 10:00:00",
            "studentEndTime": None,
            "submitTime": None,
            "progressType": 0,
        }
        info = ExamInfo.from_api(data)
        assert info.is_started is True

    def test_not_started_when_all_empty(self) -> None:
        """studentStartTime=null, progressType=0, state=1 表示未开考"""
        data = {
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
            "problemNum": 80,
            "totalScore": "100",
            "limitTime": 90,
            "startTime": "2026-07-01 00:00:00",
            "endDate": "2026-07-10 23:59:59",
            "studentStartTime": None,
            "studentEndTime": None,
            "submitTime": None,
            "progressType": 0,
        }
        info = ExamInfo.from_api(data)
        assert info.is_started is False


class TestExamListResult:
    """考试列表结果测试"""

    def test_all_combines_uncompleted_and_completed(self) -> None:
        """all 属性合并未完成和已完成"""
        uncompleted = [_make_exam("e1", state=1, remain=1)]
        completed = [_make_exam("e2", state=1, remain=0, score="80")]
        result = ExamListResult(uncompleted=uncompleted, completed=completed)
        assert len(result.all) == 2
        assert result.all[0].id == "e1"
        assert result.all[1].id == "e2"

    def test_pending_filters_state_and_remain(self) -> None:
        """pending 筛选：state in (1,2) 且 studentEndTime 为空"""
        uncompleted = [
            _make_exam("e1", state=1, remain=1),  # 未开考
            _make_exam("e2", state=2, remain=1),  # 已开考未提交
            _make_exam("e3", state=1, remain=0),  # 无剩余次数但可做最后一次
            _make_exam("e4", state=4, remain=1),  # 已提交状态
        ]
        result = ExamListResult(uncompleted=uncompleted, completed=[])
        pending = result.pending
        assert len(pending) == 3
        assert pending[0].id == "e1"
        assert pending[1].id == "e2"
        assert pending[2].id == "e3"

    def test_pending_excludes_ended_exam(self) -> None:
        """studentEndTime 不为空的考试不纳入 pending（考试已结束）"""
        e_ended = _make_exam("e5", state=2, remain=1)
        e_ended.student_end_time = "2026-07-21 11:00:00"
        uncompleted = [
            _make_exam("e1", state=2, remain=1),  # 未结束
            e_ended,  # 已结束
        ]
        result = ExamListResult(uncompleted=uncompleted, completed=[])
        pending = result.pending
        assert len(pending) == 1
        assert pending[0].id == "e1"

    def test_pending_empty_when_no_uncompleted(self) -> None:
        """无未完成考试时 pending 为空"""
        result = ExamListResult(uncompleted=[], completed=[])
        assert result.pending == []


def _make_exam(
    exam_id: str,
    *,
    state: int = 1,
    remain: int = 1,
    score: str | None = None,
) -> ExamInfo:
    """构造测试用 ExamInfo"""
    return ExamInfo(
        id=exam_id,
        state=state,
        score=score,
        achieve_count=0,
        achieve=0,
        fa_student_exam_remain_count=remain,
        course_id=100,
        course_name="测试课程",
        exam_id=exam_id,
        exam_name="测试考试",
        problem_num=10,
        total_score="100",
        limit_time=60,
        start_time="2026-01-01 00:00:00",
        end_date="2026-12-31 23:59:59",
    )

"""ZhidaoExamApi 单元测试

覆盖：
- getStudentFinalExam（考试列表，zhidao_exam 策略）
- getSaveAnswerLockResult（答案锁检查，homework 策略）

位置验证相关接口（queryIsOpenLocation/createEncodeImage/queryEncodeImageIsPass/
getLoginSchoolInfo）因验证码无法自动化已移除，不再测试。
"""

import httpx
import pytest
import respx

from zhs.api.encrypted_query import EncryptedQuery
from zhs.api.http_client import HttpClient
from zhs.api.zhidao_exam_api import ZhidaoExamApi
from zhs.config import AppConfig

EXAM_LIST_RESPONSE = {
    "currentTime": 1781533923054,
    "msg": "请求成功",
    "rt": [
        {
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
    ],
    "status": "200",
}


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def http_client(config: AppConfig) -> HttpClient:
    return HttpClient(config)


@pytest.fixture
def query(http_client: HttpClient) -> EncryptedQuery:
    return EncryptedQuery(http_client)


@pytest.fixture
def api(query: EncryptedQuery) -> ZhidaoExamApi:
    return ZhidaoExamApi(query)


class TestGetStudentFinalExam:
    """获取考试列表"""

    def test_returns_rt_array(self, api: ZhidaoExamApi) -> None:
        """返回 rt 数组"""
        with respx.mock:
            respx.post("https://taurusexam-api.zhihuishu.com/taurusExam/gateway/t/v1/student/getStudentFinalExam").mock(
                return_value=httpx.Response(200, json=EXAM_LIST_RESPONSE)
            )
            result = api.get_student_final_exam(course_id=1000083416, recruit_id="394787", flag=1)
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["examId"] == "eAqdKONe"

    def test_empty_rt(self, api: ZhidaoExamApi) -> None:
        """无考试时返回空数组"""
        with respx.mock:
            resp = {**EXAM_LIST_RESPONSE, "rt": []}
            respx.post("https://taurusexam-api.zhihuishu.com/taurusExam/gateway/t/v1/student/getStudentFinalExam").mock(
                return_value=httpx.Response(200, json=resp)
            )
            result = api.get_student_final_exam(course_id=1000083416, recruit_id="394787", flag=1)
            assert result == []

    def test_raises_on_error_status(self, api: ZhidaoExamApi) -> None:
        """status 非 '200' 时抛出异常"""
        from zhs.exceptions import ApiError

        with respx.mock:
            respx.post("https://taurusexam-api.zhihuishu.com/taurusExam/gateway/t/v1/student/getStudentFinalExam").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "请求失败"})
            )
            with pytest.raises(ApiError):
                api.get_student_final_exam(course_id=1000083416, recruit_id="394787", flag=1)


class TestGetSaveAnswerLockResult:
    """查询答案是否锁死"""

    LOCK_RESPONSE = {
        "currentTime": 1782971884619,
        "msg": "请求成功",
        "rt": {"state": 1},
        "status": "200",
    }

    HW_BASE = "https://studentexam-api.zhihuishu.com"

    def test_returns_locked_state(self, api: ZhidaoExamApi) -> None:
        """返回 rt.state（1=锁死）"""
        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/getSaveAnswerLockResult").mock(
                return_value=httpx.Response(200, json=self.LOCK_RESPONSE)
            )
            state = api.get_save_answer_lock_result(exam_id="eAqdKONe", recruit_id="394787")
            assert state == 1

    def test_unlocked_returns_zero(self, api: ZhidaoExamApi) -> None:
        """未锁死时 state=0"""
        with respx.mock:
            resp = {**self.LOCK_RESPONSE, "rt": {"state": 0}}
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/getSaveAnswerLockResult").mock(
                return_value=httpx.Response(200, json=resp)
            )
            state = api.get_save_answer_lock_result(exam_id="eAqdKONe", recruit_id="394787")
            assert state == 0


# ---------------------------------------------------------------------------
# getLoginSchoolInfo — 获取当前登录用户学校信息（用于 doExam 的 schoolId 参数）
# ---------------------------------------------------------------------------


SCHOOL_INFO_RESPONSE = {
    "currentTime": 1782974019284,
    "msg": "请求成功",
    "rt": {
        "id": None,
        "schoolId": 625,
        "bannerPath": "https://image.zhihuishu.com/testzhs/myuni/home/201607/b82fe70e13e54f859c896120b67bedc1.png",
        "background": "#276b8f",
        "schoolPageUrl": "//school.zhihuishu.com/gdut",
    },
    "status": "200",
}


class TestGetLoginSchoolInfo:
    """获取当前登录用户学校信息"""

    HW_BASE = "https://studentexam-api.zhihuishu.com"

    def test_returns_school_id(self, api: ZhidaoExamApi) -> None:
        """返回 rt.schoolId（str 型，如 "625"）"""
        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo").mock(
                return_value=httpx.Response(200, json=SCHOOL_INFO_RESPONSE)
            )
            school_id = api.get_login_school_info()
            assert school_id == "625"

    def test_returns_empty_when_rt_is_none(self, api: ZhidaoExamApi) -> None:
        """rt=null 时返回空字符串（用户未绑定学校）"""
        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo").mock(
                return_value=httpx.Response(200, json={"rt": None, "status": "200"})
            )
            school_id = api.get_login_school_info()
            assert school_id == ""

    def test_returns_empty_when_school_id_is_none(self, api: ZhidaoExamApi) -> None:
        """schoolId=null 时返回空字符串（用户未绑定学校）"""
        with respx.mock:
            resp = {**SCHOOL_INFO_RESPONSE, "rt": {**SCHOOL_INFO_RESPONSE["rt"], "schoolId": None}}
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo").mock(
                return_value=httpx.Response(200, json=resp)
            )
            school_id = api.get_login_school_info()
            assert school_id == ""

    def test_uses_homework_strategy(self, api: ZhidaoExamApi) -> None:
        """使用 homework 策略（exam_key, 无 dateFormate, status='200'）"""
        with respx.mock:
            route = respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo").mock(
                return_value=httpx.Response(200, json=SCHOOL_INFO_RESPONSE)
            )
            api.get_login_school_info()
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" not in body

    def test_raises_on_error_status(self, api: ZhidaoExamApi) -> None:
        """status 非 '200' 时抛出异常"""
        from zhs.exceptions import ApiError

        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "请求失败"})
            )
            with pytest.raises(ApiError):
                api.get_login_school_info()


# ---------------------------------------------------------------------------
# doExam — 开始考试（获取题目详情）
# ---------------------------------------------------------------------------


DO_EXAM_RESPONSE = {
    "currentTime": 1782980005268,
    "msg": "请求成功",
    "rt": {
        "id": None,
        "score": None,
        "examBase": {
            "id": "eAqdKONe",
            "name": "思想道德与法治教程试卷",
            "courseName": "思想道德与法治",
            "toChapter": None,
            "explain": "单选题40道，每道1分，多选题20道，每道2分，判断题20道，每道1分。",
            "limitTime": None,
            "problemNum": 80,
            "totalScore": "100",
            "pontType": "百分制",
            "workExamParts": [
                {
                    "id": None,
                    "startSort": 1,
                    "questionCount": 1,
                    "questionDtos": [
                        {
                            "id": None,
                            "parentId": None,
                            "name": "测试题目",
                            "listenId": None,
                            "listenData": None,
                            "questionType": {"id": 1, "name": "单选题"},
                            "questionOptions": [
                                {"id": 463433073, "content": "选项A"},
                                {"id": 463433067, "content": "选项B"},
                                {"id": 463433070, "content": "选项C"},
                                {"id": 463433065, "content": "选项D"},
                            ],
                            "questionDatas": None,
                            "questionChildrens": None,
                            "questionScore": "1",
                            "eid": "JaPd4nACmjOFYSCTE4kZpA==",
                            "comments": None,
                            "result": None,
                        }
                    ],
                }
            ],
            "ttfUrl": None,
        },
        "examEndTime": "2026-07-02 17:07:55",
        "state": None,
    },
    "status": "200",
}


class TestDoExam:
    """开始考试（获取题目详情）"""

    BASE = "https://taurusexam-api.zhihuishu.com"

    def test_returns_rt_dict(self, api: ZhidaoExamApi) -> None:
        """返回 rt 对象（含 examBase）"""
        with respx.mock:
            respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/student/doExam").mock(
                return_value=httpx.Response(200, json=DO_EXAM_RESPONSE)
            )
            result = api.do_exam(
                recruit_id="394787",
                exam_id="eAqdKONe",
                student_exam_id="edJddjZE",
                school_id="625",
                course_id="1000083416",
            )
            assert "examBase" in result
            assert result["examBase"]["id"] == "eAqdKONe"
            assert result["examBase"]["workExamParts"][0]["questionDtos"][0]["eid"] == "JaPd4nACmjOFYSCTE4kZpA=="

    def test_uses_zhidao_exam_strategy(self, api: ZhidaoExamApi) -> None:
        """使用 zhidao_exam 策略（taurusexam 域名, exam_key, 无 dateFormate, status='200'）"""
        with respx.mock:
            route = respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/student/doExam").mock(
                return_value=httpx.Response(200, json=DO_EXAM_RESPONSE)
            )
            api.do_exam(
                recruit_id="394787",
                exam_id="eAqdKONe",
                student_exam_id="edJddjZE",
                school_id="625",
                course_id="1000083416",
            )
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" not in body

    def test_raises_on_error_status(self, api: ZhidaoExamApi) -> None:
        """status 非 '200' 时抛出异常"""
        from zhs.exceptions import ApiError

        with respx.mock:
            respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/student/doExam").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "试卷已提交"})
            )
            with pytest.raises(ApiError):
                api.do_exam(
                    recruit_id="394787",
                    exam_id="eAqdKONe",
                    student_exam_id="edJddjZE",
                    school_id="625",
                    course_id="1000083416",
                )


# ---------------------------------------------------------------------------
# saveStudentAnswer — 保存单题答案
# ---------------------------------------------------------------------------


SAVE_ANSWER_RESPONSE = {
    "currentTime": 1782979669265,
    "msg": "请求成功",
    "rt": {"msg": "", "statu": "1"},
    "status": "200",
}


class TestSaveStudentAnswer:
    """保存单题答案（saveStudentAnswer）"""

    HW_BASE = "https://studentexam-api.zhihuishu.com"

    def test_returns_rt_dict(self, api: ZhidaoExamApi) -> None:
        """返回 rt 对象（含 statu 字段）"""
        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/saveStudentAnswer").mock(
                return_value=httpx.Response(200, json=SAVE_ANSWER_RESPONSE)
            )
            answer_item = {
                "examId": "eAqdKONe",
                "recruitId": "394787",
                "stuExamId": "edJddjZE",
                "eid": "vPFMpAK/PoJ5BIKaAmAoXw==",
                "schoolId": "625",
                "deviceId": "",
                "examType": 1,
                "fromType": 3,
                "answer": 463433473,
                "dataIds": "",
                "questionType": 14,
            }
            result = api.save_student_answer(answer_item, recruit_id="394787")
            assert result["statu"] == "1"

    def test_sends_source_field_as_plaintext(self, api: ZhidaoExamApi) -> None:
        """source=1 作为明文字段与 secretStr 一起发送"""
        with respx.mock:
            route = respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/saveStudentAnswer").mock(
                return_value=httpx.Response(200, json=SAVE_ANSWER_RESPONSE)
            )
            answer_item = {
                "examId": "eAqdKONe",
                "recruitId": "394787",
                "stuExamId": "edJddjZE",
                "eid": "vPFMpAK/PoJ5BIKaAmAoXw==",
                "schoolId": "625",
                "deviceId": "",
                "examType": 1,
                "fromType": 3,
                "answer": 463433473,
                "dataIds": "",
                "questionType": 14,
            }
            api.save_student_answer(answer_item, recruit_id="394787")
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "source=1" in body

    def test_uses_homework_strategy(self, api: ZhidaoExamApi) -> None:
        """使用 homework 策略（studentexam 域名, exam_key, 无 dateFormate, status='200'）"""
        with respx.mock:
            route = respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/saveStudentAnswer").mock(
                return_value=httpx.Response(200, json=SAVE_ANSWER_RESPONSE)
            )
            answer_item = {
                "examId": "eAqdKONe",
                "recruitId": "394787",
                "stuExamId": "edJddjZE",
                "eid": "vPFMpAK/PoJ5BIKaAmAoXw==",
                "schoolId": "625",
                "deviceId": "",
                "examType": 1,
                "fromType": 3,
                "answer": 463433473,
                "dataIds": "",
                "questionType": 14,
            }
            api.save_student_answer(answer_item, recruit_id="394787")
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" not in body

    def test_raises_on_error_status(self, api: ZhidaoExamApi) -> None:
        """status 非 '200' 时抛出异常"""
        from zhs.exceptions import ApiError

        with respx.mock:
            respx.post(f"{self.HW_BASE}/studentExam/gateway/t/v1/answer/saveStudentAnswer").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "试卷已提交"})
            )
            answer_item = {
                "examId": "eAqdKONe",
                "recruitId": "394787",
                "stuExamId": "edJddjZE",
                "eid": "vPFMpAK/PoJ5BIKaAmAoXw==",
                "schoolId": "625",
                "deviceId": "",
                "examType": 1,
                "fromType": 3,
                "answer": 463433473,
                "dataIds": "",
                "questionType": 14,
            }
            with pytest.raises(ApiError):
                api.save_student_answer(answer_item, recruit_id="394787")


# ---------------------------------------------------------------------------
# submit — 提交考试
# ---------------------------------------------------------------------------


SUBMIT_RESPONSE = {
    "currentTime": 1782983281910,
    "msg": "请求成功",
    "rt": {"msg": "提交成功", "statu": "1"},
    "status": "200",
}


class TestSubmitExam:
    """提交考试（submit）"""

    BASE = "https://taurusexam-api.zhihuishu.com"

    def test_returns_rt_dict(self, api: ZhidaoExamApi) -> None:
        """返回 rt 对象（含 msg 和 statu 字段）"""
        with respx.mock:
            respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/answer/submit").mock(
                return_value=httpx.Response(200, json=SUBMIT_RESPONSE)
            )
            result = api.submit_exam(
                recruit_id="394787",
                exam_id="eAqdKONe",
                stu_exam_id="edJddjZE",
                achieve_count="80",
            )
            assert result["msg"] == "提交成功"
            assert result["statu"] == "1"

    def test_uses_zhidao_exam_strategy(self, api: ZhidaoExamApi) -> None:
        """使用 zhidao_exam 策略（taurusexam 域名, exam_key, 无 dateFormate, status='200'）"""
        with respx.mock:
            route = respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/answer/submit").mock(
                return_value=httpx.Response(200, json=SUBMIT_RESPONSE)
            )
            api.submit_exam(
                recruit_id="394787",
                exam_id="eAqdKONe",
                stu_exam_id="edJddjZE",
                achieve_count="80",
            )
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" not in body
            assert "source=" not in body  # submit 不发送 source 字段

    def test_raises_on_error_status(self, api: ZhidaoExamApi) -> None:
        """status 非 '200' 时抛出异常"""
        from zhs.exceptions import ApiError

        with respx.mock:
            respx.post(f"{self.BASE}/taurusExam/gateway/t/v1/answer/submit").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "提交失败"})
            )
            with pytest.raises(ApiError):
                api.submit_exam(
                    recruit_id="394787",
                    exam_id="eAqdKONe",
                    stu_exam_id="edJddjZE",
                    achieve_count="80",
                )

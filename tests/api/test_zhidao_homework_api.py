"""api/zhidao_homework_api.py ZhidaoHomeworkApi 测试

验证知到作业 6 个业务方法：
- homework_redo: 重做作业（saveCourseTran）
- homework_do: 开始做作业（doHomework）
- homework_save_answer: 保存单题答案（saveStudentAnswer）
- homework_submit: 提交作业（submit）
- homework_look: 查看已提交作业（lookHomework）
- homework_get_answer: 获取学生答案信息（getStuAnswerInfo）
"""

import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from zhs.api.encrypted_query import EncryptedQuery
from zhs.api.http_client import HttpClient
from zhs.api.zhidao_homework_api import ZhidaoHomeworkApi
from zhs.config import AppConfig
from zhs.crypto import Cipher


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def http_client(config: AppConfig) -> HttpClient:
    """测试用 HttpClient"""
    return HttpClient(config)


@pytest.fixture
def query(http_client: HttpClient) -> EncryptedQuery:
    """测试用 EncryptedQuery"""
    return EncryptedQuery(http_client)


@pytest.fixture
def api(query: EncryptedQuery) -> ZhidaoHomeworkApi:
    """测试用 ZhidaoHomeworkApi"""
    return ZhidaoHomeworkApi(query)


class TestHomeworkRedo:
    """重做作业"""

    def test_calls_saveCourseTran(self, api: ZhidaoHomeworkApi) -> None:
        """调用 saveCourseTran 接口"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/saveCourseTran"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "data": {}}))
            result = api.homework_redo(recruit_id="r1", exam_id="e1", course_id=100)
            assert route.called
            # 数据已加密，仅验证 secretStr 存在
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert result["status"] == "200"


class TestHomeworkDo:
    """开始做作业"""

    def test_calls_doHomework(self, api: ZhidaoHomeworkApi) -> None:
        """调用 doHomework 接口"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/doHomework"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "data": {"eid": "x"}}))
            result = api.homework_do(
                recruit_id="r1",
                exam_id="e1",
                student_exam_id="s1",
                school_id="1000",
                course_id="c1",
            )
            assert route.called
            assert result["status"] == "200"


class TestHomeworkSaveAnswer:
    """保存单题答案"""

    def test_calls_saveStudentAnswer(self, api: ZhidaoHomeworkApi) -> None:
        """调用 saveStudentAnswer 接口"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/answer/saveStudentAnswer"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "data": {}}))
            answer_item: dict[str, Any] = {
                "examId": "e1",
                "eid": "x",
                "answer": "A",
                "questionType": 1,
            }
            result = api.homework_save_answer(answer_item, recruit_id="r1")
            assert route.called
            # 数据已加密，仅验证 secretStr 存在
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert result["status"] == "200"


class TestHomeworkSubmit:
    """提交作业"""

    def test_calls_submit(self, api: ZhidaoHomeworkApi) -> None:
        """调用 submit 接口"""
        with respx.mock:
            route = respx.post("https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/answer/submit").mock(
                return_value=httpx.Response(200, json={"status": "200", "rt": {"score": "90"}})
            )
            result = api.homework_submit(
                recruit_id="r1",
                exam_id="e1",
                stu_exam_id="s1",
                achieve_count=10,
            )
            assert route.called
            assert result["rt"]["score"] == "90"


class TestHomeworkLook:
    """查看已提交作业"""

    def test_calls_lookHomework(self, api: ZhidaoHomeworkApi) -> None:
        """调用 lookHomework 接口"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/lookHomework"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "data": {}}))
            api.homework_look(
                recruit_id="r1",
                student_exam_id="s1",
                exam_id="e1",
                school_id="1000",
                course_id="c1",
            )
            assert route.called


class TestHomeworkGetAnswer:
    """获取学生答案信息"""

    def test_calls_getStuAnswerInfo(self, api: ZhidaoHomeworkApi) -> None:
        """调用 getStuAnswerInfo 接口"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/answer/getStuAnswerInfo"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "data": {}}))
            result = api.homework_get_answer(
                recruit_id="r1",
                stu_exam_id="s1",
                exam_id="e1",
                school_id="1000",
                course_id="c1",
                question_ids=[1, 2, 3],
            )
            assert route.called
            # 数据已加密，仅验证 secretStr 存在
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert result["status"] == "200"


class TestHomeworkValidateSlideToken:
    """上报验证码 validate（作业风控解锁）"""

    def test_encrypts_expected_payload(self, config: AppConfig, api: ZhidaoHomeworkApi) -> None:
        """加密载荷为 recruitId/token/checkType=1/chapterId=examId，且不带 dateFormate"""
        with respx.mock:
            route = respx.post(
                "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/answer/validateSlideToken"
            ).mock(return_value=httpx.Response(200, json={"status": "200", "pass": True}))
            result = api.homework_validate_slide_token(
                recruit_id="r1",
                exam_id="exam-1",
                token="CN31_abc_v_i_1",
            )
            assert route.called
            body = route.calls[0].request.content.decode()
            secret = parse_qs(body)["secretStr"][0]
            cipher = Cipher(config.crypto.key_bytes("exam_key"), config.crypto.key_bytes("iv"))
            payload = json.loads(cipher.decrypt(secret))
            assert payload == {
                "recruitId": "r1",
                "token": "CN31_abc_v_i_1",
                "checkType": 1,
                "chapterId": "exam-1",
            }
            assert result["pass"] is True

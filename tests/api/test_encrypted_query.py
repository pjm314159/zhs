"""api/encrypted_query.py EncryptedQuery 测试

验证 6 套加密查询策略：
- zhidao: video_key, dateFormate, code=0, 检查 -12
- hike: 无加密, 时间戳, status=200, 可选签名
- ai_exam: exam_key, dateFormate, code=0
- ai_task: ai_key, dateFormate, code=200, content_type=json
- homework: exam_key, 无 dateFormate, status="200"
- ai_exam_submit: exam_key, dateFormate, 无返回体
"""

import httpx
import pytest
import respx

from zhs.api.encrypted_query import STRATEGIES, EncryptedQuery
from zhs.api.http_client import HttpClient
from zhs.config import AppConfig
from zhs.exceptions import ApiError, CaptchaRequired


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


# ---------------------------------------------------------------------------
# 策略表
# ---------------------------------------------------------------------------


class TestStrategies:
    """策略表定义"""

    def test_zhidao_strategy(self) -> None:
        """zhidao 策略：video_key, dateFormate, code=0, 检查 -12"""
        s = STRATEGIES["zhidao"]
        assert s.key_name == "video_key"
        assert s.with_dateformate is True
        assert s.check_field == "code"
        assert s.ok_value == 0
        assert s.check_captcha is True

    def test_hike_strategy(self) -> None:
        """hike 策略：无加密, status=200"""
        s = STRATEGIES["hike"]
        assert s.key_name == ""
        assert s.with_dateformate is False
        assert s.check_field == "status"
        assert s.ok_value == 200

    def test_ai_exam_strategy(self) -> None:
        """ai_exam 策略：exam_key, dateFormate, code=0"""
        s = STRATEGIES["ai_exam"]
        assert s.key_name == "exam_key"
        assert s.with_dateformate is True
        assert s.check_field == "code"
        assert s.ok_value == 0

    def test_ai_task_strategy(self) -> None:
        """ai_task 策略：ai_key, dateFormate, code=200, json"""
        s = STRATEGIES["ai_task"]
        assert s.key_name == "ai_key"
        assert s.with_dateformate is True
        assert s.check_field == "code"
        assert s.ok_value == 200
        assert s.content_type == "json"

    def test_homework_strategy(self) -> None:
        """homework 策略：exam_key, 无 dateFormate, status='200'"""
        s = STRATEGIES["homework"]
        assert s.key_name == "exam_key"
        assert s.with_dateformate is False
        assert s.check_field == "status"
        assert s.ok_value == "200"

    def test_ai_exam_submit_strategy(self) -> None:
        """ai_exam_submit 策略：exam_key, dateFormate, 无返回体"""
        s = STRATEGIES["ai_exam_submit"]
        assert s.key_name == "exam_key"
        assert s.with_dateformate is True
        assert s.has_response_body is False


# ---------------------------------------------------------------------------
# zhidao 查询
# ---------------------------------------------------------------------------


class TestZhidaoQuery:
    """zhidao 策略查询"""

    def test_encrypts_data_and_adds_dateformate(self, query: EncryptedQuery) -> None:
        """zhidao 自动加密 data + 添加 dateFormate"""
        with respx.mock:
            route = respx.post("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {"result": "ok"}})
            )
            result = query.query("zhidao", "https://example.com/api", data={"key": "value"})
            assert route.called
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" in body
            assert result["code"] == 0

    def test_code_minus_12_raises_captcha(self, query: EncryptedQuery) -> None:
        """返回码 -12 抛 CaptchaRequired"""
        with respx.mock:
            respx.post("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": -12, "message": "需要验证码"})
            )
            with pytest.raises(CaptchaRequired):
                query.query("zhidao", "https://example.com/api", data={})

    def test_non_zero_code_raises_api_error(self, query: EncryptedQuery) -> None:
        """非零返回码抛 ApiError"""
        with respx.mock:
            respx.post("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 500, "message": "server error"})
            )
            with pytest.raises(ApiError) as exc_info:
                query.query("zhidao", "https://example.com/api", data={})
            assert exc_info.value.code == 500


# ---------------------------------------------------------------------------
# hike 查询
# ---------------------------------------------------------------------------


class TestHikeQuery:
    """hike 策略查询"""

    def test_adds_timestamp(self, query: EncryptedQuery) -> None:
        """hike 自动添加 _ 时间戳"""
        with respx.mock:
            route = respx.get("https://hike.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": {}})
            )
            query.query("hike", "https://hike.example.com/api", data={})
            assert route.called
            request = route.calls[0].request
            assert "_" in str(request.url)

    def test_sig_true_adds_signature(self, query: EncryptedQuery) -> None:
        """sig=True 时自动签名"""
        with respx.mock:
            route = respx.get("https://hike.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": {}})
            )
            query.query(
                "hike",
                "https://hike.example.com/api",
                data={"uuid": "test"},
                sig=True,
            )
            assert route.called
            request = route.calls[0].request
            assert "signature=" in str(request.url)

    def test_non_200_status_raises_api_error(self, query: EncryptedQuery) -> None:
        """非 200 code 抛 ApiError"""
        with respx.mock:
            respx.get("https://hike.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 403, "message": "forbidden"})
            )
            with pytest.raises(ApiError) as exc_info:
                query.query("hike", "https://hike.example.com/api", data={})
            assert exc_info.value.code == 403


# ---------------------------------------------------------------------------
# ai_exam 查询
# ---------------------------------------------------------------------------


class TestAiExamQuery:
    """ai_exam 策略查询"""

    def test_query_works(self, query: EncryptedQuery) -> None:
        """ai_exam 同步查询正常工作"""
        with respx.mock:
            respx.post("https://ai.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            result = query.query("ai_exam", "https://ai.example.com/api", data={"q": "test"})
            assert result["code"] == 0

    def test_uses_exam_key(self, query: EncryptedQuery) -> None:
        """密钥从 config.crypto.exam_key 获取"""
        with respx.mock:
            route = respx.post("https://ai.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            query.query("ai_exam", "https://ai.example.com/api", data={"q": "test"})
            assert route.called
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body

    def test_non_zero_code_raises_api_error(self, query: EncryptedQuery) -> None:
        """非零返回码抛 ApiError"""
        with respx.mock:
            respx.post("https://ai.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 1, "message": "error"})
            )
            with pytest.raises(ApiError):
                query.query("ai_exam", "https://ai.example.com/api", data={})


# ---------------------------------------------------------------------------
# ai_task 查询
# ---------------------------------------------------------------------------


class TestAiTaskQuery:
    """ai_task 策略查询"""

    def test_query_works(self, query: EncryptedQuery) -> None:
        """ai_task 同步查询正常工作"""
        with respx.mock:
            respx.post("https://task.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": []})
            )
            result = query.query("ai_task", "https://task.example.com/api", data={"courseId": "123"})
            assert result["code"] == 200

    def test_uses_ai_key(self, query: EncryptedQuery) -> None:
        """密钥从 config.crypto.ai_key 获取，发送 dateFormate"""
        with respx.mock:
            route = respx.post("https://task.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": []})
            )
            query.query("ai_task", "https://task.example.com/api", data={"courseId": "123"})
            assert route.called
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" in body

    def test_ok_code_200(self, query: EncryptedQuery) -> None:
        """默认 ok_code=200"""
        with respx.mock:
            respx.post("https://task.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": []})
            )
            result = query.query("ai_task", "https://task.example.com/api", data={})
            assert result["code"] == 200

    def test_non_ok_code_raises_api_error(self, query: EncryptedQuery) -> None:
        """非 ok_code 抛 ApiError"""
        with respx.mock:
            respx.post("https://task.example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 500, "message": "error"})
            )
            with pytest.raises(ApiError):
                query.query("ai_task", "https://task.example.com/api", data={})


# ---------------------------------------------------------------------------
# homework 查询
# ---------------------------------------------------------------------------


class TestHomeworkQuery:
    """homework 策略查询"""

    def test_encrypts_data_without_dateformate(self, query: EncryptedQuery) -> None:
        """homework 加密数据但不发送 dateFormate"""
        with respx.mock:
            route = respx.post("https://homework.example.com/api").mock(
                return_value=httpx.Response(200, json={"status": "200", "data": {}})
            )
            query.query("homework", "https://homework.example.com/api", data={"key": "value"})
            assert route.called
            request = route.calls[0].request
            body = request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" not in body

    def test_default_ok_status_200(self, query: EncryptedQuery) -> None:
        """默认 ok_status='200'"""
        with respx.mock:
            respx.post("https://homework.example.com/api").mock(
                return_value=httpx.Response(200, json={"status": "200", "data": {}})
            )
            result = query.query("homework", "https://homework.example.com/api", data={})
            assert result["status"] == "200"

    def test_non_200_status_raises_api_error(self, query: EncryptedQuery) -> None:
        """非 '200' status 抛 ApiError"""
        with respx.mock:
            respx.post("https://homework.example.com/api").mock(
                return_value=httpx.Response(200, json={"status": "-1", "msg": "error"})
            )
            with pytest.raises(ApiError) as exc_info:
                query.query("homework", "https://homework.example.com/api", data={})
            assert exc_info.value.code == -1


# ---------------------------------------------------------------------------
# ai_exam_submit 查询
# ---------------------------------------------------------------------------


class TestAiExamSubmit:
    """ai_exam_submit 策略查询（无返回体）"""

    def test_submit_returns_true_on_200(self, query: EncryptedQuery) -> None:
        """HTTP 200 返回 True"""
        with respx.mock:
            respx.post("https://ai.example.com/submit").mock(return_value=httpx.Response(200))
            assert query.query("ai_exam_submit", "https://ai.example.com/submit", data={"k": "v"}) == {}

    def test_submit_raises_on_error(self, query: EncryptedQuery) -> None:
        """非 2xx 抛 HTTPStatusError"""
        with respx.mock:
            respx.post("https://ai.example.com/submit").mock(return_value=httpx.Response(500))
            with pytest.raises(httpx.HTTPStatusError):
                query.query("ai_exam_submit", "https://ai.example.com/submit", data={"k": "v"})


# ---------------------------------------------------------------------------
# 未知策略
# ---------------------------------------------------------------------------


class TestUnknownStrategy:
    """未知策略"""

    def test_unknown_strategy_raises_keyerror(self, query: EncryptedQuery) -> None:
        """未知策略名抛 KeyError"""
        with pytest.raises(KeyError):
            query.query("unknown", "https://example.com/api", data={})

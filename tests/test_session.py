"""Task 1.7 — session.py 测试"""

from typing import Any

import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.exceptions import ApiError, CaptchaRequired
from zhs.session import ZhsSession


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def session(config: AppConfig) -> ZhsSession:
    """测试用 session"""
    return ZhsSession(config)


@pytest.fixture
def mock_http() -> Any:
    """Mock HTTP 请求"""
    with respx.mock:
        yield


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------


class TestZhsSessionInit:
    def test_init_no_error(self, config: AppConfig) -> None:
        """ZhsSession(config) 初始化不报错"""
        s = ZhsSession(config)
        assert s is not None

    def test_urls_property(self, session: ZhsSession) -> None:
        """session.urls 返回 UrlConfig"""
        assert session.urls is not None
        assert session.urls.base == "https://onlineservice-api.zhihuishu.com"

    def test_crypto_property(self, session: ZhsSession) -> None:
        """session.crypto 返回 CryptoConfig"""
        assert session.crypto is not None
        assert session.crypto.video_key == "azp53h0kft7qi78q"


# ---------------------------------------------------------------------------
# Cookie / UUID 解析
# ---------------------------------------------------------------------------


class TestCookieUuid:
    def test_uuid_from_caslogc(self, session: ZhsSession) -> None:
        """设置 CASLOGC cookie 后 uuid 正确解析"""
        session.cookies = httpx.Cookies()
        session._cookies.set("CASLOGC", '{"uuid":"test-uuid-123"}', domain="zhihuishu.com")
        session._parse_uuid()
        assert session.uuid == "test-uuid-123"

    def test_uuid_from_url_encoded_caslogc(self, session: ZhsSession) -> None:
        """CASLOGC 为 URL 编码时也能正确解析 uuid"""
        session.cookies = httpx.Cookies()
        session._cookies.set(
            "CASLOGC",
            "%7B%22uuid%22%3A%22Xe6arnRO%22%2C%22userId%22%3A892074277%7D",
            domain="zhihuishu.com",
        )
        session._parse_uuid()
        assert session.uuid == "Xe6arnRO"

    def test_exit_record_set(self, session: ZhsSession) -> None:
        """Cookie 设置时自动添加 exitRecod_{uuid}=2"""
        session.cookies = httpx.Cookies()
        session._cookies.set("CASLOGC", '{"uuid":"abc"}', domain="zhihuishu.com")
        session._parse_uuid()
        assert session._cookies.get("exitRecod_abc") == "2"

    def test_uuid_none_without_caslogc(self, session: ZhsSession) -> None:
        """没有 CASLOGC 时 uuid 为 None"""
        session.cookies = httpx.Cookies()
        session._parse_uuid()
        assert session.uuid is None

    def test_uuid_invalid_json(self, session: ZhsSession) -> None:
        """CASLOGC 为无效 JSON 时 uuid 为 None"""
        session.cookies = httpx.Cookies()
        session._cookies.set("CASLOGC", "not-json", domain="zhihuishu.com")
        session._parse_uuid()
        assert session.uuid is None


# ---------------------------------------------------------------------------
# zhidao_query
# ---------------------------------------------------------------------------


class TestZhidaoQuery:
    def test_encrypts_data_and_adds_dateformate(self, session: ZhsSession, mock_http: Any) -> None:
        """zhidao_query 自动加密 data + 添加 dateFormate"""
        route = respx.post("https://example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"result": "ok"}})
        )
        result = session.zhidao_query("https://example.com/api", data={"key": "value"})
        assert route.called
        # 验证请求中包含 secretStr 和 dateFormate
        request = route.calls[0].request
        body = request.content.decode()
        assert "secretStr" in body
        assert "dateFormate" in body
        assert result["code"] == 0

    def test_code_minus_12_raises_captcha(self, session: ZhsSession, mock_http: Any) -> None:
        """返回码 -12 抛 CaptchaRequired"""
        respx.post("https://example.com/api").mock(
            return_value=httpx.Response(200, json={"code": -12, "message": "需要验证码"})
        )
        with pytest.raises(CaptchaRequired):
            session.zhidao_query("https://example.com/api", data={})

    def test_non_zero_code_raises_api_error(self, session: ZhsSession, mock_http: Any) -> None:
        """非零返回码抛 ApiError"""
        respx.post("https://example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 500, "message": "server error"})
        )
        with pytest.raises(ApiError) as exc_info:
            session.zhidao_query("https://example.com/api", data={})
        assert exc_info.value.code == 500


# ---------------------------------------------------------------------------
# hike_query
# ---------------------------------------------------------------------------


class TestHikeQuery:
    def test_adds_timestamp(self, session: ZhsSession, mock_http: Any) -> None:
        """hike_query 自动添加 _ 时间戳"""
        route = respx.get("https://hike.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {}})
        )
        session.hike_query("https://hike.example.com/api", data={})
        assert route.called
        request = route.calls[0].request
        assert "_" in str(request.url)

    def test_sig_true_adds_signature(self, session: ZhsSession, mock_http: Any) -> None:
        """sig=True 时自动签名"""
        route = respx.get("https://hike.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {}})
        )
        session.hike_query("https://hike.example.com/api", data={"uuid": "test"}, sig=True)
        assert route.called
        request = route.calls[0].request
        assert "signature=" in str(request.url)

    def test_non_200_status_raises_api_error(self, session: ZhsSession, mock_http: Any) -> None:
        """非 200 code 抛 ApiError"""
        respx.get("https://hike.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 403, "message": "forbidden"})
        )
        with pytest.raises(ApiError) as exc_info:
            session.hike_query("https://hike.example.com/api", data={})
        assert exc_info.value.code == 403


# ---------------------------------------------------------------------------
# ai_exam_query
# ---------------------------------------------------------------------------


class TestAiExamQuery:
    def test_sync_query_works(self, config: AppConfig, mock_http: Any) -> None:
        """ai_exam_query 同步版本正常工作"""
        session = ZhsSession(config)
        respx.post("https://ai.example.com/api").mock(return_value=httpx.Response(200, json={"code": 0, "data": {}}))
        result = session.ai_exam_query("https://ai.example.com/api", data={"q": "test"})
        assert result["code"] == 0
        session.close()

    def test_uses_exam_key(self, config: AppConfig, mock_http: Any) -> None:
        """密钥从 config.crypto.exam_key 获取"""
        session = ZhsSession(config)
        route = respx.post("https://ai.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )
        session.ai_exam_query("https://ai.example.com/api", data={"q": "test"})
        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "secretStr" in body
        session.close()

    def test_non_zero_code_raises_api_error(self, config: AppConfig, mock_http: Any) -> None:
        """非零返回码抛 ApiError"""
        session = ZhsSession(config)
        respx.post("https://ai.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 1, "message": "error"})
        )
        with pytest.raises(ApiError):
            session.ai_exam_query("https://ai.example.com/api", data={})
        session.close()


# ---------------------------------------------------------------------------
# ai_task_query
# ---------------------------------------------------------------------------


class TestAiTaskQuery:
    def test_sync_query_works(self, config: AppConfig, mock_http: Any) -> None:
        """ai_task_query 同步版本正常工作"""
        session = ZhsSession(config)
        respx.post("https://task.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": []})
        )
        result = session.ai_task_query("https://task.example.com/api", data={"courseId": "123"})
        assert result["code"] == 200
        session.close()

    def test_uses_ai_key(self, config: AppConfig, mock_http: Any) -> None:
        """密钥从 config.crypto.ai_key 获取，发送 dateFormate"""
        session = ZhsSession(config)
        route = respx.post("https://task.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": []})
        )
        session.ai_task_query("https://task.example.com/api", data={"courseId": "123"})
        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "secretStr" in body
        assert "dateFormate" in body
        session.close()

    def test_ok_code_200(self, config: AppConfig, mock_http: Any) -> None:
        """默认 ok_code=200（任务列表 API 返回 200）"""
        session = ZhsSession(config)
        respx.post("https://task.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": []})
        )
        result = session.ai_task_query("https://task.example.com/api", data={})
        assert result["code"] == 200
        session.close()

    def test_non_ok_code_raises_api_error(self, config: AppConfig, mock_http: Any) -> None:
        """非 ok_code 抛 ApiError"""
        session = ZhsSession(config)
        respx.post("https://task.example.com/api").mock(
            return_value=httpx.Response(200, json={"code": 500, "message": "error"})
        )
        with pytest.raises(ApiError):
            session.ai_task_query("https://task.example.com/api", data={})
        session.close()


# ---------------------------------------------------------------------------
# homework_query
# ---------------------------------------------------------------------------


class TestHomeworkQuery:
    def test_encrypts_data_without_dateformate(self, session: ZhsSession, mock_http: Any) -> None:
        """homework_query 加密数据但不发送 dateFormate"""
        route = respx.post("https://homework.example.com/api").mock(
            return_value=httpx.Response(200, json={"status": "200", "data": {}})
        )
        session.homework_query("https://homework.example.com/api", data={"key": "value"})
        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "secretStr" in body
        assert "dateFormate" not in body

    def test_default_ok_status_200(self, session: ZhsSession, mock_http: Any) -> None:
        """默认 ok_status='200'"""
        respx.post("https://homework.example.com/api").mock(
            return_value=httpx.Response(200, json={"status": "200", "data": {}})
        )
        result = session.homework_query("https://homework.example.com/api", data={})
        assert result["status"] == "200"

    def test_non_200_status_raises_api_error(self, session: ZhsSession, mock_http: Any) -> None:
        """非 '200' status 抛 ApiError"""
        respx.post("https://homework.example.com/api").mock(
            return_value=httpx.Response(200, json={"status": "-1", "msg": "error"})
        )
        with pytest.raises(ApiError) as exc_info:
            session.homework_query("https://homework.example.com/api", data={})
        assert exc_info.value.code == -1


# ---------------------------------------------------------------------------
# Cookie setter
# ---------------------------------------------------------------------------


class TestCookieSetter:
    def test_set_cookies_from_dict(self, session: ZhsSession) -> None:
        """从 dict 设置 cookies"""
        session.cookies = {"key1": "value1"}
        assert session._cookies.get("key1") == "value1"

    def test_set_cookies_from_list(self, session: ZhsSession) -> None:
        """从 list[dict] 设置 cookies"""
        session.cookies = [{"name": "key1", "value": "value1", "domain": "example.com"}]
        assert session._cookies.get("key1") == "value1"

    def test_set_cookies_from_httpx_cookies(self, session: ZhsSession) -> None:
        """从 httpx.Cookies 设置 cookies"""
        c = httpx.Cookies()
        c.set("key1", "value1")
        session.cookies = c
        assert session._cookies.get("key1") == "value1"

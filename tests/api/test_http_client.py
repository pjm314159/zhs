"""api/http_client.py HttpClient 测试

验证 HTTP 客户端封装：客户端生命周期、代理、重试、headers、cookies。
"""

import httpx
import pytest
import respx

from zhs.api.http_client import HttpClient
from zhs.config import AppConfig


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def client(config: AppConfig) -> HttpClient:
    """测试用 HttpClient"""
    return HttpClient(config)


class TestHttpClientInit:
    """HttpClient 初始化"""

    def test_init_no_error(self, config: AppConfig) -> None:
        """HttpClient(config) 初始化不报错"""
        c = HttpClient(config)
        assert c is not None

    def test_urls_property(self, client: HttpClient) -> None:
        """client.urls 返回 UrlConfig"""
        assert client.urls is not None
        assert client.urls.base == "https://onlineservice-api.zhihuishu.com"

    def test_crypto_property(self, client: HttpClient) -> None:
        """client.crypto 返回 CryptoConfig"""
        assert client.crypto is not None
        assert client.crypto.video_key == "azp53h0kft7qi78q"


class TestCookies:
    """Cookie 管理"""

    def test_cookies_default_empty(self, client: HttpClient) -> None:
        """默认 cookies 为空"""
        assert isinstance(client.cookies, httpx.Cookies)

    def test_set_cookies_from_dict(self, client: HttpClient) -> None:
        """从 dict 设置 cookies"""
        client.cookies = {"key1": "value1"}
        assert client.cookies.get("key1") == "value1"

    def test_set_cookies_from_list(self, client: HttpClient) -> None:
        """从 list[dict] 设置 cookies"""
        client.cookies = [{"name": "key1", "value": "value1", "domain": "example.com"}]
        assert client.cookies.get("key1") == "value1"

    def test_set_cookies_from_httpx_cookies(self, client: HttpClient) -> None:
        """从 httpx.Cookies 设置 cookies"""
        c = httpx.Cookies()
        c.set("key1", "value1")
        client.cookies = c
        assert client.cookies.get("key1") == "value1"

    def test_uuid_from_caslogc(self, client: HttpClient) -> None:
        """设置 CASLOGC cookie 后 uuid 正确解析"""
        client.cookies = httpx.Cookies()
        client.cookies.set("CASLOGC", '{"uuid":"test-uuid-123"}', domain="zhihuishu.com")
        client.parse_uuid()
        assert client.uuid == "test-uuid-123"

    def test_uuid_from_url_encoded_caslogc(self, client: HttpClient) -> None:
        """CASLOGC 为 URL 编码时也能正确解析 uuid"""
        client.cookies = httpx.Cookies()
        client.cookies.set(
            "CASLOGC",
            "%7B%22uuid%22%3A%22Xe6arnRO%22%2C%22userId%22%3A892074277%7D",
            domain="zhihuishu.com",
        )
        client.parse_uuid()
        assert client.uuid == "Xe6arnRO"

    def test_exit_record_set(self, client: HttpClient) -> None:
        """Cookie 设置时自动添加 exitRecod_{uuid}=2"""
        client.cookies = httpx.Cookies()
        client.cookies.set("CASLOGC", '{"uuid":"abc"}', domain="zhihuishu.com")
        client.parse_uuid()
        assert client.cookies.get("exitRecod_abc") == "2"

    def test_uuid_none_without_caslogc(self, client: HttpClient) -> None:
        """没有 CASLOGC 时 uuid 为 None"""
        client.cookies = httpx.Cookies()
        client.parse_uuid()
        assert client.uuid is None

    def test_uuid_invalid_json(self, client: HttpClient) -> None:
        """CASLOGC 为无效 JSON 时 uuid 为 None"""
        client.cookies = httpx.Cookies()
        client.cookies.set("CASLOGC", "not-json", domain="zhihuishu.com")
        client.parse_uuid()
        assert client.uuid is None


class TestApiQuery:
    """通用 API 查询"""

    def test_post_form(self, client: HttpClient) -> None:
        """POST form 请求"""
        with respx.mock:
            route = respx.post("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            result = client.api_query("https://example.com/api", data={"k": "v"})
            assert route.called
            assert result["code"] == 0

    def test_post_json(self, client: HttpClient) -> None:
        """POST json 请求"""
        with respx.mock:
            route = respx.post("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            client.api_query("https://example.com/api", data={"k": "v"}, content_type="json")
            assert route.called
            request = route.calls[0].request
            assert "application/json" in request.headers.get("content-type", "")

    def test_get(self, client: HttpClient) -> None:
        """GET 请求"""
        with respx.mock:
            route = respx.get("https://example.com/api").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            client.api_query("https://example.com/api", data={"k": "v"}, method="GET")
            assert route.called

    def test_post_form_default(self, client: HttpClient) -> None:
        """默认 POST form"""
        with respx.mock:
            route = respx.post("https://example.com/api").mock(return_value=httpx.Response(200, json={"code": 0}))
            client.api_query("https://example.com/api", data={"k": "v"})
            assert route.called
            request = route.calls[0].request
            assert "x-www-form-urlencoded" in request.headers.get("content-type", "")


class TestPostRaw:
    """原始 POST 请求（无返回体判断）"""

    def test_post_raw_returns_true_on_200(self, client: HttpClient) -> None:
        """HTTP 200 返回 True"""
        with respx.mock:
            respx.post("https://example.com/api").mock(return_value=httpx.Response(200))
            assert client.post_raw("https://example.com/api", data={"k": "v"}) is True

    def test_post_raw_raises_on_error(self, client: HttpClient) -> None:
        """非 2xx 抛 HTTPStatusError"""
        with respx.mock:
            respx.post("https://example.com/api").mock(return_value=httpx.Response(500))
            with pytest.raises(httpx.HTTPStatusError):
                client.post_raw("https://example.com/api", data={"k": "v"})


class TestStream:
    """流式请求"""

    def test_stream_returns_response(self, client: HttpClient) -> None:
        """stream 方法返回 httpx.Response 上下文管理器"""
        with respx.mock:
            respx.post("https://example.com/api").mock(return_value=httpx.Response(200, text="data: hello\n"))
            with client.stream("POST", "https://example.com/api", json={"k": "v"}) as resp:
                assert resp.status_code == 200
                lines = list(resp.iter_lines())
                assert "data: hello" in lines


class TestClose:
    """关闭客户端"""

    def test_close_no_error_when_not_created(self, client: HttpClient) -> None:
        """未创建 client 时 close 不报错"""
        client.close()  # 不应抛异常

    def test_close_after_use(self, client: HttpClient) -> None:
        """使用后 close 不报错"""
        with respx.mock:
            respx.post("https://example.com/api").mock(return_value=httpx.Response(200, json={}))
            client.api_query("https://example.com/api", data={})
            client.close()  # 不应抛异常

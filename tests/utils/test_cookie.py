"""Task 1.4 — utils/cookie.py 测试用例"""

import httpx

from zhs.utils.cookie import cookies_to_list, list_to_cookies


class TestCookiesToList:
    def test_empty_cookies(self) -> None:
        """空 cookies 序列化为空列表"""
        cookies = httpx.Cookies()
        result = cookies_to_list(cookies)
        assert result == []

    def test_single_cookie(self) -> None:
        """单个 cookie 序列化"""
        cookies = httpx.Cookies()
        cookies.set("name1", "value1", domain="example.com")
        result = cookies_to_list(cookies)
        assert len(result) == 1
        assert result[0]["name"] == "name1"
        assert result[0]["value"] == "value1"
        assert result[0]["domain"] == "example.com"

    def test_multiple_cookies(self) -> None:
        """多个 cookies 序列化"""
        cookies = httpx.Cookies()
        cookies.set("c1", "v1", domain="a.com")
        cookies.set("c2", "v2", domain="b.com")
        result = cookies_to_list(cookies)
        assert len(result) == 2
        names = {item["name"] for item in result}
        assert names == {"c1", "c2"}


class TestListToCookies:
    def test_empty_list(self) -> None:
        """空列表反序列化为空 Cookies"""
        result = list_to_cookies([])
        assert len(result) == 0

    def test_single_cookie(self) -> None:
        """单个 cookie 反序列化"""
        data = [{"name": "name1", "value": "value1", "domain": "example.com"}]
        result = list_to_cookies(data)
        assert result.get("name1") == "value1"

    def test_multiple_cookies(self) -> None:
        """多个 cookies 反序列化"""
        data = [
            {"name": "c1", "value": "v1", "domain": "a.com"},
            {"name": "c2", "value": "v2", "domain": "b.com"},
        ]
        result = list_to_cookies(data)
        assert result.get("c1") == "v1"
        assert result.get("c2") == "v2"


class TestRoundtrip:
    def test_roundtrip_preserves_cookie_data(self) -> None:
        """cookies_to_list → list_to_cookies 往返保持 cookie 数据"""
        original = httpx.Cookies()
        original.set("session_id", "abc123", domain="zhihuishu.com")
        original.set("token", "xyz789", domain="passport.zhihuishu.com")

        serialized = cookies_to_list(original)
        restored = list_to_cookies(serialized)

        assert restored.get("session_id") == "abc123"
        assert restored.get("token") == "xyz789"

    def test_roundtrip_empty_cookies(self) -> None:
        """空 cookies 往返"""
        original = httpx.Cookies()
        serialized = cookies_to_list(original)
        restored = list_to_cookies(serialized)
        assert len(restored) == 0

    def test_multiple_domain_cookies_preserve_domain(self) -> None:
        """不同域名的 cookies 保留域名信息"""
        original = httpx.Cookies()
        original.set("c1", "v1", domain="a.com")
        original.set("c2", "v2", domain="b.com")

        serialized = cookies_to_list(original)
        domains = {item["domain"] for item in serialized}
        assert "a.com" in domains
        assert "b.com" in domains

        restored = list_to_cookies(serialized)
        assert restored.get("c1") == "v1"
        assert restored.get("c2") == "v2"

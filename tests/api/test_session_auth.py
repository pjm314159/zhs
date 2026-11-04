"""会话校验模块测试

覆盖两条：CAS 换票建立服务端会话（含真实 Cookie 注入验证），
以及 getLoginUserInfo「只认用户信息、不解析 code」的判定口径与异常映射。
"""

import re
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from zhs.api.session_auth import SessionStatus, SessionVerifier, verify_session
from zhs.config import AppConfig
from zhs.session import ZhsSession

BASE = "https://onlineservice-api.zhihuishu.com"
PASSPORT = "https://passport.zhihuishu.com"
PROBE = f"{BASE}/gateway/f/v1/login/getLoginUserInfo"
TICKET_URL = f"{PROBE}?ticket=ST-123"


def _cas_response(status_code: int = 302, location: str = TICKET_URL) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"location": location}
    return resp


@pytest.fixture
def session() -> MagicMock:
    """默认 CAS 换票成功；各用例只需覆盖自己关心的部分"""
    session = MagicMock()
    session.urls.base = BASE
    session.urls.passport = PASSPORT
    session.get_no_redirect.return_value = _cas_response()
    session.get.return_value = MagicMock(status_code=200)
    return session


class TestSessionVerifier:
    """只认「能否取到用户信息」，不解析 code"""

    def test_ok_when_user_info_present(self, session: MagicMock) -> None:
        session.api_query.return_value = {
            "result": {"uuid": "Xe6arnRO", "username": "abc", "realName": "tester"},
            "code": 200,
        }
        assert SessionVerifier(session).verify() is SessionStatus.OK

    @pytest.mark.parametrize(
        "payload",
        [
            {"result": None, "code": 500},
            {"result": {}, "code": 401},
            {"result": {"realName": "tester"}, "code": 401},
            {"code": 200},
            {},
            {"result": [], "code": 200},
            {"result": "not-a-dict", "code": 200},
        ],
    )
    def test_expired_when_no_user_info(self, session: MagicMock, payload: dict[str, Any]) -> None:
        session.api_query.return_value = payload
        assert SessionVerifier(session).verify() is SessionStatus.EXPIRED

    def test_code_ignored_when_user_info_present(self, session: MagicMock) -> None:
        """任意 code 都不参与判定，能取到用户信息即成功"""
        session.api_query.return_value = {"result": {"uuid": "u"}, "code": 403}
        assert SessionVerifier(session).verify() is SessionStatus.OK

    def test_uses_get_login_user_info_with_timestamp(self, session: MagicMock) -> None:
        session.api_query.return_value = {"result": {"uuid": "u"}}
        with patch("zhs.api.session_auth.HttpClient.now_timestamp_ms", return_value=1793790692905):
            SessionVerifier(session).verify()

        args, kwargs = session.api_query.call_args
        assert args[0] == PROBE
        assert kwargs["method"] == "GET"
        assert kwargs["data"] == {"time": 1793790692905}

    def test_http_status_error_is_expired(self, session: MagicMock) -> None:
        request = httpx.Request("GET", BASE)
        response = httpx.Response(401, request=request)
        session.api_query.side_effect = httpx.HTTPStatusError("401", request=request, response=response)
        assert SessionVerifier(session).verify() is SessionStatus.EXPIRED

    def test_server_error_is_unavailable(self, session: MagicMock) -> None:
        """网关 5xx 属于服务端异常，不应误导用户重新登录"""
        request = httpx.Request("GET", BASE)
        response = httpx.Response(503, request=request)
        session.api_query.side_effect = httpx.HTTPStatusError("503", request=request, response=response)
        assert SessionVerifier(session).verify() is SessionStatus.UNAVAILABLE

    @pytest.mark.parametrize("exc", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
    def test_network_error_is_unavailable(self, session: MagicMock, exc: httpx.HTTPError) -> None:
        session.api_query.side_effect = exc
        assert SessionVerifier(session).verify() is SessionStatus.UNAVAILABLE

    def test_unexpected_response_is_expired(self, session: MagicMock) -> None:
        session.api_query.side_effect = ValueError("invalid json")
        assert SessionVerifier(session).verify() is SessionStatus.EXPIRED

    def test_verify_session_delegates(self, session: MagicMock) -> None:
        session.api_query.return_value = {"result": {"username": "abc"}}
        assert verify_session(session) is SessionStatus.OK


class TestCasHandshake:
    """探活前必须用 CASTGC 换票，否则 getLoginUserInfo 恒返回 403 未登录"""

    def test_cas_ticket_is_followed_before_probe(self, session: MagicMock) -> None:
        session.api_query.return_value = {"result": {"uuid": "u"}}
        assert SessionVerifier(session).verify() is SessionStatus.OK

        session.get_no_redirect.assert_called_once_with(f"{PASSPORT}/cas/login?service={PROBE}")
        session.get.assert_called_once_with(TICKET_URL, follow_redirects=True)
        session.api_query.assert_called_once()

    @pytest.mark.parametrize("status_code", [200, 302])
    def test_no_ticket_is_expired_without_probe(self, session: MagicMock, status_code: int) -> None:
        """CASTGC 过期时 CAS 返回登录页或重定向到登录页，直接判会话失效"""
        session.get_no_redirect.return_value = _cas_response(status_code, f"{PASSPORT}/login")
        assert SessionVerifier(session).verify() is SessionStatus.EXPIRED
        session.api_query.assert_not_called()

    def test_cas_server_error_is_unavailable(self, session: MagicMock) -> None:
        request = httpx.Request("GET", PASSPORT)
        cas_resp = _cas_response(503, "")
        cas_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=request, response=httpx.Response(503, request=request)
        )
        session.get_no_redirect.return_value = cas_resp
        assert SessionVerifier(session).verify() is SessionStatus.UNAVAILABLE

    def test_cas_network_error_is_unavailable(self, session: MagicMock) -> None:
        session.get_no_redirect.side_effect = httpx.ReadTimeout("slow")
        assert SessionVerifier(session).verify() is SessionStatus.UNAVAILABLE

    def test_ticket_follow_network_error_is_unavailable(self, session: MagicMock) -> None:
        session.get.side_effect = httpx.ConnectError("down")
        assert SessionVerifier(session).verify() is SessionStatus.UNAVAILABLE


class TestCasHandshakeIntegration:
    """真机问题回归：换票下发的 SESSION 必须出现在后续探活请求里"""

    def test_session_cookie_is_sent_to_probe(self) -> None:
        zhs = ZhsSession(AppConfig())
        zhs.cookies = {"CASTGC": "TGT-fake"}
        probe_cookie_names: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "cas/login" in url:
                return httpx.Response(302, headers={"location": TICKET_URL})
            if "ticket=" in url:
                return httpx.Response(
                    200,
                    headers={"set-cookie": "SESSION=sess-1; Domain=onlineservice-api.zhihuishu.com; Path=/"},
                    json={"code": 200},
                )
            probe_cookie_names.extend(
                part.split("=", 1)[0].strip() for part in request.headers.get("cookie", "").split(";") if part.strip()
            )
            return httpx.Response(200, json={"code": 200, "result": {"uuid": "u", "username": "n"}})

        try:
            with respx.mock:
                respx.route(method="GET", url=re.compile(r"https://.*")).mock(side_effect=handler)
                assert verify_session(zhs) is SessionStatus.OK
        finally:
            zhs.close()

        assert "SESSION" in probe_cookie_names

"""会话校验模块测试"""

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from zhs.api.session_auth import SessionStatus, SessionVerifier, verify_session


@pytest.fixture
def session() -> MagicMock:
    session = MagicMock()
    session.urls.base = "https://onlineservice-api.zhihuishu.com"
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
        assert args[0] == "https://onlineservice-api.zhihuishu.com/gateway/f/v1/login/getLoginUserInfo"
        assert kwargs["method"] == "GET"
        assert kwargs["data"] == {"time": 1793790692905}

    def test_http_status_error_is_expired(self, session: MagicMock) -> None:
        request = httpx.Request("GET", "https://onlineservice-api.zhihuishu.com")
        response = httpx.Response(401, request=request)
        session.api_query.side_effect = httpx.HTTPStatusError("401", request=request, response=response)
        assert SessionVerifier(session).verify() is SessionStatus.EXPIRED

    def test_server_error_is_unavailable(self, session: MagicMock) -> None:
        """网关 5xx 属于服务端异常，不应误导用户重新登录"""
        request = httpx.Request("GET", "https://onlineservice-api.zhihuishu.com")
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

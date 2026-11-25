"""api/passport_login_api.py 测试

验证账户密码登录协议：
- body 是带双引号的 JSON 字符串（裸密文，无 secretStr、无 dateFormate）
- status 归一化为 AccountLoginStatus（兼容 int / str）
- skipSet 支持 uuid 与 cacheId 两种路径
- HTTP/解析异常统一包装为 LoginFailed
- 日志中不出现密码
"""

import json

import httpx
import pytest
import respx
from loguru import logger

from zhs.api.http_client import HttpClient
from zhs.api.passport_login_api import AccountLoginResult, AccountLoginStatus, PassportLoginApi
from zhs.config import AppConfig
from zhs.crypto import Cipher
from zhs.exceptions import LoginFailed

LOGIN_URL = "https://user.zhihuishu.com/zhsuser/login/account"

DEMO_ACCOUNT = "demo-account"
DEMO_PASSWORD = "demo-password"
DEMO_VALIDATE = "demo-validate"


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def api(config: AppConfig) -> PassportLoginApi:
    return PassportLoginApi(HttpClient(config), config.crypto)


def _decode_body(raw: bytes, config: AppConfig) -> dict[str, str]:
    """把请求体按协议解回明文：JSON 字符串 → 密文 → AES 解密 → JSON"""
    ciphertext = json.loads(raw.decode())
    assert isinstance(ciphertext, str)
    cipher = Cipher(config.crypto.key_bytes("login_key"), config.crypto.key_bytes("login_iv"))
    payload: dict[str, str] = json.loads(cipher.decrypt(ciphertext))
    return payload


class TestLoginByPassword:
    def test_body_is_quoted_encrypted_json_string(self, api: PassportLoginApi, config: AppConfig) -> None:
        """body 为带双引号的密文串，解回 {account, password, validate}"""
        with respx.mock:
            route = respx.post(LOGIN_URL).mock(
                return_value=httpx.Response(200, json={"status": 1, "rt": {"pwd": "p1"}})
            )
            api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)

            raw = route.calls[0].request.content
            text = raw.decode()
            assert text.startswith('"') and text.endswith('"')
            assert "secretStr" not in text

            payload = _decode_body(raw, config)
            assert payload == {
                "account": DEMO_ACCOUNT,
                "password": DEMO_PASSWORD,
                "validate": DEMO_VALIDATE,
            }
            assert "dateFormate" not in payload

    def test_sends_login_headers(self, api: PassportLoginApi) -> None:
        with respx.mock:
            route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, json={"status": 1}))
            api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)

            headers = route.calls[0].request.headers
            assert headers["content-type"] == "application/json;charset=UTF-8"
            assert headers["origin"] == "https://login.zhihuishu.com"
            assert headers["referer"] == "https://login.zhihuishu.com/"

    @pytest.mark.parametrize(
        ("raw_status", "expected"),
        [
            (1, AccountLoginStatus.OK),
            (2, AccountLoginStatus.SCHOOL_UNVERIFIED),
            (-12, AccountLoginStatus.NEED_SECOND_CAPTCHA),
            (-5, AccountLoginStatus.WEAK_PASSWORD),
            (-13, AccountLoginStatus.ABNORMAL_LOGIN),
            ("1", AccountLoginStatus.OK),
            ("ACCOUNT_DISABLED", AccountLoginStatus.DISABLED),
            (999, AccountLoginStatus.UNKNOWN),
        ],
    )
    def test_status_normalized(
        self,
        api: PassportLoginApi,
        raw_status: int | str,
        expected: AccountLoginStatus,
    ) -> None:
        with respx.mock:
            respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, json={"status": raw_status, "msg": "m"}))
            result = api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)
            assert result.status is expected
            assert result.msg == "m"

    def test_maps_rt_fields(self, api: PassportLoginApi) -> None:
        with respx.mock:
            respx.post(LOGIN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"status": 2, "rt": {"pwd": "once-pwd", "uuid": "u1", "cacheId": "c1"}},
                )
            )
            result = api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)
            assert isinstance(result, AccountLoginResult)
            assert result.pwd == "once-pwd"
            assert result.uuid == "u1"
            assert result.cache_id == "c1"

    def test_http_error_wrapped(self, api: PassportLoginApi) -> None:
        with respx.mock:
            respx.post(LOGIN_URL).mock(return_value=httpx.Response(500))
            with pytest.raises(LoginFailed):
                api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)


class TestSkipSet:
    @pytest.mark.parametrize("identifier", ["demo-uuid", "demo-cache-id"])
    def test_posts_json_null(self, api: PassportLoginApi, identifier: str) -> None:
        url = f"https://user.zhihuishu.com/zhsuser/login/code/skipSet/{identifier}"
        with respx.mock:
            route = respx.post(url).mock(return_value=httpx.Response(200, json={"status": 1, "rt": {"pwd": "p2"}}))
            result = api.skip_set(identifier)

            assert route.calls[0].request.content == b"null"
            assert route.calls[0].request.headers["content-type"] == "application/json;charset=UTF-8"
            assert result.status is AccountLoginStatus.OK
            assert result.pwd == "p2"


class TestNoPasswordInLogs:
    def test_password_not_logged(self, api: PassportLoginApi) -> None:
        records: list[str] = []
        sink_id = logger.add(lambda message: records.append(str(message)), level="DEBUG")
        try:
            with respx.mock:
                respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, json={"status": 1, "rt": {"pwd": "p1"}}))
                api.login_by_password(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_VALIDATE)
        finally:
            logger.remove(sink_id)

        assert all(DEMO_PASSWORD not in record for record in records)

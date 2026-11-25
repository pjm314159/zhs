"""账户密码登录 API（user.zhihuishu.com/zhsuser）

协议要点（2026-11-25 抓包确认）：
- ``POST /zhsuser/login/account``，body 为**带双引号的 JSON 字符串**（裸密文），
  明文为 ``{"account", "password", "validate"}``，**不套 secretStr、不发 dateFormate**；
- 加密为 AES-128-CBC / PKCS#7 + Base64，密钥使用 ``CryptoConfig.login_key`` /
  ``login_iv``（该接口专用 IV）；
- ``status`` 为整数：``1`` 成功、``2`` 仅未完成学校认证（正常分支），其余为失败；
- ``skipSet/{uuid|cacheId}`` 用 body ``null`` 换取 oncePassword。

API 层只做协议：不重试、不碰验证码、不落盘、不判定登录成功与否。
"""

import json
import re
from enum import StrEnum

import httpx
from pydantic import BaseModel

from zhs.api.http_client import HttpClient
from zhs.config import CryptoConfig, UrlConfig
from zhs.crypto import Cipher
from zhs.exceptions import LoginFailed

_ORIGIN = "https://login.zhihuishu.com"
_REFERER = "https://login.zhihuishu.com/"

# 超长且无空白字符的标识符才会拼进 path，避免异常输入污染 URL
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class AccountLoginStatus(StrEnum):
    """账户密码登录响应状态（兼容 int 与 str 两种形态）"""

    OK = "1"
    SCHOOL_UNVERIFIED = "2"
    NEED_SECOND_CAPTCHA = "-12"
    WEAK_PASSWORD = "-5"
    ABNORMAL_LOGIN = "-13"
    DISABLED = "ACCOUNT_DISABLED"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> "AccountLoginStatus":
        return cls.UNKNOWN


class AccountLoginResult(BaseModel):
    """归一化后的登录响应：上层不再接触 status 的类型差异与 rt 嵌套"""

    status: AccountLoginStatus
    msg: str = ""
    pwd: str = ""
    uuid: str = ""
    cache_id: str = ""


class PassportLoginApi:
    """账户密码登录与免选择续登"""

    def __init__(self, http: HttpClient, crypto: CryptoConfig) -> None:
        self._http = http
        self._crypto = crypto

    @property
    def _urls(self) -> UrlConfig:
        return self._http.urls

    def login_by_password(self, account: str, password: str, validate: str) -> AccountLoginResult:
        """提交账号密码（密码仅进入密文，不写日志）"""
        url = f"{self._urls.user}/zhsuser/login/account"
        body = self._encrypt_body({"account": account, "password": password, "validate": validate})
        return self._parse(self._post_text(url, body))

    def skip_set(self, identifier: str) -> AccountLoginResult:
        """免选择续登；identifier 可为 rt.uuid 或 rt.cacheId"""
        if not _IDENTIFIER_PATTERN.fullmatch(identifier):
            raise LoginFailed("续登标识格式异常")
        url = f"{self._urls.user}/zhsuser/login/code/skipSet/{identifier}"
        return self._parse(self._post_text(url, "null"))

    def _encrypt_body(self, payload: dict[str, str]) -> str:
        """加密明文并二次 json.dumps，得到带双引号的 JSON 字符串"""
        cipher = Cipher(self._crypto.key_bytes("login_key"), self._crypto.key_bytes("login_iv"))
        return json.dumps(cipher.encrypt(json.dumps(payload)))

    def _post_text(self, url: str, content: str) -> dict[str, object]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": _ORIGIN,
            "Referer": _REFERER,
        }
        try:
            resp = self._http._get_client().post(url, content=content, headers=headers)
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LoginFailed(f"账户密码登录请求失败: {e}") from e
        return data

    @staticmethod
    def _parse(data: dict[str, object]) -> AccountLoginResult:
        rt = data.get("rt")
        rt_dict = rt if isinstance(rt, dict) else {}
        return AccountLoginResult(
            status=AccountLoginStatus(str(data.get("status", ""))),
            msg=str(data.get("msg") or data.get("message") or ""),
            pwd=str(rt_dict.get("pwd") or ""),
            uuid=str(rt_dict.get("uuid") or ""),
            cache_id=str(rt_dict.get("cacheId") or ""),
        )

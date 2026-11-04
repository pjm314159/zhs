"""会话校验：用 getLoginUserInfo 判断服务端是否认可当前会话

判据只有一个：能否从响应中取到用户信息（result.uuid / result.username）。
不解析 code，也不依赖任何业务列表是否为空；取不到信息一律视为会话失效。

getLoginUserInfo 受 CAS + Spring Session 保护，只认 onlineservice-api 域的
SESSION cookie。扫码登录只在 passport 域完成，cookies.json 里没有这个 cookie，
所以校验前先用 CASTGC 经 CAS 换票建立会话（浏览器打开 onlineh5 时也是这一步）。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from zhs.api.http_client import HttpClient

if TYPE_CHECKING:
    from zhs.session import ZhsSession


class SessionStatus(Enum):
    """会话校验结果"""

    OK = "ok"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class SessionVerifier:
    """先建立服务端会话，再用 getLoginUserInfo 探测登录态"""

    _PATH = "/gateway/f/v1/login/getLoginUserInfo"

    def __init__(self, session: ZhsSession) -> None:
        self._session = session

    @property
    def _probe_url(self) -> str:
        return f"{self._session.urls.base}{self._PATH}"

    def verify(self) -> SessionStatus:
        try:
            if not self._establish_session():
                return SessionStatus.EXPIRED
            resp = self._session.api_query(
                self._probe_url,
                data={"time": HttpClient.now_timestamp_ms()},
                method="GET",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.warning(f"会话校验服务端异常: {e}")
                return SessionStatus.UNAVAILABLE
            logger.debug(f"会话校验被服务端拒绝: {e}")
            return SessionStatus.EXPIRED
        except httpx.HTTPError as e:
            logger.warning(f"会话校验网络异常: {e}")
            return SessionStatus.UNAVAILABLE
        except Exception as e:
            logger.debug(f"会话校验响应异常: {e}")
            return SessionStatus.EXPIRED

        result = resp.get("result")
        if isinstance(result, dict) and (result.get("uuid") or result.get("username")):
            return SessionStatus.OK
        return SessionStatus.EXPIRED

    def _establish_session(self) -> bool:
        """用 CASTGC 换 CAS ticket，让 onlineservice-api 种下 SESSION cookie

        CASTGC 有效时 CAS 返回 302 + ticket，跟随 ticket 完成校验并写入会话；
        CASTGC 过期时 CAS 直接返回登录页，视为会话失效。
        4xx/5xx 交给 verify() 统一映射；3xx 是正常换票重定向，不能走 raise_for_status()。
        """
        cas_url = f"{self._session.urls.passport}/cas/login?service={self._probe_url}"
        resp = self._session.get_no_redirect(cas_url)
        # httpx 对 3xx 也会抛 HTTPStatusError，CAS 的 302 属于正常换票流程
        if resp.status_code >= 400:
            resp.raise_for_status()
        location = resp.headers.get("location", "")
        if not 300 <= resp.status_code < 400 or "ticket=" not in location:
            logger.debug("CAS 未签发 ticket，CASTGC 可能已过期")
            return False
        ticket_resp = self._session.get(location, follow_redirects=True)
        if ticket_resp.status_code >= 400:
            ticket_resp.raise_for_status()
        return True


def verify_session(session: ZhsSession) -> SessionStatus:
    """稳定入口：内部实现可替换，调用方无需改动"""
    return SessionVerifier(session).verify()

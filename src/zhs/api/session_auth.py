"""会话校验：用 getLoginUserInfo 判断服务端是否认可当前会话

判据只有一个：能否从响应中取到用户信息（result.uuid / result.username）。
不解析 code，也不依赖任何业务列表是否为空；取不到信息一律视为会话失效。
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
    """一次轻量请求探测登录态，调用方只依赖 verify_session()"""

    _PATH = "/gateway/f/v1/login/getLoginUserInfo"

    def __init__(self, session: ZhsSession) -> None:
        self._session = session

    def verify(self) -> SessionStatus:
        url = f"{self._session.urls.base}{self._PATH}"
        try:
            resp = self._session.api_query(url, data={"time": HttpClient.now_timestamp_ms()}, method="GET")
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


def verify_session(session: ZhsSession) -> SessionStatus:
    """稳定入口：内部实现可替换，调用方无需改动"""
    return SessionVerifier(session).verify()

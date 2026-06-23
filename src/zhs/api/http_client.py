"""HTTP 客户端封装

封装 httpx.Client 生命周期：代理、重试、headers、cookies、UUID 解析。
从原 ZhsSession 抽离的 HTTP 基础设施层。
"""

import json
import time
from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import unquote

import httpx

from zhs.config import AppConfig, CryptoConfig, UrlConfig
from zhs.utils.cookie import list_to_cookies


class HttpClient:
    """HTTP 客户端

    封装 httpx.Client，提供：
    - 代理与重试配置
    - 浏览器伪装 headers
    - Cookie 管理（含 CASLOGC → uuid 解析）
    - 通用 api_query / post_raw / stream 方法
    """

    def __init__(self, config: AppConfig, max_retries: int = 5) -> None:
        self._config = config
        self._max_retries = max_retries
        self._client: httpx.Client | None = None
        self._uuid: str | None = None
        self._cookies = httpx.Cookies()

    @property
    def urls(self) -> UrlConfig:
        """URL 配置"""
        return self._config.urls

    @property
    def crypto(self) -> CryptoConfig:
        """密钥配置"""
        return self._config.crypto

    @property
    def cookies(self) -> httpx.Cookies:
        """获取 cookies"""
        return self._cookies

    @cookies.setter
    def cookies(self, value: httpx.Cookies | list[dict[str, Any]] | dict[str, str]) -> None:
        """设置 cookies，自动解析 uuid 并添加 exitRecod"""
        if isinstance(value, httpx.Cookies):
            self._cookies = value
        elif isinstance(value, list):
            self._cookies = list_to_cookies(value)
        elif isinstance(value, dict):
            new_cookies = httpx.Cookies()
            for k, v in value.items():
                new_cookies.set(k, str(v))
            self._cookies = new_cookies

        self.parse_uuid()

        if self._client is not None:
            self._client.cookies = self._cookies

    def parse_uuid(self) -> None:
        """从 CASLOGC cookie 中解析 uuid，并设置 exitRecod_{uuid}=2"""
        caslogc = self._cookies.get("CASLOGC")
        if caslogc:
            try:
                decoded = unquote(caslogc)
                data = json.loads(decoded)
                self._uuid = data.get("uuid")
            except (json.JSONDecodeError, TypeError):
                self._uuid = None
        else:
            self._uuid = None

        if self._uuid:
            self._cookies.set(f"exitRecod_{self._uuid}", "2", domain="zhihuishu.com")

    @property
    def uuid(self) -> str | None:
        """从 CASLOGC cookie 中解析的 uuid"""
        return self._uuid

    def _get_client(self) -> httpx.Client:
        """获取或创建同步 HTTP 客户端"""
        if self._client is None:
            transport = httpx.HTTPTransport(retries=self._max_retries)
            proxy_dict = self._config.proxies.to_dict()
            proxy = proxy_dict.get("http") or proxy_dict.get("https") or None
            self._client = httpx.Client(
                transport=transport,
                proxy=proxy,
                cookies=self._cookies,
                timeout=30.0,
                headers={
                    "Accept": "*/*",
                    "sec-ch-ua": ('" Not A;Brand";v="99", "Chromium";v="101", "Google Chrome";v="101"'),
                    "sec-ch-ua-mobile": "?0",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        " AppleWebKit/537.36 (KHTML, like Gecko)"
                        " Chrome/101.0.4951.64 Safari/537.36"
                    ),
                    "sec-ch-ua-platform": '"Windows"',
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Origin": "https://studyh5.zhihuishu.com",
                    "Referer": "https://studyh5.zhihuishu.com/",
                },
            )
        return self._client

    def api_query(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """通用 API 查询

        Args:
            url: 请求 URL
            data: 请求数据（POST 为表单/JSON body，GET 为 query params）
            method: HTTP 方法
            content_type: "form" 或 "json"（仅 POST 时生效）
        """
        client = self._get_client()
        headers: dict[str, str] = dict(client.headers)

        if method.upper() == "POST":
            if content_type == "json":
                headers["Content-Type"] = "application/json;charset=UTF-8"
            elif content_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"

            if content_type == "json" and isinstance(data, dict):
                resp = client.post(url, content=json.dumps(data), headers=headers)
            else:
                resp = client.post(url, data=data, headers=headers)
        else:
            resp = client.get(url, params=data, headers=headers)

        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def post_raw(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        content_type: str = "form",
    ) -> bool:
        """原始 POST 请求（不解析 JSON，仅通过 HTTP 状态码判断成功）

        用于无返回体的提交接口（如 ai_exam_submit）。
        """
        client = self._get_client()
        headers: dict[str, str] = dict(client.headers)
        if content_type == "form":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif content_type == "json":
            headers["Content-Type"] = "application/json;charset=UTF-8"

        resp = client.post(url, data=data, headers=headers)
        resp.raise_for_status()
        return True

    def stream(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> AbstractContextManager[httpx.Response]:
        """流式请求（用于 SSE）

        返回 httpx.Response 上下文管理器，调用方需用 with 语句。
        """
        client = self._get_client()
        return client.stream(method, url, json=json, params=params, timeout=timeout)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        """GET 请求（用于 SSO 重定向）"""
        client = self._get_client()
        return client.get(url, params=params, follow_redirects=follow_redirects)

    def get_no_redirect(self, url: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET 请求（不跟随重定向，用于 SSO）"""
        client = self._get_client()
        return client.get(url, params=params, follow_redirects=False)

    def close(self) -> None:
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None

    @staticmethod
    def now_timestamp_ms() -> int:
        """当前时间戳（毫秒）"""
        return int(time.time()) * 1000

"""ZHS HTTP 会话管理模块

封装 httpx 同步/异步客户端，提供知到/Hike/AI 考试 API 查询方法。
所有密钥和 URL 从 AppConfig 获取，不硬编码。
"""

import json
import time
from typing import Any

import httpx

from zhs.config import AppConfig, CryptoConfig, UrlConfig
from zhs.crypto import Cipher, sign_hike
from zhs.exceptions import ApiError, CaptchaRequired


class ZhsSession:
    """智慧树 HTTP 会话封装"""

    def __init__(self, config: AppConfig, max_retries: int = 5) -> None:
        self._config = config
        self._max_retries = max_retries
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._uuid: str | None = None

        # Cookie jar
        self._cookies = httpx.Cookies()

    @property
    def urls(self) -> UrlConfig:
        """获取 URL 配置"""
        return self._config.urls

    @property
    def crypto(self) -> CryptoConfig:
        """获取密钥配置"""
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
            # 从 list[dict] 反序列化
            from zhs.utils.cookie import list_to_cookies

            self._cookies = list_to_cookies(value)
        elif isinstance(value, dict):
            new_cookies = httpx.Cookies()
            for k, v in value.items():
                new_cookies.set(k, str(v))
            self._cookies = new_cookies

        # 解析 uuid from CASLOGC
        self._parse_uuid()

        # 同步到已有 client
        if self._client is not None:
            self._client.cookies = self._cookies

    def _parse_uuid(self) -> None:
        """从 CASLOGC cookie 中解析 uuid"""
        from urllib.parse import unquote

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

        # 设置 exitRecod_{uuid}=2
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
            self._client = httpx.Client(
                transport=transport,
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

    def _get_async_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                cookies=self._cookies,
                timeout=30.0,
            )
        return self._async_client

    def api_query(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """通用 API 查询"""
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

    async def async_api_query(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """异步通用 API 查询"""
        client = self._get_async_client()
        headers: dict[str, str] = dict(client.headers)

        if method.upper() == "POST":
            if content_type == "json":
                headers["Content-Type"] = "application/json;charset=UTF-8"
            elif content_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"

            if content_type == "json" and isinstance(data, dict):
                resp = await client.post(url, content=json.dumps(data), headers=headers)
            else:
                resp = await client.post(url, data=data, headers=headers)
        else:
            resp = await client.get(url, params=data, headers=headers)

        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def zhidao_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
        content_type: str = "form",
        set_timestamp: bool = True,
    ) -> dict[str, Any]:
        """知到 API 查询（自动加密 + 时间戳）

        密钥从 config.crypto 获取，默认使用 video_key。
        返回码 -12 抛 CaptchaRequired。
        """
        if key is None:
            key = self.crypto.key_bytes("video_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)

        # 时间戳加入 data 后一起加密
        if set_timestamp:
            data = dict(data)  # 浅拷贝，不修改原始 data
            data["dateFormate"] = int(time.time()) * 1000

        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data: dict[str, Any] = {
            "secretStr": encrypted_data,
        }

        # dateFormate 同时作为独立表单字段
        if set_timestamp:
            form_data["dateFormate"] = data["dateFormate"]

        result = self.api_query(url, data=form_data, method=method, content_type=content_type)

        code = result.get("code", 0)
        if code == -12:
            raise CaptchaRequired("服务端要求验证码")
        if code != ok_code:
            raise ApiError(code=code, message=result.get("message", ""))

        return result

    def hike_query(
        self,
        url: str,
        data: dict[str, Any],
        sig: bool = False,
        ok_code: int = 200,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Hike API 查询（自动时间戳 + 可选签名）"""
        data = dict(data)  # 浅拷贝
        data["_"] = str(int(time.time()) * 1000)

        if sig:
            # 签名前将所有值转为字符串（与旧版一致）
            for k in data:
                data[k] = str(data[k])
            sign = sign_hike(data, self.crypto.hike_salt)
            data["signature"] = sign

        result = self.api_query(url, data=data, method=method)

        status = result.get("status", 0)
        if status != ok_code:
            raise ApiError(code=status, message=result.get("message", ""))

        return result

    async def ai_exam_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
    ) -> dict[str, Any]:
        """AI 考试 API 异步查询，密钥从 config.crypto 获取"""
        if key is None:
            key = self.crypto.key_bytes("exam_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)
        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data = {
            "secretStr": encrypted_data,
            "dateFormate": str(int(time.time()) * 1000),
        }

        result = await self.async_api_query(url, data=form_data, method=method)

        code = result.get("code", 0)
        if code != ok_code:
            raise ApiError(code=code, message=result.get("message", ""))

        return result

    def homework_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 200,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """知到作业 API 查询（AES-128-CBC + exam_key，无 dateFormate）

        与 zhidao_query 的区别：
        - 不发送 dateFormate 字段
        - 使用 exam_key 加密
        - ok_code 默认 200
        """
        if key is None:
            key = self.crypto.key_bytes("exam_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)
        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data: dict[str, Any] = {
            "secretStr": encrypted_data,
        }

        result = self.api_query(url, data=form_data, method=method, content_type=content_type)

        code = result.get("code", 0)
        if code != ok_code:
            raise ApiError(code=code, message=result.get("message", ""))

        return result

    def close(self) -> None:
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None

    async def aclose(self) -> None:
        """异步关闭客户端"""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

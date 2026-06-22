"""加密查询统一实现（策略模式）

将原 ZhsSession 的 6 套加密查询方法（zhidao_query / hike_query / ai_exam_query /
ai_exam_submit / ai_task_query / homework_query）抽象为策略表 + 统一 query 方法。

策略差异通过 QueryStrategy 数据类表达：
- key_name: 密钥名（"" 表示不加密，如 hike）
- with_dateformate: 是否发送 dateFormate 字段
- check_field: 检查字段（"code" / "status"）
- ok_value: 期望值
- content_type: "form" / "json"
- check_captcha: 是否检查 -12（知到视频 API 专属）
- has_response_body: 是否有 JSON 返回体（ai_exam_submit 无）
"""

import json
from dataclasses import dataclass
from typing import Any

from zhs.api.http_client import HttpClient
from zhs.crypto import Cipher, sign_hike
from zhs.exceptions import ApiError, CaptchaRequired


@dataclass(frozen=True)
class QueryStrategy:
    """加密查询策略（表驱动）

    Attributes:
        key_name: CryptoConfig 字段名（"" 表示不加密）
        with_dateformate: 是否发送 dateFormate 字段
        check_field: 检查字段（"code" / "status"）
        ok_value: 期望值
        content_type: "form" / "json"
        check_captcha: 是否检查 -12（知到视频 API 专属）
        has_response_body: 是否有 JSON 返回体（False 时仅检查 HTTP 状态码）
        default_method: 默认 HTTP 方法（hike 为 GET，其他为 POST）
    """

    key_name: str
    with_dateformate: bool
    check_field: str
    ok_value: int | str
    content_type: str = "form"
    check_captcha: bool = False
    has_response_body: bool = True
    default_method: str = "POST"


# 策略表（替代 6 个方法）
# fmt: off
STRATEGIES: dict[str, QueryStrategy] = {
    "zhidao":       QueryStrategy("video_key", True,  "code",   0,     "form",  check_captcha=True),
    "hike":         QueryStrategy("",          False, "status", 200,   "form",  default_method="GET"),
    "ai_exam":      QueryStrategy("exam_key",  True,  "code",   0,     "form"),
    "ai_task":      QueryStrategy("ai_key",    True,  "code",   200,   "json"),
    "homework":     QueryStrategy("exam_key",  False, "status", "200", "form"),
    "ai_exam_submit": QueryStrategy("exam_key", True, "code",   0,     "form", has_response_body=False),
}
# fmt: on


class EncryptedQuery:
    """加密查询统一实现

    通过策略名查表获取 QueryStrategy，按策略构建请求并检查响应。
    """

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client

    def query(
        self,
        strategy_name: str,
        url: str,
        data: dict[str, Any],
        method: str | None = None,
        *,
        sig: bool = False,
        key_bytes_override: bytes | None = None,
        ok_value_override: int | str | None = None,
        content_type_override: str | None = None,
    ) -> dict[str, Any]:
        """统一查询入口

        Args:
            strategy_name: 策略名（zhidao/hike/ai_exam/ai_task/homework/ai_exam_submit）
            url: 请求 URL
            data: 请求数据
            method: HTTP 方法（None 时使用策略的 default_method）
            sig: hike 签名（仅 hike 策略生效）
            key_bytes_override: 覆盖策略密钥（bytes，已解析），用于兼容旧 zhidao_query(key=...)
            ok_value_override: 覆盖策略期望值，用于兼容旧 zhidao_query(ok_code=...)
            content_type_override: 覆盖策略 content_type，用于兼容旧 zhidao_query(content_type=...)

        Returns:
            响应 JSON（ai_exam_submit 返回空字典）

        Raises:
            KeyError: 未知策略名
            CaptchaRequired: 知到视频 API 返回 -12
            ApiError: 响应码不匹配策略期望值
            httpx.HTTPStatusError: HTTP 状态码非 2xx
        """
        strategy = STRATEGIES[strategy_name]
        if method is None:
            method = strategy.default_method

        # 应用覆盖值（构造临时策略，保持 frozen dataclass 不可变）
        if key_bytes_override is not None or ok_value_override is not None or content_type_override is not None:
            strategy = self._apply_overrides(strategy, key_bytes_override, ok_value_override, content_type_override)

        # hike 策略特殊处理（无加密，仅时间戳 + 可选签名）
        if strategy_name == "hike":
            return self._hike_query(url, data, method, sig=sig)

        form_data = self._build_form_data(strategy, data, key_bytes_override=key_bytes_override)

        if not strategy.has_response_body:
            self._http.post_raw(url, data=form_data, content_type=strategy.content_type)
            return {}

        result = self._http.api_query(url, data=form_data, method=method, content_type=strategy.content_type)
        self._check_result(strategy, result)
        return result

    @staticmethod
    def _apply_overrides(
        strategy: QueryStrategy,
        key_bytes_override: bytes | None,
        ok_value_override: int | str | None,
        content_type_override: str | None,
    ) -> QueryStrategy:
        """应用覆盖值，返回新策略（保持原策略不可变）"""
        new_ok = ok_value_override if ok_value_override is not None else strategy.ok_value
        new_ct = content_type_override if content_type_override is not None else strategy.content_type
        return QueryStrategy(
            key_name=strategy.key_name,
            with_dateformate=strategy.with_dateformate,
            check_field=strategy.check_field,
            ok_value=new_ok,
            content_type=new_ct,
            check_captcha=strategy.check_captcha,
            has_response_body=strategy.has_response_body,
            default_method=strategy.default_method,
        )

    def _build_form_data(
        self,
        strategy: QueryStrategy,
        data: dict[str, Any],
        *,
        key_bytes_override: bytes | None = None,
    ) -> dict[str, Any]:
        """构建加密表单数据"""
        if not strategy.key_name and key_bytes_override is None:
            return data

        key = key_bytes_override if key_bytes_override is not None else self._http.crypto.key_bytes(strategy.key_name)
        iv = self._http.crypto.key_bytes("iv")
        cipher = Cipher(key, iv)

        payload = dict(data)
        if strategy.with_dateformate:
            payload["dateFormate"] = self._http.now_timestamp_ms()

        encrypted = cipher.encrypt(json.dumps(payload))

        form_data: dict[str, Any] = {"secretStr": encrypted}
        if strategy.with_dateformate:
            form_data["dateFormate"] = str(payload["dateFormate"])
        return form_data

    def _check_result(self, strategy: QueryStrategy, result: dict[str, Any]) -> None:
        """检查响应码"""
        actual = result.get(strategy.check_field, strategy.ok_value)

        if strategy.check_captcha and actual == -12:
            raise CaptchaRequired("服务端要求验证码")

        if actual != strategy.ok_value:
            code = int(actual) if isinstance(actual, str) and actual.isdigit() else actual
            message = result.get("message", result.get("msg", ""))
            raise ApiError(code=code if isinstance(code, int) else -1, message=message)

    def _hike_query(
        self,
        url: str,
        data: dict[str, Any],
        method: str = "GET",
        *,
        sig: bool = False,
    ) -> dict[str, Any]:
        """hike 查询（无加密，时间戳 + 可选签名）"""
        data = dict(data)
        data["_"] = str(self._http.now_timestamp_ms())

        if sig:
            for k in data:
                data[k] = str(data[k])
            sign = sign_hike(data, self._http.crypto.hike_salt)
            data["signature"] = sign

        result = self._http.api_query(url, data=data, method=method)
        status = result.get("status", 0)
        if status != 200:
            raise ApiError(code=status, message=result.get("message", ""))
        return result

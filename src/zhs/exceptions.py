"""ZHS 全局异常定义"""


class ZhsError(Exception):
    """ZHS 基础异常"""


class ApiError(ZhsError):
    """API 返回错误"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"API error {code}: {message}")


class CaptchaRequired(ZhsError):
    """服务端要求验证码（API 返回 code -12）

    携带触发时的响应与请求体，便于调用方决定是否自动求解。
    """

    def __init__(
        self,
        message: str,
        *,
        response: dict | None = None,
        payload: dict | None = None,
        url: str = "",
    ) -> None:
        super().__init__(message)
        self.response = response or {}
        self.payload = payload or {}
        self.url = url


class SliderVerificationRequired(ZhsError):
    """作业答题需要滑块验证"""


class LoginFailed(ZhsError):
    """登录失败"""


class TimeLimitExceeded(ZhsError):
    """刷课时间超过限制"""


class ApiUnavailableError(ZhsError):
    """API 服务不可用（网络错误、5xx 等）"""


class RateLimitError(ZhsError):
    """API 限流（429 Too Many Requests 等）"""

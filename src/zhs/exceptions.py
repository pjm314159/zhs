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
    """服务端要求验证码（API 返回 code -12）"""


class LoginFailed(ZhsError):
    """登录失败"""


class InvalidCookies(ZhsError):
    """Cookies 无效或过期"""


class TimeLimitExceeded(ZhsError):
    """刷课时间超过限制"""

"""验证码求解的数据模型。"""

from dataclasses import dataclass, field
from typing import Any, Literal

CaptchaKind = Literal["slide", "click"]


@dataclass(frozen=True)
class CaptchaChallenge:
    """一次取题的结果。

    ``front`` 在点选题里是提示文案字符串，在滑块题里是拼图 URL 列表。
    """

    captcha_id: str
    kind: CaptchaKind
    token: str
    bg_url: str
    front: str | list[str]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptchaSolution:
    """可直接提交给业务接口的结果。"""

    validate: str
    raw_validate: str

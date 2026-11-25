"""点选验证码：坐标换算与 data 编码。

载荷只有 ``m`` / ``p`` / ``ext`` 三个密文字段，``d`` 恒为空。
与滑块的两处差异：``aes_click`` 不拼 crc32；``p`` / ``ext`` 各自尾部要补 crc32。
"""

from typing import Any

from zhs.captcha import codec

CSS_WIDTH = 320


def to_css(x: float, y: float, image_width: int, css_width: int = CSS_WIDTH) -> tuple[int, int]:
    """原图坐标等比换算到点选画布坐标。"""
    if image_width <= 0:
        raise ValueError("图片宽度非法")
    scale = css_width / image_width
    return round(x * scale), round(y * scale)


def build_data(token: str, x: int, y: int) -> dict[str, Any]:
    """构造点选 ``check`` 的 data（单点题：``t=0``、``ext=1,0``）。"""
    position = codec.with_crc(codec.xor_encode(token, f"{x},{y},0"))
    extent = codec.with_crc(codec.xor_encode(token, "1,0"))
    return {
        "d": "",
        "m": codec.aes_click("00000000"),
        "p": codec.aes_click(position),
        "ext": codec.aes_click(extent),
    }


__all__ = ["CSS_WIDTH", "build_data", "to_css"]

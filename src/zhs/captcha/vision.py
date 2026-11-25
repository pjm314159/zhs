"""点选识图客户端。

一次非流式调用：整图 + 提示文案 → 原图坐标。
``max_tokens`` 必须给足：当前网关的模型会先写大段分析再给 JSON，
预算不足会以 ``finish_reason=length`` 结束且 content 为空。
"""

import base64
import json
import re
from dataclasses import dataclass
from io import BytesIO

from loguru import logger
from openai import OpenAI
from PIL import Image

PROMPT = """这是网易易盾的点选验证码图片，尺寸 {width}x{height} 像素。
提示语：{tips}

找出提示语要求点击的那个字符（注意颜色、大小写，以及「朝向一样」这类约束），
给出它在图片中的中心坐标。

只输出 JSON，不要解释：
{{"x": <横坐标整数>, "y": <纵坐标整数>}}"""

@dataclass(frozen=True)
class VisionOptions:
    """识图调用参数。"""

    api_key: str
    base_url: str
    model: str
    timeout: float = 120.0
    max_tokens: int = 8000


def click_point(options: VisionOptions, image: bytes, tips: str) -> tuple[float, float] | None:
    """返回字符中心点的原图坐标；失败返回 None。"""
    if not options.api_key or not options.model:
        logger.warning("验证码识图缺少 api_key 或 model")
        return None

    try:
        with Image.open(BytesIO(image)) as img:
            width, height = img.size
            mime = f"image/{(img.format or 'jpeg').lower()}"
    except Exception as exc:
        logger.warning(f"验证码图片解析失败: {exc}")
        return None

    payload = base64.b64encode(image).decode()
    client = OpenAI(api_key=options.api_key, base_url=options.base_url, timeout=options.timeout)
    try:
        response = client.chat.completions.create(  # type: ignore[call-overload]
            model=options.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT.format(width=width, height=height, tips=tips)},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{payload}"}},
                    ],
                }
            ],
            temperature=0,
            max_tokens=options.max_tokens,
        )
    except Exception as exc:
        logger.warning(f"验证码识图请求失败: {exc}")
        return None
    finally:
        client.close()

    choice = response.choices[0]
    content = choice.message.content or ""
    if not content:
        logger.warning(f"验证码识图返回空内容（finish_reason={choice.finish_reason}）")
        return None
    return _parse(content)


def _parse(content: str) -> tuple[float, float] | None:
    """容忍 JSON 被包裹在说明文字或代码块里。"""
    match = re.search(r"\{[^{}]*\}", content)
    if match:
        try:
            data = json.loads(match.group(0))
            return float(data["x"]), float(data["y"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    pair = re.search(r"[xX]\s*[=:：]\s*(-?\d+(?:\.\d+)?).*?[yY]\s*[=:：]\s*(-?\d+(?:\.\d+)?)", content, re.S)
    if pair:
        return float(pair.group(1)), float(pair.group(2))

    logger.warning(f"验证码识图结果无法解析: {content[:120]}")
    return None


__all__ = ["PROMPT", "VisionOptions", "click_point"]

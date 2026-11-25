"""滑块验证码：缺口识别、轨迹生成与 data 编码。

缺口识别只用 Canny 边缘匹配（实测 10 次全过），不引入多算法综合。
OpenCV 与 numpy 属于可选依赖，未安装时 ``available()`` 返回 False。
"""

import math
import random
from typing import Any

from zhs.captcha import codec

try:  # pragma: no cover - 取决于是否安装 extra
    import cv2
    import numpy as np

    _HAS_CV = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _HAS_CV = False

SAMPLE_NUM = 50


def available() -> bool:
    """OpenCV 是否可用。"""
    return _HAS_CV


def find_gap_x(background: Any, front: Any) -> float:
    """返回缺口左边缘在背景图中的横坐标。"""
    if not _HAS_CV:
        raise RuntimeError("未安装 opencv，无法识别滑块缺口")

    image = front
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)

    rgb = image[:, :, :3]
    alpha = image[:, :, 3]
    _, mask = cv2.threshold(alpha, 50, 255, cv2.THRESH_BINARY)

    background_edge = cv2.Canny(cv2.cvtColor(background, cv2.COLOR_BGR2GRAY), 50, 150)
    front_edge = cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY), 50, 150)
    front_edge = cv2.bitwise_and(front_edge, front_edge, mask=cv2.erode(mask, np.ones((3, 3), np.uint8)))

    result = cv2.matchTemplate(background_edge, front_edge, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(result)[3][0])


def build_track(distance: float, duration_ms: int = 800) -> list[tuple[float, float, int, int]]:
    """生成「加速 → 快速接近 → 减速 → 对齐」四段轨迹。"""
    points: list[tuple[float, float, int, int]] = []
    current = 0.0
    elapsed = 0
    middle = distance * random.uniform(0.50, 0.60)

    while current < middle:
        acceleration = 2.0 + random.uniform(0, 3.0) * (current / max(middle, 1))
        current = min(middle, current + acceleration + random.uniform(0, 1))
        y = random.gauss(0, 0.8) + math.sin(current / 25) * 2
        elapsed += random.randint(6, 12)
        points.append((current, y, elapsed, 1))

    fast = distance * random.uniform(0.88, 0.94)
    while current < fast:
        velocity = 4.0 + random.uniform(0, 4) * (1 - (current - middle) / max(fast - middle, 1))
        current = min(fast, current + velocity + random.uniform(-0.3, 0.8))
        y = random.gauss(0, 0.6) + math.sin(current / 18) * 1.2
        elapsed += random.randint(7, 14)
        points.append((current, y, elapsed, 1))

    while current < distance - 3:
        velocity = max(0.3, 2.5 * (distance - current) / max(distance, 1))
        current = min(distance - 3, current + velocity + random.uniform(-0.3, 0.2))
        y = random.gauss(0, 0.5) + math.sin(current / 12)
        elapsed += random.randint(15, 30)
        points.append((current, y, elapsed, 1))

    while current < distance:
        current = min(distance, current + random.uniform(0.2, 0.5))
        elapsed += random.randint(20, 45)
        points.append((current, random.gauss(0, 0.3), elapsed, 1))

    if not points or points[-1][0] != distance:
        elapsed += random.randint(5, 10)
        points.append((distance, 0.0, elapsed, 1))
    return points


def _sample(values: list[str], target_length: int) -> list[str]:
    if len(values) <= target_length:
        return values
    result: list[str] = []
    for index, value in enumerate(values):
        if index >= (len(result) * (len(values) - 1)) / (target_length - 1):
            result.append(value)
    return result


def build_data(token: str, trace: list[tuple[float, float, int, int]], distance: float, width: int) -> dict[str, Any]:
    """构造滑块 ``check`` 的 data（五个字段，均为 aes 密文）。"""
    trace_data = [
        codec.xor_encode(token, f"{round(x)},{round(y)},{elapsed},1") for x, y, elapsed, _ in trace
    ]
    timestamps = sorted({elapsed for _, _, elapsed, _ in trace})
    position_percent = int(distance) / width * 100
    return {
        "d": codec.aes(":".join(_sample(trace_data, SAMPLE_NUM))),
        "m": "",
        "p": codec.aes(codec.xor_encode(token, str(position_percent))),
        "f": codec.aes(codec.xor_encode(token, ",".join(str(value) for value in timestamps))),
        "ext": codec.aes(codec.xor_encode(token, f"1,{len(trace_data)}")),
    }


__all__ = ["SAMPLE_NUM", "available", "build_data", "build_track", "find_gap_x"]

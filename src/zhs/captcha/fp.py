"""fp 的读取与格式校验。

fp 是 IRisk 设备指纹，约 190 字符，尾段为 ``:13 位毫秒时间戳``。
只能由使用者手动采集后整串填入配置，不支持续期或改写。
"""

import re

FP_MIN_LEN = 150
FP_MAX_LEN = 260
_FP_TAIL = re.compile(r":\d{13}$")


def normalize_fp(text: str) -> str:
    """去掉空白、换行与包裹引号；不做其它改写。"""
    return text.strip().strip('"').strip("'").replace("\r", "").replace("\n", "")


def validate_fp_format(fp: str) -> list[str]:
    """返回问题列表，空列表表示格式合法。"""
    problems: list[str] = []
    if not fp:
        problems.append("fp 为空")
        return problems
    if not (FP_MIN_LEN <= len(fp) <= FP_MAX_LEN):
        problems.append(f"长度异常: {len(fp)}（预期约 190）")
    if not _FP_TAIL.search(fp):
        problems.append("尾段不是 :13位毫秒时间戳")
    if "%" in fp:
        problems.append("疑似未做 decodeURIComponent（含 %xx）")
    return problems


__all__ = ["FP_MAX_LEN", "FP_MIN_LEN", "normalize_fp", "validate_fp_format"]

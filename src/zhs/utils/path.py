"""路径工具模块"""

from itertools import zip_longest
from pathlib import Path


def get_data_dir() -> Path:
    """获取数据目录（.zhs/，项目根目录下），不存在时自动创建"""
    data_dir = Path(".zhs")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """获取配置文件路径（.zhs/config.toml）"""
    return get_data_dir() / "config.toml"


def version_cmp(v1: str, v2: str) -> int:
    """语义化版本比较，返回负数/零/正数表示 v1 小于/等于/大于 v2"""
    parts1 = [int(p) for p in v1.split(".")]
    parts2 = [int(p) for p in v2.split(".")]
    for p1, p2 in zip_longest(parts1, parts2, fillvalue=0):
        diff = p1 - p2
        if diff:
            return diff
    return 0

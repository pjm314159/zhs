"""路径工具模块"""

from pathlib import Path


def get_data_dir() -> Path:
    """获取数据目录（.zhs/，项目根目录下），不存在时自动创建"""
    data_dir = Path(".zhs")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """获取配置文件路径（.zhs/config.toml）"""
    return get_data_dir() / "config.toml"

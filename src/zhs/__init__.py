"""ZHS - 智慧树自动刷课工具"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # 单一来源：已安装分发的版本（由 pyproject.toml 决定，发布流程保证其准确）
    __version__ = _pkg_version("zhs")
except PackageNotFoundError:  # 未安装（例如直接从源码树运行）
    __version__ = "0.0.0+unknown"

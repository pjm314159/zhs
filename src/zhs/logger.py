"""ZHS 日志模块

基于 loguru 的生产级日志系统，提供：
- 双通道输出（stderr + 文件）
- 敏感信息自动脱敏
- 文件轮转（10MB/7天/zip压缩）
- 幂等初始化
"""

import re
import sys
from pathlib import Path

from loguru import logger

from zhs.config import AppConfig
from zhs.utils.path import get_data_dir

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # CASLOGC=<value>
    re.compile(r"(CASLOGC=)\S+", re.IGNORECASE),
    # token=<value>
    re.compile(r"(token=)\S+", re.IGNORECASE),
    # password=<value>
    re.compile(r"(password=)\S+", re.IGNORECASE),
    # apiKey=<value>
    re.compile(r"(apiKey=)\S+", re.IGNORECASE),
    # Authorization: Bearer <value>
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
)


def _sensitive_filter(record: dict) -> bool:  # type: ignore[type-arg]
    """对 record["message"] 中的敏感字段进行脱敏，始终返回 True（不过滤任何记录）"""
    msg = record["message"]
    for pattern in _SENSITIVE_PATTERNS:
        msg = pattern.sub(r"\1***", msg)
    record["message"] = msg
    return True


# ---------------------------------------------------------------------------
# 格式定义
# ---------------------------------------------------------------------------

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level:<7}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - {message}"
)

_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {thread.name} | {name}:{function}:{line} | {message}"

# ---------------------------------------------------------------------------
# 幂等控制
# ---------------------------------------------------------------------------

_initialized: bool = False


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def setup_logging(config: AppConfig, log_dir: Path | None = None) -> None:
    """配置 loguru 日志系统。

    - 移除 loguru 默认 sink（id=0）
    - 注册 stderr sink（级别由 config.log_level 控制）
    - 注册文件 sink（始终 DEBUG，轮转 10MB/7天）
    - 注册敏感信息过滤 filter
    - 确保幂等：重复调用不会重复注册 sink

    Args:
        config: 应用配置
        log_dir: 日志文件目录，默认为 .zhs/logs/
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return

    # 移除 loguru 默认 sink
    logger.remove()

    # 注册 stderr sink（带敏感信息过滤）
    log_level = config.display.log_level.upper()
    logger.add(
        sys.stderr,
        level=log_level,
        format=_CONSOLE_FORMAT,
        filter=_sensitive_filter,  # type: ignore[arg-type]
    )

    # 注册文件 sink（带敏感信息过滤）
    if log_dir is None:
        log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "zhs_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        filter=_sensitive_filter,  # type: ignore[arg-type]
    )

    _initialized = True


def get_log_dir() -> Path:
    """返回日志文件目录路径（<data_dir>/logs/），自动创建"""
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

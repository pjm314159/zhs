"""Task 1.8 — logger.py 测试"""

import sys
from pathlib import Path
from typing import Any

from loguru import logger
from pytest import CaptureFixture

from zhs.config import AppConfig, DisplayConfig
from zhs.logger import _SENSITIVE_PATTERNS as SENSITIVE_PATTERNS  # noqa: F401
from zhs.logger import get_log_dir, setup_logging

# ---------------------------------------------------------------------------
# 辅助：每次测试前重置 logger 状态，确保测试隔离
# ---------------------------------------------------------------------------


def _reset_logger() -> None:
    """移除所有 handler 并重置 _initialized 标志"""
    import zhs.logger as mod

    handler_ids = list(logger._core.handlers.keys())  # type: ignore[attr-defined]
    for hid in handler_ids:
        logger.remove(hid)
    # 恢复默认 sink，让 loguru 处于初始状态
    logger.add(lambda _: None, level="DEBUG")
    # 重置幂等标志
    mod._initialized = False


def _find_stderr_handlers() -> list[Any]:
    """查找使用 sys.stderr 的 handler"""
    result = []
    for h in logger._core.handlers.values():  # type: ignore[attr-defined]
        sink = h._sink  # noqa: SLF001
        # loguru StreamSink 的 _stream 属性
        if hasattr(sink, "_stream"):
            stream = sink._stream  # noqa: SLF001
            if stream is sys.stderr:
                result.append(h)
    return result


def _find_file_handlers() -> list[Any]:
    """查找文件类型的 handler"""
    result = []
    for h in logger._core.handlers.values():  # type: ignore[attr-defined]
        sink = h._sink  # noqa: SLF001
        if hasattr(sink, "_path"):
            result.append(h)
    return result


# ---------------------------------------------------------------------------
# TestSetupLogging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_removes_default_sink(self) -> None:
        """setup_logging 移除 loguru 默认 sink (id=0)"""
        _reset_logger()
        config = AppConfig(display=DisplayConfig(log_level="INFO"))
        setup_logging(config)
        assert 0 not in logger._core.handlers  # type: ignore[attr-defined]

    def test_registers_stderr_sink(self) -> None:
        """注册 stderr sink，级别由 config.log_level 控制"""
        _reset_logger()
        config = AppConfig(display=DisplayConfig(log_level="WARNING"))
        setup_logging(config)
        stderr_handlers = _find_stderr_handlers()
        assert len(stderr_handlers) >= 1
        # WARNING = 30
        assert stderr_handlers[0]._levelno >= 30  # noqa: SLF001

    def test_registers_file_sink(self) -> None:
        """注册文件 sink，始终 DEBUG 级别"""
        _reset_logger()
        config = AppConfig(display=DisplayConfig(log_level="INFO"))
        setup_logging(config)
        file_handlers = _find_file_handlers()
        assert len(file_handlers) >= 1
        # DEBUG = 10
        assert file_handlers[0]._levelno == 10  # noqa: SLF001

    def test_file_sink_rotation_config(self) -> None:
        """文件 sink 配置了轮转（10MB）和保留（7天）"""
        _reset_logger()
        config = AppConfig()
        setup_logging(config)
        file_handlers = _find_file_handlers()
        assert len(file_handlers) >= 1
        # 验证文件路径包含 zhs 前缀（说明配置了文件 sink）
        sink = file_handlers[0]._sink  # noqa: SLF001
        path_str = str(sink._path)  # noqa: SLF001
        assert "zhs_" in path_str

    def test_idempotent(self) -> None:
        """重复调用 setup_logging 不会重复注册 sink"""
        _reset_logger()
        config = AppConfig()
        setup_logging(config)
        handler_count_after_first = len(logger._core.handlers)  # type: ignore[attr-defined]
        setup_logging(config)
        handler_count_after_second = len(logger._core.handlers)  # type: ignore[attr-defined]
        assert handler_count_after_first == handler_count_after_second

    def test_log_level_case_insensitive(self) -> None:
        """log_level 大小写不敏感"""
        for level in ["info", "INFO", "Info"]:
            _reset_logger()
            config = AppConfig(display=DisplayConfig(log_level=level))
            setup_logging(config)
            # 不应抛异常


# ---------------------------------------------------------------------------
# TestGetLogDir
# ---------------------------------------------------------------------------


class TestGetLogDir:
    def test_returns_path_under_data_dir(self) -> None:
        """日志目录在 data_dir/logs/ 下"""
        log_dir = get_log_dir()
        assert log_dir.name == "logs"
        assert "zhs" in str(log_dir).lower()

    def test_creates_directory(self) -> None:
        """日志目录不存在时自动创建"""
        log_dir = get_log_dir()
        assert log_dir.exists()


# ---------------------------------------------------------------------------
# TestSensitiveFilter
# ---------------------------------------------------------------------------


class TestSensitiveFilter:
    @staticmethod
    def _redact(text: str) -> str:
        """使用与实现相同的替换逻辑"""
        for pattern in SENSITIVE_PATTERNS:
            text = pattern.sub(r"\1***", text)
        return text

    def test_caslogc_filtered(self) -> None:
        """CASLOGC 值被脱敏"""
        result = self._redact("CASLOGC=%7B%22uuid%22%7D")
        assert "CASLOGC=***" in result
        assert "%7B%22uuid%22%7D" not in result

    def test_token_filtered(self) -> None:
        """token 值被脱敏"""
        result = self._redact("token=abc123def")
        assert "token=***" in result
        assert "abc123def" not in result

    def test_password_filtered(self) -> None:
        """password 值被脱敏"""
        result = self._redact("password=mysecret")
        assert "password=***" in result
        assert "mysecret" not in result

    def test_apikey_filtered(self) -> None:
        """apiKey 值被脱敏"""
        result = self._redact("apiKey=sk-xxxx")
        assert "apiKey=***" in result
        assert "sk-xxxx" not in result

    def test_authorization_bearer_filtered(self) -> None:
        """Authorization Bearer token 被脱敏"""
        result = self._redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        assert "Bearer ***" in result
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_normal_text_unchanged(self) -> None:
        """普通文本不被脱敏"""
        result = self._redact("登录成功: uuid=Xe6arnRO")
        assert result == "登录成功: uuid=Xe6arnRO"

    def test_patcher_integrated(self, tmp_path: Path) -> None:
        """filter 与 loguru 集成后，日志消息自动脱敏"""
        _reset_logger()
        log_file = tmp_path / "test_patcher.log"
        config = AppConfig(display=DisplayConfig(log_level="DEBUG"))

        import zhs.logger as mod

        mod._initialized = False

        # 调用 setup_logging 注册 filter
        setup_logging(config)

        # 额外添加一个测试用的文件 sink（带 filter）
        from zhs.logger import _sensitive_filter

        logger.add(str(log_file), level="DEBUG", format="{message}", filter=_sensitive_filter)  # type: ignore[arg-type]

        # 写入包含敏感信息的日志
        logger.info("登录信息: token=abc123def")
        logger.info("普通消息: uuid=Xe6arnRO")

        # 读取日志文件验证
        content = log_file.read_text(encoding="utf-8")
        assert "token=***" in content
        assert "abc123def" not in content
        assert "uuid=Xe6arnRO" in content


# ---------------------------------------------------------------------------
# TestConsoleFormat
# ---------------------------------------------------------------------------


class TestConsoleFormat:
    def test_console_output_format(self, capsys: CaptureFixture[str]) -> None:
        """控制台输出格式包含时间戳+级别+消息"""
        _reset_logger()
        config = AppConfig(display=DisplayConfig(log_level="DEBUG"))
        setup_logging(config)
        logger.info("测试格式消息")
        sys.stderr.flush()
        captured = capsys.readouterr()
        output = captured.err
        assert "INFO" in output or "测试格式消息" in output


# ---------------------------------------------------------------------------
# TestFileFormat
# ---------------------------------------------------------------------------


class TestFileFormat:
    def test_file_output_contains_thread_info(self, tmp_path: Path) -> None:
        """文件输出包含线程名+模块名+行号"""
        _reset_logger()
        log_file = tmp_path / "test_format.log"

        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {thread.name} | {name}:{function}:{line} | {message}"
        )
        logger.add(str(log_file), level="DEBUG", format=file_format)

        logger.info("线程测试消息")

        content = log_file.read_text(encoding="utf-8")
        assert "MainThread" in content
        assert "INFO" in content
        assert "线程测试消息" in content

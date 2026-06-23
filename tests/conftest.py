"""ZHS 测试全局 fixtures"""

from pathlib import Path
from typing import Any

import pytest

from zhs.config import AppConfig


@pytest.fixture
def fixtures_dir() -> Path:
    """测试 fixtures 目录"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_config() -> AppConfig:
    """默认 AppConfig 实例"""
    return AppConfig()


@pytest.fixture
def api_response_factory() -> Any:
    """通用 API 响应工厂"""

    def _make(
        code: int = 0,
        data: dict[str, Any] | list[dict[str, Any]] | None = None,
        message: str = "",
        status: int = 200,
    ) -> dict[str, Any]:
        return {"code": code, "data": data or {}, "message": message, "status": status}

    return _make

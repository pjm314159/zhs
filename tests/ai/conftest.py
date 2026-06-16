"""AI 模块测试 conftest"""

from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_ppt_initialize_cache() -> Any:
    """自动 mock PptConverter._initialize_cache 避免真实 API 调用"""
    with patch("zhs.ai.ppt.PptConverter._initialize_cache"):
        yield

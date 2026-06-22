"""LLMProviderFactory 测试"""

from unittest.mock import MagicMock

from zhs.config import AIConfig
from zhs.llm.base import LLMProvider
from zhs.llm.factory import LLMProviderFactory
from zhs.llm.openai import OpenAIProvider
from zhs.llm.zhidao import ZhidaoAIProvider


class TestLLMProviderFactoryCreate:
    """LLMProviderFactory.create 工厂方法"""

    def test_disabled_ai_returns_none(self) -> None:
        """AI 禁用时返回 None"""
        config = AIConfig(enabled=False)
        assert LLMProviderFactory.create(config) is None

    def test_use_zhidao_ai_returns_zhidao_provider(self) -> None:
        """use_zhidao_ai=True 返回 ZhidaoAIProvider"""
        config = AIConfig(enabled=True, use_zhidao_ai=True)
        session = MagicMock()
        provider = LLMProviderFactory.create(config, session=session, course_id="123", course_name="测试课程")
        assert isinstance(provider, ZhidaoAIProvider)

    def test_openai_api_key_returns_openai_provider(self) -> None:
        """有 api_key 且 use_zhidao_ai=False 返回 OpenAIProvider"""
        config = AIConfig(
            enabled=True,
            use_zhidao_ai=False,
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )
        provider = LLMProviderFactory.create(config)
        assert isinstance(provider, OpenAIProvider)

    def test_no_api_key_returns_none(self) -> None:
        """启用 AI 但无 api_key 且不使用知到 AI 时返回 None"""
        config = AIConfig(enabled=True, use_zhidao_ai=False, api_key="")
        assert LLMProviderFactory.create(config) is None

    def test_returns_llm_provider_subclass(self) -> None:
        """返回值是 LLMProvider 子类"""
        config = AIConfig(enabled=True, use_zhidao_ai=False, api_key="sk-test")
        provider = LLMProviderFactory.create(config)
        assert isinstance(provider, LLMProvider)

    def test_zhidao_provider_receives_course_info(self) -> None:
        """ZhidaoAIProvider 接收 course_id 和 course_name"""
        config = AIConfig(enabled=True, use_zhidao_ai=True)
        session = MagicMock()
        provider = LLMProviderFactory.create(config, session=session, course_id="999", course_name="数学")
        assert isinstance(provider, ZhidaoAIProvider)
        assert provider._course_id == "999"
        assert provider._course_name == "数学"

    def test_openai_provider_receives_config(self) -> None:
        """OpenAIProvider 接收 api_key/base_url/model"""
        config = AIConfig(
            enabled=True,
            use_zhidao_ai=False,
            api_key="sk-abc",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        provider = LLMProviderFactory.create(config)
        assert isinstance(provider, OpenAIProvider)
        assert provider._model_name == "deepseek-chat"

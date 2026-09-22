"""Task 5.3 — llm/openai.py TDD"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.exceptions import ZhsError
from zhs.llm.openai import OpenAIProvider


class TestOpenAIRetryPolicy:
    """重试策略：4xx（429 限流除外）属于请求本身的问题，重试无意义"""

    @patch("zhs.llm.openai.time.sleep")
    @patch("zhs.llm.openai.OpenAI")
    def test_402_not_retried(self, mock_openai_cls: MagicMock, mock_sleep: MagicMock) -> None:
        """402 余额不足：只请求一次，不 sleep 重试"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        err = Exception("Error code: 402 - Insufficient Balance")
        err.status_code = 402  # type: ignore[attr-defined]
        mock_client.chat.completions.create.side_effect = err

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        with pytest.raises(ZhsError, match="non-retryable"):
            provider.completion("test prompt")

        mock_client.chat.completions.create.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("zhs.llm.openai.time.sleep")
    @patch("zhs.llm.openai.OpenAI")
    def test_429_is_retried(self, mock_openai_cls: MagicMock, mock_sleep: MagicMock) -> None:
        """429 限流：仍重试到上限"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        err = Exception("Error code: 429 - rate limit")
        err.status_code = 429  # type: ignore[attr-defined]
        mock_client.chat.completions.create.side_effect = err

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        with pytest.raises(ZhsError, match="after 3 retries"):
            provider.completion("test prompt")

        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("zhs.llm.openai.time.sleep")
    @patch("zhs.llm.openai.OpenAI")
    def test_unlisted_4xx_is_retried(self, mock_openai_cls: MagicMock, mock_sleep: MagicMock) -> None:
        """未列入 NON_RETRYABLE_STATUS 的 4xx（如 418）：仍按可重试处理"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        err = Exception("Error code: 418 - teapot")
        err.status_code = 418  # type: ignore[attr-defined]
        mock_client.chat.completions.create.side_effect = err

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        with pytest.raises(ZhsError, match="after 3 retries"):
            provider.completion("test prompt")

        assert mock_sleep.call_count == 2

    @patch("zhs.llm.openai.time.sleep")
    @patch("zhs.llm.openai.OpenAI")
    def test_error_without_status_code_is_retried(self, mock_openai_cls: MagicMock, mock_sleep: MagicMock) -> None:
        """无状态码的错误（网络/超时）：仍按原策略重试"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("Connection error")

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        with pytest.raises(ZhsError, match="after 3 retries"):
            provider.completion("test prompt")

        assert mock_sleep.call_count == 2


class TestOpenAICompletion:
    """OpenAI 兼容接口 completion"""

    @patch("zhs.llm.openai.OpenAI")
    def test_stream_completion(self, mock_openai_cls: MagicMock) -> None:
        """流式响应解析"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # 模拟流式响应
        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="```"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="answer\n"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content='[{"id": 1}]'))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="\n```"))]),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks)

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.openai.OpenAI")
    def test_api_error_handling(self, mock_openai_cls: MagicMock) -> None:
        """API 错误处理"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        with pytest.raises(Exception, match="API error"):
            provider.completion("test prompt")

    @patch("zhs.llm.openai.OpenAI")
    def test_custom_base_url(self, mock_openai_cls: MagicMock) -> None:
        """自定义 base_url"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        chunks = [MagicMock(choices=[MagicMock(delta=MagicMock(content="```answer\nok\n```"))])]
        mock_client.chat.completions.create.return_value = iter(chunks)

        provider = OpenAIProvider(
            api_key="test-key",
            base_url="https://api.moonshot.cn/v1",
            model_name="moonshot-v1-32k",
        )
        provider.completion("test")
        # 验证 OpenAI 客户端使用自定义 base_url
        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.moonshot.cn/v1"

    @patch("zhs.llm.openai.OpenAI")
    def test_model_name_passed(self, mock_openai_cls: MagicMock) -> None:
        """model_name 传递给 API"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        chunks = [MagicMock(choices=[MagicMock(delta=MagicMock(content="```answer\nok\n```"))])]
        mock_client.chat.completions.create.return_value = iter(chunks)

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-3.5-turbo")
        provider.completion("test")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-3.5-turbo"

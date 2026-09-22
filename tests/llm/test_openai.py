"""Task 5.3 — llm/openai.py TDD"""

import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from zhs.exceptions import ZhsError
from zhs.llm.openai import OpenAIProvider


def _chunk(content: str) -> MagicMock:
    """构造一个流式 chunk"""
    return MagicMock(choices=[MagicMock(delta=MagicMock(content=content))])


class _FakeStream:
    """可迭代的假流：记录已产出 chunk 数，close 可观测

    gap > 0 时每个 chunk 前 sleep，给主线程留出「提前终止」的时间窗口。
    """

    def __init__(self, contents: list[str], gap: float = 0.0, close_error: bool = False) -> None:
        self._contents = contents
        self._gap = gap
        self._close_error = close_error
        self.yielded = 0
        self.closed = False

    def __iter__(self) -> Iterator[MagicMock]:
        for content in self._contents:
            if self._gap:
                time.sleep(self._gap)
            self.yielded += 1
            yield _chunk(content)

    def close(self) -> None:
        self.closed = True
        if self._close_error:
            raise RuntimeError("close failed")


class TestStreamEarlyTermination:
    """提前终止后必须停止 reader 并关闭流（否则队列无人消费、连接泄漏）"""

    @patch("zhs.llm.openai.OpenAI")
    def test_reader_stops_and_stream_closed_after_early_termination(self, mock_openai_cls: MagicMock) -> None:
        """找到答案标记后：reader 停止拉取、stream.close() 被调用"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        tail = [f"padding-{i}" for i in range(50)]
        stream = _FakeStream(["```answer\n", '[{"id": 103}]', "\n```", *tail], gap=0.05)
        mock_client.chat.completions.create.return_value = stream

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        result = provider.completion("prompt")

        assert "```answer" in result
        time.sleep(0.3)  # 给被抛弃的 reader 一点时间：若未停流它会继续拉取
        assert stream.closed is True
        assert stream.yielded <= 5, f"reader 未停止，继续拉取了 {stream.yielded} 个 chunk"

    @patch("zhs.llm.openai.logger")
    @patch("zhs.llm.openai.OpenAI")
    def test_no_drop_warning_after_early_termination(self, mock_openai_cls: MagicMock, mock_logger: MagicMock) -> None:
        """提前终止不应产生 chunk 丢弃告警"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        tail = [f"padding-{i}" for i in range(30)]
        stream = _FakeStream(["```answer\n", "ok", "\n```", *tail], gap=0.05)
        mock_client.chat.completions.create.return_value = stream

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        provider.completion("prompt")

        time.sleep(0.3)
        warnings = " ".join(str(call.args[0]) for call in mock_logger.warning.call_args_list if call.args)
        assert "chunk_queue" not in warnings

    @patch("zhs.llm.openai.OpenAI")
    def test_full_text_returned_when_marker_closes_at_end(self, mock_openai_cls: MagicMock) -> None:
        """标记在最后一个 chunk 才闭合时，返回完整拼接文本"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        parts = [f"part-{i};" for i in range(20)] + ["```answer", "done", "```"]
        mock_client.chat.completions.create.return_value = _FakeStream(parts)

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        result = provider.completion("prompt")

        assert result == "".join(parts)

    @patch("zhs.llm.openai.OpenAI")
    def test_timeout_stops_reader_and_closes_stream(self, mock_openai_cls: MagicMock) -> None:
        """流式超时也要停流并关闭"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        stream = _FakeStream(["```answer", "late"], gap=0.5)
        mock_client.chat.completions.create.return_value = stream

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4", max_retries=1, timeout=0.2)
        with pytest.raises(ZhsError, match="timeout"):
            provider.completion("prompt")

        assert stream.closed is True

    @patch("zhs.llm.openai.STREAM_IDLE_TIMEOUT", 0.3)
    @patch("zhs.llm.openai.OpenAI")
    def test_thinking_phase_without_content_is_not_a_timeout(self, mock_openai_cls: MagicMock) -> None:
        """思考阶段只发空 delta（reasoning_content）时，不应被空闲超时误杀"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        # 6 个空 delta，间隔 0.1s（累计 0.6s > 空闲阈值 0.3s），之后才给出正文
        stream = _FakeStream(["", "", "", "", "", "", "```answer\n", "ok", "\n```"], gap=0.1)
        mock_client.chat.completions.create.return_value = stream

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4", max_retries=1, timeout=5.0)
        result = provider.completion("prompt")

        assert "```answer" in result

    @patch("zhs.llm.openai.OpenAI")
    def test_close_failure_does_not_break_result(self, mock_openai_cls: MagicMock) -> None:
        """stream.close() 抛异常时仍正常返回答案"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        stream = _FakeStream(["```answer\n", "ok", "\n```"], close_error=True)
        mock_client.chat.completions.create.return_value = stream

        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
        result = provider.completion("prompt")

        assert "```answer" in result


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

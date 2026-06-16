"""Task 5.4 — llm/zhidao.py TDD"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.llm.zhidao import ZhidaoAIProvider


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.uuid = "test-uuid"
    session.crypto = MagicMock()
    session.crypto.ai_sign_prefix = "8ZflKEagfL"
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    # mock _get_client() 返回带 post 方法的 client
    mock_client = MagicMock()
    session._get_client.return_value = mock_client
    return session


class TestZhidaoAICompletion:
    """智慧树内置 AI completion"""

    @patch("zhs.llm.zhidao.sign_zhidao_ai")
    def test_non_stream_completion(self, mock_sign: MagicMock, mock_session: MagicMock) -> None:
        """非流式调用"""
        mock_sign.return_value = ("https://example.com/api?sign=abc", {"sessionNid": "chatcmpl-test"})
        mock_session._get_client.return_value.post.return_value = MagicMock(
            text='data: {"choices": [{"delta": {"content": "```answer\\n[{\\"id\\": 1}]\\n```"}}]}\n\ndata: [DONE]\n'
        )

        provider = ZhidaoAIProvider(mock_session, stream=False)
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.sign_zhidao_ai")
    def test_stream_completion(self, mock_sign: MagicMock, mock_session: MagicMock) -> None:
        """流式响应解析"""
        mock_sign.return_value = ("https://example.com/api?sign=abc", {"sessionNid": "chatcmpl-test"})

        # 模拟 stream() 上下文管理器
        stream_lines = [
            'data: {"choices": [{"delta": {"content": "```answer\\nok\\n```"}}]}',
            "data: [DONE]",
        ]
        mock_stream_response = MagicMock()
        mock_stream_response.iter_lines.return_value = stream_lines
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_response)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_session._get_client.return_value.stream.return_value = mock_stream_ctx

        provider = ZhidaoAIProvider(mock_session, stream=True)
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.sign_zhidao_ai")
    def test_sign_called_with_correct_params(self, mock_sign: MagicMock, mock_session: MagicMock) -> None:
        """签名使用正确的参数"""
        mock_sign.return_value = ("https://example.com/api?sign=abc", {"sessionNid": "chatcmpl-test"})
        mock_session._get_client.return_value.post.return_value = MagicMock(
            text='data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n'
        )

        provider = ZhidaoAIProvider(mock_session)
        provider.completion("test prompt")
        mock_sign.assert_called_once()
        call_data = mock_sign.call_args[0][0]
        assert "url" in call_data
        assert "modelCode" in call_data
        assert "messageList" in call_data

    @patch("zhs.llm.zhidao.sign_zhidao_ai")
    def test_api_error_handling(self, mock_sign: MagicMock, mock_session: MagicMock) -> None:
        """API 错误处理"""
        mock_sign.return_value = ("https://example.com/api?sign=abc", {"sessionNid": "chatcmpl-test"})
        mock_session._get_client.return_value.post.side_effect = Exception("Network error")

        provider = ZhidaoAIProvider(mock_session)
        with pytest.raises(Exception, match="Network error"):
            provider.completion("test prompt")

    @patch("zhs.llm.zhidao.sign_zhidao_ai")
    def test_sse_parsing(self, mock_sign: MagicMock, mock_session: MagicMock) -> None:
        """SSE 响应解析"""
        mock_sign.return_value = ("https://example.com/api?sign=abc", {"sessionNid": "chatcmpl-test"})
        sse_text = (
            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
            'data: {"choices": [{"delta": {"content": " World"}}]}\n\n'
            "data: [DONE]\n"
        )
        mock_session._get_client.return_value.post.return_value = MagicMock(text=sse_text)

        provider = ZhidaoAIProvider(mock_session)
        result = provider.completion("test prompt")
        assert "Hello World" in result

"""Task 5.4 — llm/zhidao.py TDD（chatHome API 版本）"""

import json
from unittest.mock import MagicMock, patch

import pytest

from zhs.llm.zhidao import ZhidaoAIProvider


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.key_bytes.side_effect = lambda name: {
        "ai_key": b"hw2fdlwcj4cs1mx7",
        "iv": b"1g3qqdh4jvbskb9x",
    }.get(name, b"")
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.ai_analysis = "https://ai-course-assistant-api.zhihuishu.com"
    mock_client = MagicMock()
    session._get_client.return_value = mock_client
    return session


def _make_stream_ctx(lines: list[str]) -> MagicMock:
    """构造 mock stream() 上下文管理器"""
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = lines
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_response)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    return mock_stream_ctx


def _mock_map_uid_response(map_uid: str = "8234567890123456789", sc_map_uid: str = "7123456789012345678") -> MagicMock:
    """构造 get-course-mapUid 响应"""
    resp = MagicMock()
    resp.json.return_value = {
        "code": 200,
        "message": "OK",
        "data": {"mapUid": map_uid, "scMapUid": sc_map_uid, "mapName": "测试课程"},
    }
    return resp


class TestZhidaoAICompletion:
    """智慧树内置 AI completion（chatHome API）"""

    def test_init_requires_course_id(self, mock_session: MagicMock) -> None:
        """初始化必须传入 course_id"""
        provider = ZhidaoAIProvider(mock_session, course_id="123", course_name="测试")
        assert provider._course_id == "123"
        assert provider._course_name == "测试"

    @patch("zhs.llm.zhidao.Cipher")
    def test_stream_completion_text_event(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """TEXT 事件解析（增量文本）"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:abc123",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:def456",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", course_name="测试课程")
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.Cipher")
    def test_stream_completion_full_text_event(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """FULL_TEXT 事件解析（多行文本）"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:abc",
            "event:FULL_TEXT",
            "data:分析中...",
            "data:",
            "data:```answer",
            'data:[{"id": 679780238, "content": "对"}]',
            "data:```",
            "id:def",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678")
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.Cipher")
    def test_stream_early_stop(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """检测到答案标记后提前终止"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"分析中..."}',
            "id:2",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:3",
            "event:TEXT",
            'data:{"text":"后续无用内容"}',
            "id:4",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678")
        result = provider.completion("test prompt")
        assert "```answer" in result
        assert "后续无用内容" not in result

    @patch("zhs.llm.zhidao.Cipher")
    def test_map_uid_cached(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """mapUid 获取后缓存，不重复请求"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678")
        provider.completion("test1")
        provider.completion("test2")

        # get-course-mapUid 的 post 只调用一次
        assert mock_client.post.call_count == 1

    @patch("zhs.llm.zhidao.Cipher")
    def test_api_error_handling(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """chatHome 请求错误处理"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()
        mock_client.stream.side_effect = Exception("Network error")

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", max_retries=1)
        with pytest.raises(Exception, match="Network error"):
            provider.completion("test prompt")

    def test_generate_conversation_id(self, mock_session: MagicMock) -> None:
        """conversationId 生成 20 字符随机字符串"""
        provider = ZhidaoAIProvider(mock_session, course_id="123")
        conv_id = provider._generate_conversation_id()
        assert len(conv_id) == 20
        conv_id2 = provider._generate_conversation_id()
        assert conv_id != conv_id2

    @patch("zhs.llm.zhidao.Cipher")
    def test_chatHome_payload_contains_required_fields(
        self, mock_cipher_cls: MagicMock, mock_session: MagicMock
    ) -> None:
        """chatHome 请求体包含必需字段"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", course_name="测试课程")
        provider.completion("test prompt")

        # 验证 chatHome 调用参数
        stream_call = mock_client.stream.call_args
        assert stream_call.kwargs["params"] == {"userId": "0"}
        payload = stream_call.kwargs["json"]
        assert payload["query"] == "test prompt"
        assert payload["course_name"] == "测试课程"
        assert payload["model"] == "bot"
        assert payload["user_id"] == 0
        assert payload["courseId"] == "7123456789012345678"
        assert payload["course_id"] == "7123456789012345678"
        assert payload["language"] == "chinese"
        assert payload["bizType"] == "HOME_PAGE"
        assert len(payload["conversationId"]) == 20
        # data_info 和 relation_id_list 是 JSON 字符串
        data_info = json.loads(payload["data_info"])
        assert "relation_id_list" in data_info
        assert data_info["top_k"] == 5
        assert data_info["threshold"] == 0.95
        relation_list = json.loads(payload["relation_id_list"])
        assert relation_list[0]["course_id"] == "7123456789012345678"
        assert relation_list[0]["map_uid"] == "8234567890123456789"

    @patch("zhs.llm.zhidao.Cipher")
    def test_no_answer_marker_raises_error(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """SSE 流结束但未找到答案标记时抛异常"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        # 流式响应中没有 ```answer 标记
        stream_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"这是分析内容"}',
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", max_retries=1)
        with pytest.raises(Exception, match="AI 未返回有效答案"):
            provider.completion("test prompt")

    @patch("zhs.llm.zhidao.Cipher")
    def test_empty_stream_raises_error(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """SSE 流响应为空时抛异常"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        # 空流
        stream_lines = ["id:1", "event:END", "data:"]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", max_retries=1)
        with pytest.raises(Exception, match="SSE 流响应为空"):
            provider.completion("test prompt")

    @patch("zhs.llm.zhidao.Cipher")
    def test_no_answer_marker_retries(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """未找到答案标记时触发重试"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        # 第一次无答案标记，第二次有答案标记
        fail_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"分析中..."}',
            "id:2",
            "event:END",
            "data:",
        ]
        success_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.side_effect = [
            _make_stream_ctx(fail_lines),
            _make_stream_ctx(success_lines),
        ]

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678", max_retries=3, retry_delay=0)
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.Cipher")
    def test_full_text_event_no_json_error(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """FULL_TEXT 事件纯文本不触发 JSON 解析错误"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        # FULL_TEXT 事件包含纯中文文本（不应触发 JSON 解析警告）
        stream_lines = [
            "id:1",
            "event:FULL_TEXT",
            "data:这是纯文本内容，不是JSON",
            "data:",
            "data:```answer",
            'data:[{"id": 1, "content": "A"}]',
            "data:```",
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678")
        result = provider.completion("test prompt")
        assert "```answer" in result

    @patch("zhs.llm.zhidao.Cipher")
    def test_no_user_info_api_call(self, mock_cipher_cls: MagicMock, mock_session: MagicMock) -> None:
        """不再调用 /api/v1/user/info"""
        mock_cipher_cls.return_value.encrypt.return_value = "encrypted-data"

        mock_client = mock_session._get_client.return_value
        mock_client.post.return_value = _mock_map_uid_response()

        stream_lines = [
            "id:1",
            "event:TEXT",
            'data:{"text":"```answer\\n[{\\"id\\": 1}]\\n```"}',
            "id:2",
            "event:END",
            "data:",
        ]
        mock_client.stream.return_value = _make_stream_ctx(stream_lines)

        provider = ZhidaoAIProvider(mock_session, course_id="7123456789012345678")
        provider.completion("test prompt")

        # 不应调用 client.get（user/info）
        mock_client.get.assert_not_called()

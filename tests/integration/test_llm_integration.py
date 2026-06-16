"""LLM 集成测试 — 智慧树 AI、OpenAI、Prompt 模板"""

import os

import pytest

from zhs.llm.prompts import build_choice_prompt, build_fill_blank_prompt, parse_choice_answer, parse_fill_blank_answer
from zhs.session import ZhsSession

pytestmark = pytest.mark.integration


class TestZhidaoAI:
    """智慧树内置 AI"""

    def test_zhidao_ai_non_stream(self, logged_in_session: ZhsSession) -> None:
        """LM-01: 智慧树 AI 非流式响应"""
        from zhs.llm.zhidao import ZhidaoAIProvider

        provider = ZhidaoAIProvider(logged_in_session, stream=False)
        result = provider.completion("1+1等于多少？请回答数字")
        # AI 可能返回空（频率限制等），仅验证不抛异常
        assert isinstance(result, str)

    def test_zhidao_ai_stream(self, logged_in_session: ZhsSession) -> None:
        """LM-02: 智慧树 AI 流式响应"""
        from zhs.llm.zhidao import ZhidaoAIProvider

        provider = ZhidaoAIProvider(logged_in_session, stream=True)
        result = provider.completion("1+1等于多少？请回答数字")
        assert isinstance(result, str)

    def test_zhidao_ai_sign_correct(self, logged_in_session: ZhsSession) -> None:
        """LM-03: 签名正确，请求成功（通过成功调用间接验证）"""
        from zhs.llm.zhidao import ZhidaoAIProvider

        provider = ZhidaoAIProvider(logged_in_session, stream=False)
        # 如果签名错误，会抛异常
        result = provider.completion("你好")
        assert isinstance(result, str)


class TestOpenAI:
    """OpenAI 兼容接口"""

    @pytest.mark.openai
    def test_openai_non_stream(self) -> None:
        """LM-05: OpenAI 非流式"""
        api_key = os.environ.get("ZHS_TEST_OPENAI_API_KEY")
        if not api_key:
            pytest.skip("未设置 ZHS_TEST_OPENAI_API_KEY")

        from zhs.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=api_key, stream=False)
        result = provider.completion("1+1等于多少？")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.openai
    def test_openai_stream(self) -> None:
        """LM-06: OpenAI 流式"""
        api_key = os.environ.get("ZHS_TEST_OPENAI_API_KEY")
        if not api_key:
            pytest.skip("未设置 ZHS_TEST_OPENAI_API_KEY")

        from zhs.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=api_key, stream=True)
        result = provider.completion("1+1等于多少？")
        assert isinstance(result, str)
        assert len(result) > 0


class TestPrompts:
    """Prompt 模板（纯函数，无需 API）"""

    def test_choice_prompt_with_reference(self) -> None:
        """LM-09: 选择题 Prompt 包含参考资料代码块包裹"""
        prompt = build_choice_prompt(
            question="以下哪个是正确的？",
            choices=[{"id": 1, "content": "A. 选项1"}, {"id": 2, "content": "B. 选项2"}],
            answer_type="单选题",
            reference_materials=[{"name": "课件1", "content": "这是参考资料"}],
        )
        assert "```课件1" in prompt
        assert "这是参考资料" in prompt
        assert "最合适的答案" in prompt

    def test_multiple_choice_prompt(self) -> None:
        """LM-10: 多选题 Prompt 包含"所有正确的答案" """
        prompt = build_choice_prompt(
            question="以下哪些是正确的？",
            choices=[{"id": 1, "content": "A. 选项1"}, {"id": 2, "content": "B. 选项2"}, {"id": 3, "content": "C. 选项3"}],
            answer_type="多选题",
        )
        assert "所有正确的答案" in prompt

    def test_fill_blank_prompt_with_context(self) -> None:
        """LM-11: 填空题 Prompt 包含 theme 和 knowledgePoint"""
        prompt = build_fill_blank_prompt(
            question="请填写答案",
            extra={"theme": "第一章", "knowledgePoint": "知识点1"},
        )
        assert "第一章" in prompt
        assert "知识点1" in prompt

    def test_parse_choice_answer(self) -> None:
        """选择题答案解析"""
        result = parse_choice_answer("```answer\n[{\"id\": 1, \"content\": \"A\"}]\n```")
        assert 1 in result

    def test_parse_fill_blank_answer(self) -> None:
        """填空题答案解析"""
        result = parse_fill_blank_answer("```answer\n这是答案\n```")
        assert "这是答案" in result

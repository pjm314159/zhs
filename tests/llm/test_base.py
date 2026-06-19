"""Task 5.2 — llm/base.py TDD"""

from zhs.llm.base import LLMProvider


class ConcreteLLMProvider(LLMProvider):
    """用于测试的具体实现"""

    def completion(self, prompt: str, aim_start: str = "```answer", aim_end: str = "```") -> str:
        return '```answer\n[{"id": 1, "content": "A"}]\n```'


class TestLLMProvider:
    """LLMProvider 抽象基类"""

    def test_cannot_instantiate_abstract(self) -> None:
        """不能直接实例化抽象类"""
        import pytest

        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        """具体子类可以实例化"""
        provider = ConcreteLLMProvider()
        assert provider is not None

    def test_completion_method(self) -> None:
        """completion 方法返回字符串"""
        provider = ConcreteLLMProvider()
        result = provider.completion("test prompt")
        assert isinstance(result, str)

    def test_parse_choice_answer_delegates(self) -> None:
        """parse_choice_answer 委托给 prompts 模块"""
        provider = ConcreteLLMProvider()
        result = provider.parse_choice_answer('```answer\n[{"id": 1, "content": "A"}]\n```')
        assert result == [1]

    def test_parse_fill_blank_answer_delegates(self) -> None:
        """parse_fill_blank_answer 委托给 prompts 模块"""
        provider = ConcreteLLMProvider()
        result = provider.parse_fill_blank_answer("```answer\n答案1\n答案2\n```")
        assert result == ["答案1/答案2"]

    def test_single_choice_convenience(self) -> None:
        """single_choice 便捷方法构建 prompt 并解析"""
        provider = ConcreteLLMProvider()
        result = provider.single_choice("什么是 Python?", [{"id": 1, "content": "编程语言"}])
        assert result == [1]

    def test_multiple_choice_convenience(self) -> None:
        """multiple_choice 便捷方法"""
        provider = ConcreteLLMProvider()
        result = provider.multiple_choice(
            "哪些是编程语言?",
            [{"id": 1, "content": "Python"}, {"id": 2, "content": "Java"}],
        )
        assert result == [1]

    def test_judgement_convenience(self) -> None:
        """judgement 便捷方法"""
        provider = ConcreteLLMProvider()
        result = provider.judgement("Python 是编程语言?", [{"id": 1, "content": "对"}, {"id": 2, "content": "错"}])
        assert result == [1]

    def test_fill_blank_convenience(self) -> None:
        """fill_blank 便捷方法"""

        # ConcreteLLMProvider.completion 返回选择题格式，需要用返回填空格式的 provider
        class FillBlankProvider(LLMProvider):
            def completion(self, prompt: str, aim_start: str = "```answer", aim_end: str = "```") -> str:
                return "```answer\n编程\n```"

        fb_provider = FillBlankProvider()
        result = fb_provider.fill_blank("Python 是___语言")
        assert result == ["编程"]

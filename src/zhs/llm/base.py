"""LLM 提供者抽象基类"""

from abc import ABC, abstractmethod

from zhs.llm.prompts import (
    build_choice_prompt,
    build_fill_blank_prompt,
    parse_choice_answer,
    parse_fill_blank_answer,
)


class LLMProvider(ABC):
    """LLM 提供者抽象基类

    子类必须实现 completion 方法。
    便捷方法（single_choice, multiple_choice 等）自动构建 Prompt 并解析答案。
    """

    @abstractmethod
    def completion(
        self,
        prompt: str,
        aim_start: str = "```answer",
        aim_end: str = "```",
    ) -> str:
        """调用 LLM 获取补全结果"""
        ...

    def single_choice(
        self,
        question: str,
        choices: list[dict[str, object]],
        reference_materials: list[dict[str, str]] | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[int]:
        """单选题：构建 Prompt → 调用 LLM → 解析答案"""
        prompt = build_choice_prompt(question, choices, "单选题", reference_materials, extra)
        result = self.completion(prompt)
        return parse_choice_answer(result)

    def multiple_choice(
        self,
        question: str,
        choices: list[dict[str, object]],
        reference_materials: list[dict[str, str]] | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[int]:
        """多选题：构建 Prompt → 调用 LLM → 解析答案"""
        prompt = build_choice_prompt(question, choices, "多选题", reference_materials, extra)
        result = self.completion(prompt)
        return parse_choice_answer(result)

    def judgement(
        self,
        question: str,
        choices: list[dict[str, object]],
        reference_materials: list[dict[str, str]] | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[int]:
        """判断题：构建 Prompt → 调用 LLM → 解析答案"""
        prompt = build_choice_prompt(question, choices, "判断题", reference_materials, extra)
        result = self.completion(prompt)
        return parse_choice_answer(result)

    def fill_blank(
        self,
        question: str,
        reference_materials: list[dict[str, str]] | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[str]:
        """填空题：构建 Prompt → 调用 LLM → 解析答案"""
        prompt = build_fill_blank_prompt(question, reference_materials, extra)
        result = self.completion(prompt)
        return parse_fill_blank_answer(result)

    def parse_choice_answer(self, completion: str) -> list[int]:
        """从 LLM 输出提取选项 ID 列表"""
        return parse_choice_answer(completion)

    def parse_fill_blank_answer(self, completion: str) -> list[str]:
        """从 LLM 输出提取填空答案"""
        return parse_fill_blank_answer(completion)

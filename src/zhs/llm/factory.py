"""LLM 提供者工厂

统一 LLMProvider 的初始化逻辑，消除 HomeworkCtx/ExamCtx 中的重复代码。
"""

from zhs.config import AIConfig
from zhs.llm.base import LLMProvider
from zhs.llm.openai import OpenAIProvider
from zhs.llm.zhidao import ZhidaoAIProvider
from zhs.session import ZhsSession


class LLMProviderFactory:
    """LLM 提供者工厂

    根据 AIConfig 创建对应的 LLMProvider 实例（仅 AI 智慧课程使用）：
    - AI 禁用 → None
    - use_builtin_ai=True → ZhidaoAIProvider（智慧树内置 AI，需 session/course 上下文）
    - 有 api_key → OpenAIProvider
    - 其他 → None

    知到作业/知到考试不走此工厂（由 cli.bootstrap.init_llm 创建）：它们没有内置 AI，
    只能用自定义 api_key（`use_builtin_ai` 仅作用于 AI 智慧课程）。
    """

    @staticmethod
    def create(
        ai_config: AIConfig,
        session: ZhsSession | None = None,
        course_id: str = "",
        course_name: str = "",
    ) -> LLMProvider | None:
        """创建 LLM 提供者

        Args:
            ai_config: AI 配置
            session: ZhsSession（ZhidaoAIProvider 需要）
            course_id: 课程 ID（ZhidaoAIProvider 需要）
            course_name: 课程名（ZhidaoAIProvider 需要）

        Returns:
            LLMProvider 实例或 None
        """
        if not ai_config.enabled:
            return None
        if ai_config.use_builtin_ai:
            if session is None:
                return None
            return ZhidaoAIProvider(
                session=session,
                course_id=course_id,
                course_name=course_name,
            )
        if ai_config.api_key:
            return OpenAIProvider(
                api_key=ai_config.api_key,
                base_url=ai_config.base_url,
                model_name=ai_config.model,
            )
        return None

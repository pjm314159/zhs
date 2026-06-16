"""OpenAI 兼容接口 LLM 提供者"""

import re
import time
from typing import Any

from loguru import logger
from openai import OpenAI

from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容接口

    支持任何 OpenAI 兼容的 API（包括 MoonShot、DeepSeek 等）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model_name: str = "gpt-4",
        stream: bool = False,
        extra: dict[str, Any] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_token: int = 27900,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model_name = model_name
        self._stream = stream
        self._extra = extra or {}
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_token = max_token

    def completion(
        self,
        prompt: str,
        aim_start: str = "```answer",
        aim_end: str = "```",
    ) -> str:
        """调用 OpenAI 兼容接口获取补全结果（含重试和流式提前终止）"""
        # Token 截断
        prompt = self._truncate_prompt(prompt)

        for attempt in range(self._max_retries):
            try:
                if self._stream:
                    return self._stream_completion(prompt, aim_start, aim_end)

                response = self._client.chat.completions.create(
                    model=self._model_name,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    **self._extra,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ZhsError("OpenAI API returned empty content")
                return str(content)
            except ZhsError:
                raise
            except Exception as e:
                logger.error(f"OpenAI attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    raise ZhsError(f"OpenAI API error after {self._max_retries} retries: {e}") from e
        raise ZhsError("Unexpected error in OpenAI completion")

    def _stream_completion(self, prompt: str, aim_start: str = "```answer", aim_end: str = "```") -> str:
        """流式响应解析（含提前终止）"""
        stream = self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            **self._extra,
        )
        collected: list[str] = []
        cache: str = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content is not None:
                collected.append(delta.content)
                cache += delta.content
                # 检测到答案标记后提前终止
                match = re.search(f"{re.escape(aim_start)}(.*?){re.escape(aim_end)}", cache, re.DOTALL)
                if match:
                    return cache
        return "".join(collected)

    def _truncate_prompt(self, prompt: str) -> str:
        """截断过长的 prompt（简单字符估算，约 4 字符/token）"""
        max_chars = self._max_token * 4
        if len(prompt) > max_chars:
            prompt = prompt[-max_chars:]
            logger.warning(f"Prompt 过长，已截断至约 {self._max_token} tokens")
        return prompt

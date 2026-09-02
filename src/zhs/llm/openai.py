"""OpenAI 兼容接口 LLM 提供者"""

import contextlib
import re
import time
from queue import Empty, Full, Queue
from threading import Thread
from typing import Any

from loguru import logger
from openai import OpenAI

from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容接口

    支持任何 OpenAI 兼容的 API（包括 MoonShot、DeepSeek 等）。
    默认启用流式响应，检测到答案标记后提前终止。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model_name: str = "gpt-4",
        extra: dict[str, Any] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_token: int = 27900,
        timeout: float = 120.0,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._model_name = model_name
        self._extra = extra or {}
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_token = max_token
        self._timeout = timeout

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
                return self._stream_completion(prompt, aim_start, aim_end)
            except Exception as e:
                logger.error(f"OpenAI attempt {attempt + 1}/{self._max_retries} failed: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    raise ZhsError(f"OpenAI API error after {self._max_retries} retries: {e}") from e
        raise ZhsError("Unexpected error in OpenAI completion")

    def _stream_completion(self, prompt: str, aim_start: str = "```answer", aim_end: str = "```") -> str:
        """流式响应解析（含提前终止和真正的超时保护）

        使用后台线程读取 stream chunks，主线程通过 Queue.get(timeout) 实现真正的超时。
        即使 OpenAI SDK 的 __next__() 阻塞，主线程也能在 timeout 后超时退出。
        """
        stream = self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            timeout=self._timeout,
            **self._extra,
        )

        # 后台线程读取 chunks，通过 Queue 传递给主线程
        # Queue item: str = content delta, None = 流结束, Exception = 错误
        chunk_queue: Queue[str | None | Exception] = Queue(maxsize=100)

        def _reader() -> None:
            try:
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    content = delta.content if delta.content else ""
                    try:
                        chunk_queue.put(content, timeout=5.0)
                    except Full:
                        logger.warning("chunk_queue 满，丢弃 chunk")
                chunk_queue.put(None, timeout=5.0)  # 流结束信号
            except Exception as e:
                with contextlib.suppress(Full):
                    chunk_queue.put(e, timeout=5.0)

        reader_thread = Thread(target=_reader, daemon=True)
        reader_thread.start()
        logger.debug("OpenAI stream reader 线程已启动")

        collected: list[str] = []
        cache: str = ""
        start_time = time.monotonic()

        while True:
            remaining = self._timeout - (time.monotonic() - start_time)
            if remaining <= 0:
                logger.error(f"OpenAI 流式响应超时（>{self._timeout}s），已收集 {len(collected)} 个 chunk")
                raise ZhsError(f"OpenAI stream timeout after {self._timeout}s")

            try:
                item = chunk_queue.get(timeout=min(remaining, 30.0))
            except Empty:
                # 超时未收到 chunk
                elapsed = time.monotonic() - start_time
                logger.error(f"OpenAI 流式响应超时（{elapsed:.1f}s 无数据），已收集 {len(collected)} 个 chunk")
                raise ZhsError(f"OpenAI stream timeout after {elapsed:.1f}s") from None

            if item is None:
                # 流结束
                break
            if isinstance(item, Exception):
                raise ZhsError(f"OpenAI stream error: {item}") from item

            content = item
            if content:
                collected.append(content)
                cache += content
                # 检测到答案标记后提前终止
                match = re.search(f"{re.escape(aim_start)}(.*?){re.escape(aim_end)}", cache, re.DOTALL)
                if match:
                    logger.info("检测到答案标记，提前终止 OpenAI 流")
                    return cache

        # 流结束但未找到答案标记
        result = "".join(collected)
        if not result:
            logger.error("OpenAI 流响应为空，未找到答案标记")
            raise ZhsError("OpenAI 流响应为空，未找到答案标记")
        logger.error(f"OpenAI 流结束但未找到答案标记, 响应长度={len(result)}, 内容前200字: {result[:200]}")
        raise ZhsError(f"OpenAI 未返回有效答案（响应长度={len(result)}）")

    def _truncate_prompt(self, prompt: str) -> str:
        """截断过长的 prompt（简单字符估算，约 4 字符/token）"""
        max_chars = self._max_token * 4
        if len(prompt) > max_chars:
            prompt = prompt[-max_chars:]
            logger.warning(f"Prompt 过长，已截断至约 {self._max_token} tokens")
        return prompt

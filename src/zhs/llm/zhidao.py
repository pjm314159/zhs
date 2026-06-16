"""智慧树内置 AI（moonshot-v1-32k）LLM 提供者"""

import json
import re
import time
from typing import Any

from loguru import logger

from zhs.crypto import sign_zhidao_ai
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.session import ZhsSession


class ZhidaoAIProvider(LLMProvider):
    """智慧树内置 AI

    使用智慧树内置的 AI 对话接口（基于 moonshot-v1-32k），
    通过 sign_zhidao_ai 签名后发送请求。
    """

    def __init__(
        self,
        session: ZhsSession,
        stream: bool = False,
        extra: dict[str, Any] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._session = session
        self._stream = stream
        self._extra = extra or {}
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def completion(
        self,
        prompt: str,
        aim_start: str = "```answer",
        aim_end: str = "```",
    ) -> str:
        """调用智慧树内置 AI 获取补全结果（含重试和流式提前终止）"""
        for attempt in range(self._max_retries):
            try:
                return self._do_completion(prompt, aim_start, aim_end)
            except Exception as e:
                logger.error(f"Zhidao AI attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    raise ZhsError(f"Zhidao AI error after {self._max_retries} retries: {e}") from e
        raise ZhsError("Unexpected error in ZhidaoAI completion")

    def _do_completion(self, prompt: str, aim_start: str, aim_end: str) -> str:
        """单次调用智慧树内置 AI"""
        url = self._session.urls.ai_chat
        data: dict[str, Any] = {
            "url": url,
            "modelCode": "moonshot-v1-32k",
            "stream": self._stream,
            "messageList": [{"role": "user", "content": prompt}],
        }
        data.update(self._extra)

        # 签名
        signed_url, signed_data = sign_zhidao_ai(data, self._session.crypto.ai_sign_prefix)

        # 发送请求
        if self._stream:
            with self._session._get_client().stream(
                "POST", signed_url, json=signed_data, headers={"Content-Type": "application/json"}, timeout=60.0
            ) as response:
                return self._parse_stream_with_early_stop(response.iter_lines(), aim_start, aim_end)
        else:
            response = self._session._get_client().post(
                signed_url, json=signed_data, headers={"Content-Type": "application/json"}
            )
            return self._parse_sse(response.text)

    def _parse_stream_with_early_stop(self, lines: Any, aim_start: str, aim_end: str) -> str:
        """解析流式响应，检测到答案标记后提前终止"""
        collected: list[str] = []
        cache: str = ""
        for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        collected.append(content)
                        cache += content
                        # 检测到答案标记后提前终止
                        match = re.search(f"{re.escape(aim_start)}(.*?){re.escape(aim_end)}", cache, re.DOTALL)
                        if match:
                            return cache
            except json.JSONDecodeError:
                continue
        return "".join(collected)

    def _parse_sse(self, text: str) -> str:
        """解析 SSE 响应文本"""
        collected: list[str] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        collected.append(content)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse SSE line: {data_str}")
        return "".join(collected)

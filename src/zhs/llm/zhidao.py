"""智慧树内置 AI（chatHome API）LLM 提供者

使用 ai-course-assistant-api 域名的 chatHome 接口进行作业答题。
流程：
1. 调用 get-course-mapUid 获取 mapUid/scMapUid（加密接口，每个课程仅一次）
2. 调用 chatHome 进行 SSE 流式对话，检测到答案标记后提前终止
"""

import json
import re
import secrets
import string
import time
from typing import Any

from loguru import logger

from zhs.crypto import Cipher
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.session import ZhsSession


class ZhidaoAIProvider(LLMProvider):
    """智慧树内置 AI（chatHome API）

    使用 ai-course-assistant-api 域名的 chatHome 接口，
    SSE 流式响应，检测到答案标记后提前终止。
    """

    def __init__(
        self,
        session: ZhsSession,
        course_id: str,
        course_name: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._session = session
        self._course_id = str(course_id)
        self._course_name = course_name
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        # 缓存 mapUid（每个课程仅请求一次）
        self._map_uid: str | None = None
        self._sc_map_uid: str | None = None
        logger.debug(f"ZhidaoAIProvider 初始化: course_id={self._course_id}, course_name={self._course_name}")

    def completion(
        self,
        prompt: str,
        aim_start: str = "```answer",
        aim_end: str = "```",
    ) -> str:
        """调用智慧树内置 AI 获取补全结果（含重试和流式提前终止）"""
        logger.debug(f"开始调用智慧树 AI, prompt 长度={len(prompt)}")
        for attempt in range(self._max_retries):
            try:
                result = self._do_completion(prompt, aim_start, aim_end)
                logger.debug(f"智慧树 AI 调用成功, 响应长度={len(result)}")
                return result
            except Exception as e:
                logger.error(f"智慧树 AI 第 {attempt + 1}/{self._max_retries} 次调用失败: {e}")
                if attempt < self._max_retries - 1:
                    logger.debug(f"等待 {self._retry_delay}s 后重试...")
                    time.sleep(self._retry_delay)
                else:
                    raise ZhsError(f"智慧树 AI 调用失败（已重试 {self._max_retries} 次）: {e}") from e
        raise ZhsError("Unexpected error in ZhidaoAI completion")

    # --- 上下文获取 ---

    def _get_course_map_uid(self) -> tuple[str, str]:
        """获取课程 mapUid 和 scMapUid（加密接口，每个课程仅请求一次）

        返回 (mapUid, scMapUid)
        """
        if self._map_uid is not None and self._sc_map_uid is not None:
            logger.debug(f"使用缓存的 mapUid={self._map_uid}, scMapUid={self._sc_map_uid}")
            return self._map_uid, self._sc_map_uid

        logger.debug(f"获取课程 mapUid: course_id={self._course_id}")
        url = f"{self._session.urls.ai}/run/gateway/t/common/course/get-course-mapUid"
        timestamp = int(time.time()) * 1000
        plain_data = {
            "courseId": self._course_id,
            "dateFormate": timestamp,
        }

        # AES-128-CBC 加密（ai_key）
        key = self._session.crypto.key_bytes("ai_key")
        iv = self._session.crypto.key_bytes("iv")
        cipher = Cipher(key, iv)
        encrypted = cipher.encrypt(json.dumps(plain_data))
        logger.debug(f"get-course-mapUid 请求加密完成, timestamp={timestamp}")

        payload = {
            "secretStr": encrypted,
            "date": timestamp,
        }

        try:
            client = self._session._get_client()
            resp = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            result = resp.json()
            code = result.get("code")
            if code != 200:
                logger.error(f"get-course-mapUid 返回错误: code={code}, message={result.get('message')}")
                raise ZhsError(f"get-course-mapUid 失败: code={code}, msg={result.get('message')}")

            data = result.get("data", {})
            map_uid = str(data.get("mapUid", ""))
            sc_map_uid = str(data.get("scMapUid", self._course_id))
            map_name = data.get("mapName", "")

            if not map_uid:
                logger.warning(f"get-course-mapUid 返回 mapUid 为空, course_id={self._course_id}")
                map_uid = ""

            self._map_uid = map_uid
            self._sc_map_uid = sc_map_uid
            logger.debug(f"获取 mapUid 成功: mapUid={map_uid}, scMapUid={sc_map_uid}, mapName={map_name}")
            return map_uid, sc_map_uid
        except ZhsError:
            raise
        except Exception as e:
            logger.error(f"get-course-mapUid 请求异常: {e}")
            return "", self._course_id

    def _generate_conversation_id(self) -> str:
        """生成 20 字符随机 conversationId"""
        alphabet = string.ascii_letters + string.digits
        conv_id = "".join(secrets.choice(alphabet) for _ in range(20))
        logger.debug(f"生成 conversationId={conv_id}")
        return conv_id

    # --- chatHome 调用 ---

    def _do_completion(self, prompt: str, aim_start: str, aim_end: str) -> str:
        """单次调用 chatHome（流式响应，含提前终止）"""
        map_uid, sc_map_uid = self._get_course_map_uid()

        # 构造 relation_id_list 和 data_info
        relation_item = {
            "course_id": self._course_id,
            "map_uid": map_uid,
            "sc_map_uid": sc_map_uid,
        }
        relation_id_list = [relation_item]
        data_info = {
            "history_recores": "",
            "relation_id_list": relation_id_list,
            "top_k": 5,
            "threshold": 0.95,
        }

        # 构造请求体
        url = f"{self._session.urls.ai_analysis}/api/v4/ai-assistant/chatHome"
        conversation_id = self._generate_conversation_id()
        payload: dict[str, Any] = {
            "query": prompt,
            "course_name": self._course_name,
            "node_name": "",
            "avatarRequest": {
                "courseId": self._course_id,
                "recruitId": "",
                "chapterId": "",
                "videoId": "",
            },
            "recruitId": None,
            "video_url": "",
            "node_ids": "[]",
            "video_segment": "[]",
            "video_summary": "",
            "data_info": json.dumps(data_info, ensure_ascii=False),
            "model": "bot",
            "intention": "",
            "user_id": 0,
            "courseId": self._course_id,
            "course_id": self._course_id,
            "conversationId": conversation_id,
            "isBaseCourse": True,
            "imgUrls": [],
            "files": [],
            "kg_node_name": "",
            "language": "chinese",
            "bizType": "HOME_PAGE",
            "scene": "校内课",
            "is_share_course": "0",
            "messageId": None,
            "relation_id_list": json.dumps(relation_id_list, ensure_ascii=False),
        }

        logger.debug(f"chatHome 请求: url={url}, conversationId={conversation_id}, mapUid={map_uid}")

        # 流式请求
        client = self._session._get_client()
        with client.stream(
            "POST",
            url,
            params={"userId": "0"},
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60.0,
        ) as response:
            return self._parse_stream_with_early_stop(response.iter_lines(), aim_start, aim_end)

    def _parse_stream_with_early_stop(self, lines: Any, aim_start: str, aim_end: str) -> str:
        """解析 SSE 流式响应，检测到答案标记后提前终止

        事件类型：
        - TEXT: data:{"text":"..."} 增量文本
        - FULL_TEXT: data:... 多行完整文本
        - END: 流结束

        如果流结束但未检测到答案标记，抛出 ZhsError 触发重试。
        """
        collected: list[str] = []
        cache: str = ""
        event_count = 0
        current_event: str | None = None

        for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            line = line.strip()
            if not line:
                continue

            # 处理 event 行
            if line.startswith("event:"):
                current_event = line[6:].strip()
                event_count += 1
                if current_event == "END":
                    logger.debug(f"SSE 流结束, 共处理 {event_count} 个事件")
                    break
                continue

            # 处理 id 行
            if line.startswith("id:"):
                continue

            # 处理 data 行
            if not line.startswith("data:"):
                continue

            data_str = line[5:]  # 保留前导空格（FULL_TEXT 多行场景）

            # TEXT 事件：JSON 格式 {"text": "..."}
            if current_event == "TEXT":
                try:
                    data = json.loads(data_str)
                    if isinstance(data, dict) and "text" in data:
                        content = str(data["text"])
                        if content:
                            collected.append(content)
                            cache += content
                except json.JSONDecodeError:
                    logger.warning(f"TEXT 事件 JSON 解析失败: {data_str[:100]}")
                # 检测答案标记
                match = re.search(f"{re.escape(aim_start)}(.*?){re.escape(aim_end)}", cache, re.DOTALL)
                if match:
                    logger.info(f"检测到答案标记，提前终止 SSE 流（已处理 {event_count} 个事件）")
                    return cache
                continue

            # FULL_TEXT 事件：纯文本（可能多行）
            if data_str:
                collected.append(data_str)
                cache += data_str
                # 检测答案标记
                match = re.search(f"{re.escape(aim_start)}(.*?){re.escape(aim_end)}", cache, re.DOTALL)
                if match:
                    logger.info(f"检测到答案标记，提前终止 SSE 流（已处理 {event_count} 个事件）")
                    return cache

        # 流结束但未找到答案标记
        result = "".join(collected)
        if not result:
            logger.error("SSE 流响应为空，未找到答案标记")
            raise ZhsError("SSE 流响应为空，未找到答案标记")
        logger.error(f"SSE 流结束但未找到答案标记, 响应长度={len(result)}")
        raise ZhsError(f"AI 未返回有效答案（响应长度={len(result)}）")

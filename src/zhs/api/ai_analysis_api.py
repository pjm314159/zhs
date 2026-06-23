"""AI 解析 SSE 流式 API

从原 ZhsSession.ai_analysis_run 迁移。
使用 ai-course-assistant-api 域名，明文 JSON POST，SSE 流式响应。
与作业 API 不同：不加密、不同域名、流式响应。
"""

import json
from typing import Any

from loguru import logger

from zhs.api.http_client import HttpClient


class AiAnalysisApi:
    """AI 解析 API（SSE 流式）

    流程：
    1. GET /api/v1/user/info 获取 userId
    2. POST /api/v1/question/analysis/thread/run（SSE 流式）获取解析内容
    """

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client
        self._base = http_client.urls.ai_analysis

    def run(
        self,
        course_id: int,
        recruit_id: str,
        question_id: int,
        thread_id: str = "",
        run_id: str | None = None,
        regenerate: bool = False,
        timeout: float = 60.0,
    ) -> str:
        """调用 AI 解析 run API（SSE 流式），返回完整解析内容

        Args:
            course_id: 课程 ID
            recruit_id: 招募 ID
            question_id: 题目数字型 ID（来自 lookHomework 的 id 字段）
            thread_id: 会话线程 ID（首次为空字符串）
            run_id: 运行 ID（首次为 None）
            regenerate: 是否重新生成
            timeout: 请求超时时间（秒）

        Returns:
            AI 解析完整文本内容（失败时返回空字符串）
        """
        # 先获取 userId
        user_id = self._get_user_id(course_id, recruit_id)
        if not user_id:
            logger.warning("无法获取 AI 解析 userId，跳过 AI 解析")
            return ""

        run_url = f"{self._base}/api/v1/question/analysis/thread/run"
        run_data = {
            "courseId": str(course_id),
            "recruitId": recruit_id,
            "userRole": "STUDENT",
            "userId": user_id,
            "threadId": thread_id,
            "questionId": question_id,
            "regenerate": regenerate,
            "runId": run_id,
        }

        return self._stream_run(run_url, run_data, timeout)

    def _get_user_id(self, course_id: int, recruit_id: str) -> int:
        """获取 userId"""
        try:
            info_url = f"{self._base}/api/v1/user/info"
            resp = self._http.get(
                info_url,
                params={
                    "userId": "0",
                    "courseId": str(course_id),
                    "recruitId": recruit_id,
                },
            )
            data = resp.json()
            return int(data.get("data", {}).get("userId", 0))
        except Exception as e:
            logger.warning(f"获取 AI 解析 userId 失败: {e}")
            return 0

    def _stream_run(
        self,
        url: str,
        data: dict[str, Any],
        timeout: float,
    ) -> str:
        """流式调用 run API，拼接 content"""
        full_content: list[str] = []

        try:
            with self._http.stream("POST", url, json=data, timeout=timeout) as resp:
                if resp.status_code != 200:
                    logger.warning(f"AI 解析 API 返回状态码 {resp.status_code}")
                    return ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            data_obj = json.loads(data_str)
                            content = data_obj.get("choices", [{}])[0].get("message", {}).get("content", "")
                            is_stop = data_obj.get("stop", False)
                            if content:
                                full_content.append(content)
                            if is_stop:
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"AI 解析请求失败: {e}")
            return ""

        return "".join(full_content)

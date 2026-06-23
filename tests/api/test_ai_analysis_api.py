"""api/ai_analysis_api.py AiAnalysisApi 测试

验证 AI 解析 SSE 流式 API：
- 先获取 userId（GET /api/v1/user/info）
- 再调用 run（POST /api/v1/question/analysis/thread/run，SSE 流式）
- 解析 SSE 数据行，拼接 content
"""

import httpx
import pytest
import respx

from zhs.api.ai_analysis_api import AiAnalysisApi
from zhs.api.http_client import HttpClient
from zhs.config import AppConfig


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def http_client(config: AppConfig) -> HttpClient:
    """测试用 HttpClient"""
    return HttpClient(config)


@pytest.fixture
def api(http_client: HttpClient) -> AiAnalysisApi:
    """测试用 AiAnalysisApi"""
    return AiAnalysisApi(http_client)


class TestAiAnalysisRun:
    """AI 解析 run"""

    def test_returns_empty_when_user_info_fails(self, api: AiAnalysisApi) -> None:
        """获取 userId 失败时返回空字符串"""
        with respx.mock:
            respx.get("https://ai-course-assistant-api.zhihuishu.com/api/v1/user/info").mock(
                return_value=httpx.Response(500)
            )
            result = api.run(course_id=100, recruit_id="r1", question_id=1)
            assert result == ""

    def test_returns_empty_when_user_id_zero(self, api: AiAnalysisApi) -> None:
        """userId 为 0 时返回空字符串"""
        with respx.mock:
            respx.get("https://ai-course-assistant-api.zhihuishu.com/api/v1/user/info").mock(
                return_value=httpx.Response(200, json={"data": {"userId": 0}})
            )
            result = api.run(course_id=100, recruit_id="r1", question_id=1)
            assert result == ""

    def test_returns_content_on_success(self, api: AiAnalysisApi) -> None:
        """成功时返回拼接的 content"""
        sse_lines = [
            'data: {"choices":[{"message":{"content":"hello"}}],"stop":false}',
            'data: {"choices":[{"message":{"content":" world"}}],"stop":true}',
        ]
        sse_text = "\n".join(sse_lines) + "\n"

        with respx.mock:
            respx.get("https://ai-course-assistant-api.zhihuishu.com/api/v1/user/info").mock(
                return_value=httpx.Response(200, json={"data": {"userId": 12345}})
            )
            respx.post("https://ai-course-assistant-api.zhihuishu.com/api/v1/question/analysis/thread/run").mock(
                return_value=httpx.Response(200, text=sse_text)
            )
            result = api.run(course_id=100, recruit_id="r1", question_id=1)
            assert result == "hello world"

    def test_returns_empty_on_non_200(self, api: AiAnalysisApi) -> None:
        """run API 返回非 200 时返回空字符串"""
        with respx.mock:
            respx.get("https://ai-course-assistant-api.zhihuishu.com/api/v1/user/info").mock(
                return_value=httpx.Response(200, json={"data": {"userId": 12345}})
            )
            respx.post("https://ai-course-assistant-api.zhihuishu.com/api/v1/question/analysis/thread/run").mock(
                return_value=httpx.Response(500)
            )
            result = api.run(course_id=100, recruit_id="r1", question_id=1)
            assert result == ""

    def test_stops_on_stop_flag(self, api: AiAnalysisApi) -> None:
        """stop=true 时停止读取"""
        sse_lines = [
            'data: {"choices":[{"message":{"content":"first"}}],"stop":false}',
            'data: {"choices":[{"message":{"content":"stop"}}],"stop":true}',
            'data: {"choices":[{"message":{"content":"after"}}],"stop":false}',
        ]
        sse_text = "\n".join(sse_lines) + "\n"

        with respx.mock:
            respx.get("https://ai-course-assistant-api.zhihuishu.com/api/v1/user/info").mock(
                return_value=httpx.Response(200, json={"data": {"userId": 12345}})
            )
            respx.post("https://ai-course-assistant-api.zhihuishu.com/api/v1/question/analysis/thread/run").mock(
                return_value=httpx.Response(200, text=sse_text)
            )
            result = api.run(course_id=100, recruit_id="r1", question_id=1)
            assert result == "firststop"
            assert "after" not in result

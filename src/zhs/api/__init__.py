"""api/ 子包：HTTP 客户端与 API 端点封装

将原 ZhsSession 的职责拆分：
- HttpClient：HTTP 客户端生命周期（httpx.Client、代理、重试、headers）
- EncryptedQuery：6 套加密查询方法的策略表实现
- ZhidaoHomeworkApi：知到作业业务 API（6 个方法）
- AiAnalysisApi：AI 解析 SSE 流式
- SsoAuthenticator：CAS SSO 认证
"""

from zhs.api.ai_analysis_api import AiAnalysisApi
from zhs.api.encrypted_query import STRATEGIES, EncryptedQuery, QueryStrategy
from zhs.api.http_client import HttpClient
from zhs.api.sso import SsoAuthenticator
from zhs.api.zhidao_homework_api import ZhidaoHomeworkApi

__all__ = [
    "AiAnalysisApi",
    "EncryptedQuery",
    "HttpClient",
    "QueryStrategy",
    "STRATEGIES",
    "SsoAuthenticator",
    "ZhidaoHomeworkApi",
]

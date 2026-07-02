"""题库 QuestionBankClient 测试 — respx mock HTTP"""

from unittest.mock import patch

import httpx
import pytest
import respx

from zhs.question_bank.client import QuestionBankClient
from zhs.question_bank.models import QuestionBankResult

QUERY_URL = "https://tk.enncy.cn/query"
INFO_URL = "https://tk.enncy.cn/info"
TOKEN = "test-token-abc"


@pytest.fixture
def client() -> QuestionBankClient:
    return QuestionBankClient(token=TOKEN, query_url=QUERY_URL, info_url=INFO_URL, max_retries=2, retry_delay=0)


# ---------------------------------------------------------------------------
# query — 成功 / 无答案 / 参数
# ---------------------------------------------------------------------------


class TestQuerySuccess:
    def test_query_success_returns_result(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"times": 96, "user_times": 100, "success_times": 80}}
                )
            )
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "code": 1,
                        "data": {
                            "question": "q",
                            "answer": "连续性#\n创新性#",
                            "times": 95,
                            "ai": False,
                        },
                        "message": "请求成功",
                    },
                )
            )
            result = client.query("题目内容", options="A\nB", qtype="multiple")
        assert result is not None
        assert isinstance(result, QuestionBankResult)
        assert result.times == 95
        assert result.ai is False
        # 次数从响应同步
        assert client.remaining_times == 95

    def test_query_no_answer_returns_none(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 96}}))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"code": 0, "data": {"question": "q", "answer": "无答案"}, "message": "请求失败"},
                )
            )
            result = client.query("题目")
        assert result is None
        # 无答案不减次数（保持 info 的 96）
        assert client.remaining_times == 96

    def test_query_sends_correct_params(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            route = respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 9, "ai": False}}
                )
            )
            client.query("我的题目", options="选项1\n选项2", qtype="single")
        req = route.calls[0].request
        assert req.url.params["token"] == TOKEN
        assert req.url.params["title"] == "我的题目"
        assert req.url.params["type"] == "single"
        assert req.url.params["options"] == "选项1\n选项2"

    def test_query_omits_options_when_empty(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            route = respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 9, "ai": False}}
                )
            )
            client.query("题目")
        req = route.calls[0].request
        assert "options" not in req.url.params


# ---------------------------------------------------------------------------
# times / lazy info
# ---------------------------------------------------------------------------


class TestTimesManagement:
    def test_lazy_info_on_first_query(self, client: QuestionBankClient) -> None:
        assert client.remaining_times is None
        with respx.mock:
            info_route = respx.get(INFO_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"times": 50, "user_times": 60, "success_times": 40}}
                )
            )
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 49, "ai": False}}
                )
            )
            client.query("题目")
        assert info_route.called
        assert client.remaining_times == 49

    def test_info_not_refetched_on_second_query(self, client: QuestionBankClient) -> None:
        with respx.mock:
            info_route = respx.get(INFO_URL).mock(
                return_value=httpx.Response(200, json={"code": 1, "data": {"times": 50}})
            )
            query_route = respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 49, "ai": False}}
                )
            )
            client.query("题目1")
            client.query("题目2")
        # info 只被调用一次
        assert len(info_route.calls) == 1
        assert len(query_route.calls) == 2

    def test_times_zero_skips_query(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 0}}))
            query_route = respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 0, "ai": False}}
                )
            )
            result = client.query("题目")
        assert result is None
        assert not query_route.called
        assert client.remaining_times == 0

    def test_info_failure_keeps_times_none_queries_anyway(self, client: QuestionBankClient) -> None:
        # /info 失败时 _remaining_times 保持 None（≠0），仍乐观查询
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(500))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 5, "ai": False}}
                )
            )
            result = client.query("题目")
        assert result is not None
        assert client.remaining_times == 5


# ---------------------------------------------------------------------------
# get_info
# ---------------------------------------------------------------------------


class TestGetInfo:
    def test_get_info_success(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"times": 96, "user_times": 100, "success_times": 80}}
                )
            )
            info = client.get_info()
        assert info is not None
        assert info.times == 96
        assert info.user_times == 100
        assert info.success_times == 80
        assert client.remaining_times == 96

    def test_get_info_failure_returns_none(self, client: QuestionBankClient) -> None:
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 0, "data": {}, "message": "失败"}))
            info = client.get_info()
        assert info is None


# ---------------------------------------------------------------------------
# 错误处理 / 重试
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_network_error_retries_then_none(self, client: QuestionBankClient) -> None:
        # 预设 times 跳过懒加载 info，直接测 query 错误路径
        client._remaining_times = 10
        with respx.mock:
            respx.get(QUERY_URL).mock(side_effect=httpx.ConnectError("conn refused"))
            result = client.query("题目")
        assert result is None
        # 次数保持不变（查询失败不减）
        assert client.remaining_times == 10

    def test_malformed_json_returns_none(self, client: QuestionBankClient) -> None:
        client._remaining_times = 10
        with respx.mock:
            respx.get(QUERY_URL).mock(return_value=httpx.Response(200, text="not json"))
            result = client.query("题目")
        assert result is None
        assert client.remaining_times == 10

    def test_5xx_retries_then_none(self, client: QuestionBankClient) -> None:
        client._remaining_times = 10
        with respx.mock:
            respx.get(QUERY_URL).mock(return_value=httpx.Response(503))
            result = client.query("题目")
        assert result is None
        assert client.remaining_times == 10

    def test_query_http_error_does_not_crash(self, client: QuestionBankClient) -> None:
        # 先用 info 设置 times=10，再让 query 返回 500
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            respx.get(QUERY_URL).mock(return_value=httpx.Response(500))
            result = client.query("题目")
        assert result is None
        # 次数保持不变（10）
        assert client.remaining_times == 10


# ---------------------------------------------------------------------------
# 使用统计
# ---------------------------------------------------------------------------


class TestUsageStats:
    """题库使用统计：成功次数 / 总查询次数"""

    def test_stats_initial_zero(self, client: QuestionBankClient) -> None:
        """初始统计为 0"""
        assert client._success_count == 0
        assert client._total_queries == 0

    def test_success_increments_stats(self, client: QuestionBankClient) -> None:
        """成功查询增加 _success_count 和 _total_queries"""
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 9, "ai": False}}
                )
            )
            result = client.query("题目")
        assert result is not None
        assert client._success_count == 1
        assert client._total_queries == 1

    def test_no_answer_increments_total_only(self, client: QuestionBankClient) -> None:
        """无答案（code=0）增加 _total_queries 但不增加 _success_count"""
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {"question": "q", "answer": "无答案"}})
            )
            result = client.query("题目")
        assert result is None
        assert client._success_count == 0
        assert client._total_queries == 1

    def test_error_does_not_increment_stats(self, client: QuestionBankClient) -> None:
        """网络错误：_total_queries 增加（尝试了查询），_success_count 不增加"""
        client._remaining_times = 10
        with respx.mock:
            respx.get(QUERY_URL).mock(side_effect=httpx.ConnectError("conn refused"))
            result = client.query("题目")
        assert result is None
        assert client._success_count == 0
        # 失败的查询尝试也算一次"总查询"
        assert client._total_queries == 1

    def test_times_zero_skips_query_no_stats(self, client: QuestionBankClient) -> None:
        """times=0 跳过查询，不增加统计"""
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 0}}))
            result = client.query("题目")
        assert result is None
        assert client._success_count == 0
        assert client._total_queries == 0

    def test_get_usage_stats_returns_tuple(self, client: QuestionBankClient) -> None:
        """get_usage_stats() 返回 (success, total) 元组"""
        with respx.mock:
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 9, "ai": False}}
                )
            )
            client.query("题目1")
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {"question": "q", "answer": "无答案"}})
            )
            client.query("题目2")
        success, total = client.get_usage_stats()
        assert success == 1
        assert total == 2

    def test_success_query_logs_info(self, client: QuestionBankClient) -> None:
        """成功查询时 logger.info 被调用（提示用户题库被使用）"""
        with (
            respx.mock,
            patch("zhs.question_bank.client.logger") as mock_logger,
        ):
            respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"code": 1, "data": {"times": 10}}))
            respx.get(QUERY_URL).mock(
                return_value=httpx.Response(
                    200, json={"code": 1, "data": {"question": "q", "answer": "A", "times": 9, "ai": False}}
                )
            )
            result = client.query("题目")
        assert result is not None
        # 验证有 info 调用包含"题库"关键字
        info_calls = [c for c in mock_logger.info.call_args_list]
        assert any("题库" in str(c) for c in info_calls)

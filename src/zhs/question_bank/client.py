"""题库客户端：查询 enncy.cn 题库 API

使用独立 httpx.Client（不复用 ZhsSession，因后者带 zhihuishu Origin/Referer/cookies，
不适用于 enncy.cn）。失败绝不中断做题，捕获异常后返回 None 回退纯 LLM。
"""

import contextlib
import time
from typing import Any

import httpx
from loguru import logger

from zhs.question_bank.models import QuestionBankInfo, QuestionBankResult

_DEFAULT_QUERY_URL = "https://tk.enncy.cn/query"
_DEFAULT_INFO_URL = "https://tk.enncy.cn/info"
_USER_AGENT = "ZHS/0.1"


class QuestionBankClient:
    """题库查询客户端

    次数管理：懒加载 ``/info`` 缓存 ``_remaining_times``；成功查询（code=1）时从响应同步；
    无答案（code=0）不减；次数为 0 时跳过查询。
    """

    def __init__(
        self,
        token: str,
        query_url: str = _DEFAULT_QUERY_URL,
        info_url: str = _DEFAULT_INFO_URL,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._token = token
        self._query_url = query_url
        self._info_url = info_url
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        # 独立 client：plain UA，NO zhihuishu Origin/Referer/cookies
        self._client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": _USER_AGENT},
        )
        # None = 未知，懒加载；0 = 已耗尽
        self._remaining_times: int | None = None
        # 使用统计
        self._success_count: int = 0
        self._total_queries: int = 0

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def query(
        self,
        title: str,
        options: str = "",
        qtype: str = "unknown",
    ) -> QuestionBankResult | None:
        """查询题库。

        Returns:
            ``QuestionBankResult`` 成功（code=1）；``None`` 无答案（code=0）或出错。
            无答案与出错都不减次数。
        """
        # 懒加载剩余次数
        if self._remaining_times is None:
            self.get_info()
        if self._remaining_times == 0:
            logger.info("题库剩余次数为 0，跳过查询")
            return None

        params: dict[str, str] = {
            "token": self._token,
            "title": title,
            "type": qtype,
        }
        if options:
            params["options"] = options

        # 统计：实际发起查询（不含跳过）
        self._total_queries += 1

        data = self._get_with_retry(self._query_url, params)
        if data is None:
            return None

        code = data.get("code")
        if code == 1:
            result = QuestionBankResult.model_validate(data.get("data", {}))
            # 同步次数（仅成功查询才更新）
            self._remaining_times = result.times
            # 统计：成功查询
            self._success_count += 1
            # 用户可见的 log 提示
            logger.info(f"题库查询成功: 剩余次数 {result.times}, 本次使用 1 次（累计成功 {self._success_count} 次）")
            return result

        # code == 0：无答案，不减次数
        logger.debug(f"题库无答案: {data.get('message', '')}")
        return None

    def get_info(self) -> QuestionBankInfo | None:
        """查询题库信息接口，缓存剩余次数。"""
        data = self._get_with_retry(self._info_url, {"token": self._token})
        if data is None:
            return None
        if data.get("code") == 1:
            info = QuestionBankInfo.model_validate(data.get("data", {}))
            self._remaining_times = info.times
            logger.info(f"题库信息: 剩余 {info.times} 次, 累计 {info.user_times} 次, 成功 {info.success_times} 次")
            return info
        logger.warning(f"题库信息获取失败: {data.get('message', '')}")
        return None

    @property
    def remaining_times(self) -> int | None:
        """当前缓存的剩余次数（None 表示未查询过 /info）"""
        return self._remaining_times

    def get_usage_stats(self) -> tuple[int, int]:
        """获取使用统计

        Returns:
            (success_count, total_queries) 元组
        """
        return self._success_count, self._total_queries

    def close(self) -> None:
        self._client.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _get_with_retry(self, url: str, params: dict[str, str]) -> dict[str, Any] | None:
        """GET with retry on network/5xx/parse errors. Returns parsed JSON dict or None."""
        for attempt in range(self._max_retries):
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"题库请求 HTTP 错误 (尝试 {attempt + 1}/{self._max_retries}): {e.response.status_code}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                continue
            except (httpx.RequestError, ValueError) as e:
                # ValueError 涵盖 JSONDecodeError（malformed JSON）
                logger.error(f"题库请求失败 (尝试 {attempt + 1}/{self._max_retries}): {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                continue
            if isinstance(data, dict):
                return data
            logger.error(f"题库响应非 JSON 对象: {type(data).__name__}")
            return None
        return None

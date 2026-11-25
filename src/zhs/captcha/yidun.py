"""易盾验证码协议层（纯 HTTP）。

三段式：``getconf`` 取 dt → ``get`` 取题 → ``check`` 提交答案。
响应是 JSONP，需要剥掉回调外壳。
"""

import json
import random
import re
from typing import Any

import httpx
from loguru import logger

from zhs.captcha.codec import aes, generate_cb
from zhs.config import AppConfig

# captchaId 决定题型，调用方无法指定
CAPTCHA_SLIDE = "75f9f716460a422f89a628f50fd8cc2b"
CAPTCHA_CLICK = "4da3050565514a35a50541b0e1f54538"

ZONE_ID = "CN31"
SDK_VERSION = "2.28.5"
LOAD_VERSION = "2.5.0"
RUN_ENV = "10"
BASE_URL = "https://c.dun.163.com"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)


def create_client(config: AppConfig, timeout: float = 20.0) -> httpx.Client:
    """易盾独立客户端：不带智慧树 Cookie，仅沿用代理设置。"""
    proxy_dict = config.proxies.to_dict()
    proxy = proxy_dict.get("http") or proxy_dict.get("https") or None
    return httpx.Client(
        proxy=proxy,
        timeout=timeout,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )


def parse_jsonp(text: str) -> dict[str, Any]:
    """剥掉 ``__JSONP_xxx({...});`` 外壳。"""
    match = re.search(r"\((\{.*\})\)", text, re.S)
    if not match:
        raise ValueError(f"响应不是 JSONP: {text[:120]}")
    parsed: dict[str, Any] = json.loads(match.group(1))
    return parsed


def _callback(index: int = 0) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "__JSONP_" + "".join(random.choice(alphabet) for _ in range(7)) + f"_{index}"


def _get(client: httpx.Client, path: str, params: dict[str, Any], referer: str) -> dict[str, Any]:
    payload = {"referer": referer}
    payload.update({key: value for key, value in params.items() if value is not None})
    response = client.get(f"{BASE_URL}{path}", params=payload)
    response.raise_for_status()
    result = parse_jsonp(response.text)
    logger.debug(f"易盾 {path} -> error={result.get('error')} msg={result.get('msg')}")
    return result


def getconf(client: httpx.Client, captcha_id: str, referer: str) -> dict[str, Any]:
    """取 dt / irToken。"""
    return _get(
        client,
        "/api/v2/getconf",
        {
            "zoneId": "",
            "dt": "",
            "id": captcha_id,
            "ipv6": "false",
            "runEnv": RUN_ENV,
            "iv": "5",
            "loadVersion": LOAD_VERSION,
            "lang": "zh-CN",
            "callback": _callback(0),
        },
        referer,
    )


def fetch(
    client: httpx.Client,
    captcha_id: str,
    fp: str,
    width: int,
    dt: str = "",
    ir_token: str = "",
    referer: str = "",
) -> dict[str, Any]:
    """取题：返回 token / bg / front / type。"""
    return _get(
        client,
        "/api/v3/get",
        {
            "zoneId": ZONE_ID,
            "dt": dt,
            "irToken": ir_token,
            "id": captcha_id,
            "fp": fp,
            "https": "true",
            "type": "",
            "version": SDK_VERSION,
            "dpr": "2",
            "dev": "3",
            "cb": generate_cb(),
            "ipv6": "false",
            "runEnv": RUN_ENV,
            "group": "",
            "scene": "",
            "lang": "zh-CN",
            "sdkVersion": "",
            "loadVersion": LOAD_VERSION,
            "iv": "4",
            "user": "",
            "width": str(width),
            "audio": "false",
            "sizeType": "10",
            "smsVersion": "v3",
            "token": "",
            "callback": _callback(1),
        },
        referer,
    )


def check(
    client: httpx.Client,
    captcha_id: str,
    token: str,
    data: dict[str, Any],
    width: int,
    type_: int,
    dt: str = "",
    referer: str = "",
) -> dict[str, Any]:
    """提交答案，成功时 ``data.validate`` 是裸 validate。"""
    return _get(
        client,
        "/api/v3/check",
        {
            "zoneId": ZONE_ID,
            "dt": dt,
            "id": captcha_id,
            "token": token,
            "data": json.dumps(data, separators=(",", ":"), ensure_ascii=True),
            "width": str(width),
            "type": str(type_),
            "version": SDK_VERSION,
            "cb": generate_cb(),
            "user": "",
            "extraData": "",
            "bf": "5001",
            "runEnv": RUN_ENV,
            "sdkVersion": "",
            "loadVersion": LOAD_VERSION,
            "iv": "4",
            "callback": _callback(2),
        },
        referer,
    )


def compose_validate(raw_validate: str, fp: str, zone_id: str = ZONE_ID) -> str:
    """SDK 二次组装：``{zoneId}_{aes(raw+'::'+fp)}_v_i_1``。"""
    return f"{zone_id}_{aes(raw_validate + '::' + fp)}_v_i_1"


__all__ = [
    "BASE_URL",
    "CAPTCHA_CLICK",
    "CAPTCHA_SLIDE",
    "ZONE_ID",
    "check",
    "compose_validate",
    "create_client",
    "fetch",
    "getconf",
    "parse_jsonp",
]

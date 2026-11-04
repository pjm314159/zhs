"""Cookie 序列化工具模块"""

import json
from pathlib import Path
from typing import Any

import httpx


def read_cookies_file(cookies_path: Path) -> list[dict[str, Any]] | None:
    """读取 cookies.json；文件缺失、内容为空、损坏或不是非空列表时返回 None"""
    if not cookies_path.exists():
        return None

    try:
        with open(cookies_path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None

    if not isinstance(raw, list) or not raw:
        return None
    return raw


def cookies_to_list(cookies: httpx.Cookies) -> list[dict[str, Any]]:
    """将 httpx.Cookies 序列化为字典列表，每个字典包含 name、value、domain、path"""
    result: list[dict[str, Any]] = []
    for cookie in cookies.jar:
        result.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            }
        )
    return result


def list_to_cookies(cookie_list: list[dict[str, Any]]) -> httpx.Cookies:
    """将字典列表反序列化为 httpx.Cookies 对象"""
    cookies = httpx.Cookies()
    for item in cookie_list:
        cookies.set(
            item["name"],
            item["value"],
            domain=item.get("domain", ""),
            path=item.get("path", "/"),
        )
    return cookies

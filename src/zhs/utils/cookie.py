"""Cookie 序列化工具模块"""

from typing import Any

import httpx


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

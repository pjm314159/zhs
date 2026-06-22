"""知到作业本地缓存管理（兼容入口）

实际实现已迁移至 zhs.cache.zhidao_cache.ZhidaoHomeworkCache。
本模块通过 PEP 562 懒加载保留 HomeworkCache 别名，避免循环导入。
"""

from __future__ import annotations


def __getattr__(name: str) -> object:
    """懒加载 HomeworkCache，避免循环导入"""
    if name == "HomeworkCache":
        from zhs.cache.zhidao_cache import ZhidaoHomeworkCache

        return ZhidaoHomeworkCache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["HomeworkCache"]  # noqa: F822

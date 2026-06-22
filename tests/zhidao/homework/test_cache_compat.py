"""zhidao/homework/cache.py PEP 562 兼容入口测试

验证懒加载 HomeworkCache 别名指向 ZhidaoHomeworkCache。
"""

import importlib

import pytest

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache


class TestPep562LazyLoad:
    """PEP 562 模块级 __getattr__ 懒加载"""

    def test_homework_cache_alias_resolves_to_zhidao_cache(self) -> None:
        """HomeworkCache 别名解析为 ZhidaoHomeworkCache"""
        from zhs.zhidao.homework import cache as cache_mod

        assert cache_mod.HomeworkCache is ZhidaoHomeworkCache

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """未知属性抛出 AttributeError"""
        from zhs.zhidao.homework import cache as cache_mod

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = cache_mod.NotExist  # noqa: B018

    def test_attribute_error_message_contains_module_name(self) -> None:
        """AttributeError 信息包含模块名和属性名"""
        from zhs.zhidao.homework import cache as cache_mod

        with pytest.raises(AttributeError) as exc_info:
            _ = cache_mod.FooBar  # noqa: B018
        assert "zhs.zhidao.homework.cache" in str(exc_info.value)
        assert "FooBar" in str(exc_info.value)

    def test_module_all_contains_homework_cache(self) -> None:
        """__all__ 包含 HomeworkCache"""
        from zhs.zhidao.homework import cache as cache_mod

        assert "HomeworkCache" in cache_mod.__all__

    def test_repeated_access_returns_same_class(self) -> None:
        """多次访问返回同一个类对象"""
        from zhs.zhidao.homework import cache as cache_mod

        first = cache_mod.HomeworkCache
        second = cache_mod.HomeworkCache
        assert first is second

    def test_import_via_from_import(self) -> None:
        """from zhs.zhidao.homework.cache import HomeworkCache 可用"""
        # 使用 importlib 确保独立导入路径生效
        mod = importlib.import_module("zhs.zhidao.homework.cache")
        assert mod.HomeworkCache is ZhidaoHomeworkCache

    def test_homework_cache_instantiable(self) -> None:
        """通过别名可实例化"""
        from zhs.zhidao.homework.cache import HomeworkCache

        instance = HomeworkCache()  # type: ignore[operator]
        assert isinstance(instance, ZhidaoHomeworkCache)

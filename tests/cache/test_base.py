"""cache/base.py BaseQuestionCache 测试

验证缓存基类的路径管理、加载/保存、惰性加载、错误处理等公共行为。
"""

import json
from pathlib import Path
from typing import Any

import pytest

from zhs.cache.base import BaseQuestionCache


class _DummyCache(BaseQuestionCache[dict[str, Any]]):
    """用于测试的具体子类（条目类型为 dict）"""

    course_type = "dummy"

    def _deserialize_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        return dict(data)

    def _serialize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        return dict(entry)

    # 暴露受保护方法供测试
    def load_exam(self, course_id: int | str, exam_id: int | str) -> dict[str, dict[str, Any]]:
        return self._load_exam(course_id, exam_id)

    def save_exam(self, course_id: int | str, exam_id: int | str, entries: dict[str, dict[str, Any]]) -> None:
        self._save_exam(course_id, exam_id, entries)

    def load_all_exams(self, course_id: int | str) -> dict[str, dict[str, Any]]:
        return self._load_all_exams(course_id)

    def cache_path(self, course_id: int | str, exam_id: int | str) -> Path:
        return self._cache_path(course_id, exam_id)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """临时缓存目录"""
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir: Path) -> _DummyCache:
    """缓存实例"""
    return _DummyCache(cache_dir=cache_dir)


class TestCachePath:
    """缓存路径计算"""

    def test_path_format(self, cache: _DummyCache) -> None:
        """路径格式: {cache_dir}/{course_type}/{course_id}/{exam_id}.json"""
        path = cache.cache_path(100, "exam1")
        assert path.name == "exam1.json"
        assert path.parent.name == "100"
        assert path.parent.parent.name == "dummy"

    def test_path_with_string_ids(self, cache: _DummyCache) -> None:
        """字符串 ID 也能正确处理"""
        path = cache.cache_path("course_abc", "exam_xyz")
        assert "course_abc" in str(path)
        assert path.name == "exam_xyz.json"


class TestLoadExam:
    """加载 exam 缓存"""

    def test_load_empty_returns_empty(self, cache: _DummyCache) -> None:
        """空缓存返回空字典"""
        result = cache.load_exam(100, "exam1")
        assert result == {}

    def test_load_existing_file(self, cache: _DummyCache, cache_dir: Path) -> None:
        """加载已有文件"""
        # 准备文件
        path = cache_dir / "dummy" / "100" / "exam1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"q1": {"answer": "A"}}, f)

        result = cache.load_exam(100, "exam1")
        assert "q1" in result
        assert result["q1"]["answer"] == "A"

    def test_load_lazy_caching(self, cache: _DummyCache, cache_dir: Path) -> None:
        """惰性加载：第二次调用不重新读文件"""
        path = cache_dir / "dummy" / "100" / "exam1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"q1": {"answer": "A"}}, f)

        # 第一次加载
        result1 = cache.load_exam(100, "exam1")
        # 修改文件
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"q2": {"answer": "B"}}, f)
        # 第二次加载应返回缓存（不重新读文件）
        result2 = cache.load_exam(100, "exam1")
        assert result1 is result2
        assert "q1" in result2
        assert "q2" not in result2

    def test_load_corrupted_file(self, cache: _DummyCache, cache_dir: Path) -> None:
        """损坏文件不崩溃，返回空字典"""
        path = cache_dir / "dummy" / "100" / "exam1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid json{{{{", encoding="utf-8")

        result = cache.load_exam(100, "exam1")
        assert result == {}


class TestSaveExam:
    """保存 exam 缓存"""

    def test_save_creates_file(self, cache: _DummyCache, cache_dir: Path) -> None:
        """保存创建文件"""
        entries = {"q1": {"answer": "A"}}
        cache.save_exam(100, "exam1", entries)

        path = cache_dir / "dummy" / "100" / "exam1.json"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "q1" in data
        assert data["q1"]["answer"] == "A"

    def test_save_creates_parent_dirs(self, cache: _DummyCache, cache_dir: Path) -> None:
        """保存创建父目录"""
        cache.save_exam(999, "exam_xyz", {"q": {"a": "b"}})
        path = cache_dir / "dummy" / "999" / "exam_xyz.json"
        assert path.exists()

    def test_save_overwrites_existing(self, cache: _DummyCache, cache_dir: Path) -> None:
        """保存覆盖已有文件"""
        cache.save_exam(100, "exam1", {"q1": {"answer": "old"}})
        cache.save_exam(100, "exam1", {"q2": {"answer": "new"}})

        path = cache_dir / "dummy" / "100" / "exam1.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "q1" not in data
        assert "q2" in data


class TestLoadAllExams:
    """加载课程下所有 exam 缓存"""

    def test_load_all_empty(self, cache: _DummyCache) -> None:
        """空目录返回空字典"""
        result = cache.load_all_exams(100)
        assert result == {}

    def test_load_all_merges_multiple_exams(self, cache: _DummyCache) -> None:
        """合并多个 exam 文件"""
        cache.save_exam(100, "exam1", {"q1": {"answer": "A"}})
        cache.save_exam(100, "exam2", {"q2": {"answer": "B"}})

        result = cache.load_all_exams(100)
        assert "q1" in result
        assert "q2" in result

    def test_load_all_skips_corrupted(self, cache: _DummyCache, cache_dir: Path) -> None:
        """跳过损坏文件"""
        cache.save_exam(100, "exam1", {"q1": {"answer": "A"}})
        # 写入损坏文件
        path = cache_dir / "dummy" / "100" / "bad.json"
        path.write_text("invalid{{{{", encoding="utf-8")

        result = cache.load_all_exams(100)
        assert "q1" in result


class TestAbstractMethods:
    """抽象方法验证"""

    def test_cannot_instantiate_abstract(self) -> None:
        """不能直接实例化抽象类"""
        with pytest.raises(TypeError):
            BaseQuestionCache(  # type: ignore[abstract]
                cache_dir=Path(".")
            )

"""AiExamCache 测试

验证 AI 作业/考试缓存的行为：基本读写、合并加载、答案解析、持久化、损坏文件处理。
"""

import json
from pathlib import Path
from typing import Any

import pytest

from zhs.cache.ai_cache import AiExamCache


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """临时缓存目录"""
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir: Path) -> AiExamCache:
    """缓存实例"""
    return AiExamCache(cache_dir=cache_dir)


def _make_entry(
    question: str = "",
    answer: str = "",
    answer_content: str = "",
    question_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造缓存条目"""
    return {
        "question": question,
        "answer": answer,
        "answer_content": answer_content,
        "questionDict": question_dict or {},
    }


class TestCachePath:
    """缓存路径格式"""

    def test_path_uses_ai_subdir(self, cache: AiExamCache, cache_dir: Path) -> None:
        """路径格式: {cache_dir}/ai/{course_id}/{exam_id}.json"""
        cache.put(100, "exam1", 123, _make_entry(answer="A"))
        path = cache_dir / "ai" / "100" / "exam1.json"
        assert path.exists()


class TestBasicGetPut:
    """基本读写"""

    def test_get_empty(self, cache: AiExamCache) -> None:
        """空缓存返回 None"""
        assert cache.get(100, "exam1", 123) is None

    def test_put_and_get(self, cache: AiExamCache) -> None:
        """写入后读取"""
        entry = _make_entry(question="Q1", answer="A")
        cache.put(100, "exam1", 123, entry)
        result = cache.get(100, "exam1", 123)
        assert result is not None
        assert result["question"] == "Q1"
        assert result["answer"] == "A"

    def test_put_persists_to_file(self, cache: AiExamCache, cache_dir: Path) -> None:
        """写入后文件存在"""
        entry = _make_entry(answer="A")
        cache.put(100, "exam1", 123, entry)

        path = cache_dir / "ai" / "100" / "exam1.json"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # key 为纯 question_id 字符串
        assert "123" in data

    def test_key_is_question_id_string(self, cache: AiExamCache, cache_dir: Path) -> None:
        """key 为 question_id 的字符串形式"""
        cache.put(100, "exam1", 456, _make_entry(answer="B"))
        path = cache_dir / "ai" / "100" / "exam1.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "456" in data
        assert all(k.isdigit() for k in data)


class TestLoadAllForCourse:
    """加载课程下所有 exam 缓存"""

    def test_load_all_empty(self, cache: AiExamCache) -> None:
        """空目录返回空字典"""
        result = cache.load_all_for_course(100)
        assert result == {}

    def test_load_all_merges_multiple_exams(self, cache: AiExamCache) -> None:
        """合并多个 exam 文件"""
        cache.put(100, "exam1", 1, _make_entry(answer="A"))
        cache.put(100, "exam2", 2, _make_entry(answer="B"))

        result = cache.load_all_for_course(100)
        assert "1" in result
        assert "2" in result
        assert result["1"]["answer"] == "A"
        assert result["2"]["answer"] == "B"

    def test_load_all_skips_corrupted(self, cache: AiExamCache, cache_dir: Path) -> None:
        """跳过损坏文件"""
        cache.put(100, "exam1", 1, _make_entry(answer="A"))
        # 写入损坏文件
        path = cache_dir / "ai" / "100" / "bad.json"
        path.write_text("invalid{{{{", encoding="utf-8")

        result = cache.load_all_for_course(100)
        assert "1" in result


class TestParseAnswer:
    """答案解析（静态方法）"""

    def test_empty_returns_none(self) -> None:
        """空字符串返回 None"""
        assert AiExamCache.parse_answer("") is None

    def test_with_separator_splits(self) -> None:
        """含 #@# 分隔符→拆分"""
        assert AiExamCache.parse_answer("1#@#2#@#3") == ["1", "2", "3"]

    def test_without_separator_single_element(self) -> None:
        """不含 #@# → 单元素列表"""
        assert AiExamCache.parse_answer("答案") == ["答案"]

    def test_slash_not_split(self) -> None:
        """填空题 answer 含 / 不拆分"""
        result = AiExamCache.parse_answer("身体健康/心理健康")
        assert result == ["身体健康/心理健康"]


class TestReloadFromDisk:
    """从磁盘重新加载"""

    def test_reload_from_file(self, cache_dir: Path) -> None:
        """从文件重新加载"""
        cache1 = AiExamCache(cache_dir=cache_dir)
        cache1.put(100, "exam1", 123, _make_entry(answer="A"))

        # 新实例从文件加载
        cache2 = AiExamCache(cache_dir=cache_dir)
        result = cache2.get(100, "exam1", 123)
        assert result is not None
        assert result["answer"] == "A"


class TestCorruptedFile:
    """损坏文件处理"""

    def test_corrupted_file(self, cache_dir: Path) -> None:
        """损坏文件不崩溃"""
        path = cache_dir / "ai" / "100"
        path.mkdir(parents=True, exist_ok=True)
        (path / "exam1.json").write_text("invalid json{{{", encoding="utf-8")

        cache = AiExamCache(cache_dir=cache_dir)
        result = cache.get(100, "exam1", 123)
        assert result is None


class TestOverwrite:
    """覆盖写入"""

    def test_put_overwrites_existing(self, cache: AiExamCache) -> None:
        """put 覆盖已有条目"""
        cache.put(100, "exam1", 1, _make_entry(answer="old"))
        cache.put(100, "exam1", 1, _make_entry(answer="new"))
        result = cache.get(100, "exam1", 1)
        assert result is not None
        assert result["answer"] == "new"


class TestMultipleCourses:
    """多课程独立存储"""

    def test_multiple_courses_separate(self, cache: AiExamCache) -> None:
        """不同课程的缓存独立存储"""
        cache.put(100, "exam1", 1, _make_entry(answer="A"))
        cache.put(200, "exam1", 1, _make_entry(answer="B"))

        result1 = cache.get(100, "exam1", 1)
        result2 = cache.get(200, "exam1", 1)
        assert result1 is not None
        assert result2 is not None
        assert result1["answer"] == "A"
        assert result2["answer"] == "B"

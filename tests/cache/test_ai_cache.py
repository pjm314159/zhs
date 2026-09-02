"""AiExamCache 测试（SQLite 版）

验证 AI 作业/考试缓存的行为：基本读写、合并加载、答案解析、持久化、课程级查询、导入导出。
"""

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

    def test_db_file_exists(self, cache: AiExamCache, cache_dir: Path) -> None:
        """写入后 SQLite 数据库文件存在"""
        cache.put(100, "exam1", 123, _make_entry(answer="A"))
        db_path = cache_dir / "questions_bank.db"
        assert db_path.exists()

    def test_put_preserves_question_dict(self, cache: AiExamCache) -> None:
        """写入后 questionDict 正确保存"""
        qd = {"id": 1, "type": "single", "options": [{"id": 1, "content": "A"}]}
        cache.put(100, "exam1", 123, _make_entry(question="Q1", answer="1", question_dict=qd))
        result = cache.get(100, "exam1", 123)
        assert result is not None
        assert result["questionDict"] == qd


class TestLoadAllForCourse:
    """加载课程下所有 exam 缓存"""

    def test_load_all_empty(self, cache: AiExamCache) -> None:
        """空数据库返回空字典"""
        result = cache.load_all_for_course(100)
        assert result == {}

    def test_load_all_merges_multiple_exams(self, cache: AiExamCache) -> None:
        """合并多个 exam"""
        cache.put(100, "exam1", 1, _make_entry(answer="A"))
        cache.put(100, "exam2", 2, _make_entry(answer="B"))

        result = cache.load_all_for_course(100)
        assert "1" in result
        assert "2" in result
        assert result["1"]["answer"] == "A"
        assert result["2"]["answer"] == "B"


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

    def test_reload_from_db(self, cache_dir: Path) -> None:
        """从 SQLite 数据库重新加载"""
        cache1 = AiExamCache(cache_dir=cache_dir)
        cache1.put(100, "exam1", 123, _make_entry(answer="A"))

        # 新实例从数据库加载
        cache2 = AiExamCache(cache_dir=cache_dir)
        result = cache2.get(100, "exam1", 123)
        assert result is not None
        assert result["answer"] == "A"


class TestOverwrite:
    """覆盖写入（UPSERT）"""

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


class TestSearchInCourse:
    """课程级查询（仅 exam 模块使用）"""

    def test_search_finds_by_question_text(self, cache: AiExamCache) -> None:
        """按题目文本跨 exam 搜索"""
        cache.put(100, "exam1", 1, _make_entry(question="什么是 TCP？", answer="3"))
        cache.put(100, "exam2", 2, _make_entry(question="什么是 UDP？", answer="5"))

        # 在 exam2 中搜索 exam1 的题目
        result = cache.search_in_course(100, "什么是 TCP？")
        assert result is not None
        assert result["answer"] == "3"

    def test_search_skips_empty_answer(self, cache: AiExamCache) -> None:
        """跳过无答案的题目"""
        cache.put(100, "exam1", 1, _make_entry(question="Q1", answer=""))
        result = cache.search_in_course(100, "Q1")
        assert result is None

    def test_search_empty_question_returns_none(self, cache: AiExamCache) -> None:
        """空题目文本返回 None"""
        result = cache.search_in_course(100, "")
        assert result is None

    def test_search_no_match_returns_none(self, cache: AiExamCache) -> None:
        """无匹配返回 None"""
        cache.put(100, "exam1", 1, _make_entry(question="Q1", answer="A"))
        result = cache.search_in_course(100, "不存在的题目")
        assert result is None


class TestExportImport:
    """导出导入"""

    def test_export_course(self, cache: AiExamCache) -> None:
        """导出课程数据"""
        cache.put(100, "exam1", 1, _make_entry(question="Q1", answer="A"), course_name="测试课程")
        cache.put(100, "exam2", 2, _make_entry(question="Q2", answer="B"), course_name="测试课程")

        data = cache.export_course(100)
        assert data["type"] == "ai"
        assert data["course_id"] == 100
        assert data["course_name"] == "测试课程"
        assert len(data["exams"]) == 2

    def test_import_course(self, cache_dir: Path) -> None:
        """导入课程数据"""
        data = {
            "version": 2,
            "type": "ai",
            "course_id": 100,
            "course_name": "测试课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "question_id": "1",
                            "question": "Q1",
                            "answer": "A",
                            "answer_content": "选项A",
                            "questionDict": {"id": 1},
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache = AiExamCache(cache_dir=cache_dir)
        cache.import_course(data)

        result = cache.get(100, "exam1", 1)
        assert result is not None
        assert result["question"] == "Q1"
        assert result["answer"] == "A"
        assert result["questionDict"] == {"id": 1}

    def test_export_import_roundtrip(self, cache: AiExamCache, cache_dir: Path) -> None:
        """导出导入往返"""
        cache.put(100, "exam1", 1, _make_entry(question="Q1", answer="A"), course_name="课程")
        cache.put(100, "exam2", 2, _make_entry(question="Q2", answer="B"), course_name="课程")

        data = cache.export_course(100)

        # 导入到新缓存
        cache2 = AiExamCache(cache_dir=cache_dir / "other")
        cache2.import_course(data)

        assert cache2.get(100, "exam1", 1) is not None
        assert cache2.get(100, "exam2", 2) is not None
        result = cache2.get(100, "exam1", 1)
        assert result is not None
        assert result["answer"] == "A"

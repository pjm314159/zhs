"""ZhidaoHomeworkCache 测试

验证知到作业缓存的所有行为：基本读写、标记正确/错误、选项匹配、持久化、损坏文件处理。
"""

import json
from pathlib import Path

import pytest

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """临时缓存目录"""
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir: Path) -> ZhidaoHomeworkCache:
    """缓存实例"""
    return ZhidaoHomeworkCache(cache_dir=cache_dir)


class TestCachePath:
    """缓存路径格式"""

    def test_path_uses_zhidao_subdir(self, cache: ZhidaoHomeworkCache, cache_dir: Path) -> None:
        """路径格式: {cache_dir}/zhidao/{course_id}/{exam_id}.json"""
        cache.put(100, "exam1", "q1", HomeworkCacheEntry(questionType=1, lastUpdated="2026-06-21"))
        path = cache_dir / "zhidao" / "100" / "exam1.json"
        assert path.exists()


class TestBasicGetPut:
    """基本读写"""

    def test_get_empty(self, cache: ZhidaoHomeworkCache) -> None:
        """空缓存返回 None"""
        assert cache.get(100, "exam1", "eid1") is None

    def test_put_and_get(self, cache: ZhidaoHomeworkCache) -> None:
        """写入后读取"""
        entry = HomeworkCacheEntry(
            questionType=1,
            options=[HomeworkCacheOption(id=1, content="A")],
            correctOptions=[1],
            lastUpdated="2026-06-21T12:00:00",
        )
        cache.put(100, "exam1", "eid1", entry)
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert result.question_type == 1
        assert result.correct_options == [1]

    def test_put_persists_to_file(self, cache: ZhidaoHomeworkCache, cache_dir: Path) -> None:
        """写入后文件存在"""
        entry = HomeworkCacheEntry(questionType=1, lastUpdated="2026-06-21T12:00:00")
        cache.put(100, "exam1", "eid1", entry)

        path = cache_dir / "zhidao" / "100" / "exam1.json"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # 新格式：key 仅 question_key，无 courseId:examId: 前缀
        assert "eid1" in data
        assert "100:exam1:eid1" not in data

    def test_key_format_no_prefix(self, cache: ZhidaoHomeworkCache, cache_dir: Path) -> None:
        """新格式 key 无 courseId:examId: 前缀"""
        cache.mark_correct(100, "exam1", "eid1", [1])
        path = cache_dir / "zhidao" / "100" / "exam1.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "eid1" in data
        assert all(":" not in k for k in data)


class TestMarkCorrectWrong:
    """标记正确/错误选项"""

    def test_mark_correct(self, cache: ZhidaoHomeworkCache) -> None:
        """标记正确选项"""
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert 1 in result.correct_options
        assert 2 in result.correct_options

    def test_mark_wrong(self, cache: ZhidaoHomeworkCache) -> None:
        """标记错误选项"""
        cache.mark_wrong(100, "exam1", "eid1", [3, 4])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert 3 in result.wrong_options
        assert 4 in result.wrong_options

    def test_mark_correct_removes_from_wrong(self, cache: ZhidaoHomeworkCache) -> None:
        """标记正确后从错误列表移除"""
        cache.mark_wrong(100, "exam1", "eid1", [1, 2])
        cache.mark_correct(100, "exam1", "eid1", [1])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert 1 in result.correct_options
        assert 1 not in result.wrong_options
        assert 2 in result.wrong_options

    def test_mark_wrong_removes_from_correct(self, cache: ZhidaoHomeworkCache) -> None:
        """标记错误后从正确列表移除"""
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        cache.mark_wrong(100, "exam1", "eid1", [1])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert 1 not in result.correct_options
        assert 1 in result.wrong_options
        assert 2 in result.correct_options


class TestGetOptions:
    """获取选项列表"""

    def test_get_correct_options(self, cache: ZhidaoHomeworkCache) -> None:
        """获取正确选项"""
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        assert cache.get_correct_options(100, "exam1", "eid1") == [1, 2]

    def test_get_wrong_options(self, cache: ZhidaoHomeworkCache) -> None:
        """获取错误选项"""
        cache.mark_wrong(100, "exam1", "eid1", [3])
        assert cache.get_wrong_options(100, "exam1", "eid1") == [3]

    def test_get_correct_options_empty(self, cache: ZhidaoHomeworkCache) -> None:
        """无缓存时返回空列表"""
        assert cache.get_correct_options(100, "exam1", "eid1") == []


class TestSaveOptions:
    """保存选项信息"""

    def test_save_options(self, cache: ZhidaoHomeworkCache) -> None:
        """保存选项信息"""
        options = [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")]
        cache.save_options(100, "exam1", "eid1", question_type=1, options=options)
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert result.question_type == 1
        assert len(result.options) == 2
        assert result.options[0].id == 1

    def test_save_options_no_overwrite(self, cache: ZhidaoHomeworkCache) -> None:
        """已有选项时不覆盖"""
        options1 = [HomeworkCacheOption(id=1, content="A")]
        options2 = [HomeworkCacheOption(id=2, content="B")]
        cache.save_options(100, "exam1", "eid1", question_type=1, options=options1)
        cache.save_options(100, "exam1", "eid1", question_type=2, options=options2)
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        # 选项不覆盖，但 question_type 更新
        assert result.question_type == 2
        assert len(result.options) == 1
        assert result.options[0].id == 1


class TestSaveAiAnalysis:
    """保存 AI 解析"""

    def test_save_ai_analysis(self, cache: ZhidaoHomeworkCache) -> None:
        """保存 AI 解析内容"""
        cache.save_ai_analysis(100, "exam1", "eid1", "解析内容")
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert result.ai_analysis == "解析内容"


class TestMultipleExams:
    """多 exam 独立存储"""

    def test_multiple_exams(self, cache: ZhidaoHomeworkCache) -> None:
        """多个 exam 独立存储"""
        cache.mark_correct(100, "exam1", "eid1", [1])
        cache.mark_correct(100, "exam2", "eid2", [2])
        assert cache.get_correct_options(100, "exam1", "eid1") == [1]
        assert cache.get_correct_options(100, "exam2", "eid2") == [2]


class TestReloadFromDisk:
    """从磁盘重新加载"""

    def test_reload_from_file(self, cache_dir: Path) -> None:
        """从文件重新加载"""
        cache1 = ZhidaoHomeworkCache(cache_dir=cache_dir)
        cache1.mark_correct(100, "exam1", "eid1", [1])

        # 新实例从文件加载
        cache2 = ZhidaoHomeworkCache(cache_dir=cache_dir)
        result = cache2.get(100, "exam1", "eid1")
        assert result is not None
        assert result.correct_options == [1]


class TestCorruptedFile:
    """损坏文件处理"""

    def test_corrupted_file(self, cache_dir: Path) -> None:
        """损坏文件不崩溃"""
        path = cache_dir / "zhidao" / "100"
        path.mkdir(parents=True, exist_ok=True)
        (path / "exam1.json").write_text("invalid json{{{", encoding="utf-8")

        cache = ZhidaoHomeworkCache(cache_dir=cache_dir)
        result = cache.get(100, "exam1", "eid1")
        assert result is None


class TestFindKeyByOptions:
    """通过选项匹配查找 question key"""

    def test_find_key_by_options(self, cache: ZhidaoHomeworkCache) -> None:
        """通过选项 ID 集合查找 question key"""
        options = [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")]
        cache.save_options(100, "exam1", "eid1", question_type=1, options=options)

        result = cache.find_key_by_options(100, "exam1", [1, 2])
        assert result == "eid1"

    def test_find_key_no_match(self, cache: ZhidaoHomeworkCache) -> None:
        """无匹配返回 None"""
        options = [HomeworkCacheOption(id=1, content="A")]
        cache.save_options(100, "exam1", "eid1", question_type=1, options=options)

        result = cache.find_key_by_options(100, "exam1", [999])
        assert result is None

    def test_find_key_empty_cache(self, cache: ZhidaoHomeworkCache) -> None:
        """空缓存返回 None"""
        result = cache.find_key_by_options(100, "exam1", [1, 2])
        assert result is None

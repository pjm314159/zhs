"""ZhidaoHomeworkCache 测试（SQLite 版）

验证知到作业缓存的所有行为：基本读写、标记正确/错误、选项匹配、持久化、双键查询。
SQLite 实现（questions_bank.db）的详细测试见 test_zhidao_cache_db.py。
本文件保留行为兼容性测试。
"""

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

    def test_db_file_exists(self, cache: ZhidaoHomeworkCache, cache_dir: Path) -> None:
        """写入后 SQLite 数据库文件存在"""
        entry = HomeworkCacheEntry(questionType=1, lastUpdated="2026-06-21T12:00:00")
        cache.put(100, "exam1", "eid1", entry)
        db_path = cache_dir / "questions_bank.db"
        assert db_path.exists()


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
        """标记错误选择方式（追加组合，不合并）"""
        cache.mark_wrong(100, "exam1", "eid1", [3, 4])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert [3, 4] in result.wrong_options

    def test_mark_correct_removes_matching_wrong(self, cache: ZhidaoHomeworkCache) -> None:
        """标记正确后移除完全匹配的错误组合"""
        cache.mark_wrong(100, "exam1", "eid1", [1, 2])
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        assert 1 in result.correct_options
        assert 2 in result.correct_options
        assert [1, 2] not in result.wrong_options

    def test_mark_wrong_does_not_remove_from_correct(self, cache: ZhidaoHomeworkCache) -> None:
        """标记错误组合不从正确列表移除（多选题可能部分正确）"""
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        cache.mark_wrong(100, "exam1", "eid1", [1])
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        # correct_options 不变（多选场景下 1 可能仍正确）
        assert 1 in result.correct_options
        assert 2 in result.correct_options
        assert [1] in result.wrong_options


class TestGetOptions:
    """获取选项列表"""

    def test_get_correct_options(self, cache: ZhidaoHomeworkCache) -> None:
        """获取正确选项"""
        cache.mark_correct(100, "exam1", "eid1", [1, 2])
        assert cache.get_correct_options(100, "exam1", "eid1") == [1, 2]

    def test_get_wrong_options(self, cache: ZhidaoHomeworkCache) -> None:
        """获取错误选择方式列表"""
        cache.mark_wrong(100, "exam1", "eid1", [3])
        assert cache.get_wrong_options(100, "exam1", "eid1") == [[3]]

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

    def test_save_options_by_eid_skips_existing(self, cache: ZhidaoHomeworkCache) -> None:
        """eid 已有记录时跳过（不覆盖选项、不更新 question_type）"""
        options1 = [HomeworkCacheOption(id=1, content="A")]
        options2 = [HomeworkCacheOption(id=2, content="B")]
        cache.save_options(100, "exam1", "eid1", question_type=1, options=options1)
        cache.save_options(100, "exam1", "eid1", question_type=2, options=options2)
        result = cache.get(100, "exam1", "eid1")
        assert result is not None
        # eid 保存跳过已有记录，保留第一次的数据
        assert result.question_type == 1
        assert len(result.options) == 1
        assert result.options[0].id == 1

    def test_save_options_by_id_updates_existing(self, cache: ZhidaoHomeworkCache) -> None:
        """id 已有记录时更新（question_type、options 均更新）"""
        options1 = [HomeworkCacheOption(id=1, content="A")]
        options2 = [HomeworkCacheOption(id=2, content="B")]
        cache.save_options(100, "exam1", "1001", question_type=1, options=options1)
        cache.save_options(100, "exam1", "1001", question_type=2, options=options2)
        result = cache.get(100, "exam1", "1001")
        assert result is not None
        # id 保存更新已有记录
        assert result.question_type == 2
        assert len(result.options) == 1
        assert result.options[0].id == 2


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

    def test_reload_from_db(self, cache_dir: Path) -> None:
        """从 SQLite 数据库重新加载"""
        cache1 = ZhidaoHomeworkCache(cache_dir=cache_dir)
        cache1.mark_correct(100, "exam1", "eid1", [1])

        # 新实例从数据库加载
        cache2 = ZhidaoHomeworkCache(cache_dir=cache_dir)
        result = cache2.get(100, "exam1", "eid1")
        assert result is not None
        assert result.correct_options == [1]


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

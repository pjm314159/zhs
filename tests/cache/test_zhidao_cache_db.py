"""SQLite 版 ZhidaoHomeworkCache 单元测试

覆盖双键存储、桥接写入、课程级查询、导入导出。
"""

from pathlib import Path

import pytest

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.zhidao.homework.models import HomeworkCacheOption


@pytest.fixture
def cache(tmp_path: Path) -> ZhidaoHomeworkCache:
    """临时数据库的 cache 实例"""
    return ZhidaoHomeworkCache(cache_dir=tmp_path)


class TestSaveAndGet:
    """保存与查询"""

    def test_save_by_eid_and_get(self, cache: ZhidaoHomeworkCache) -> None:
        """save_options_by_eid 保存后，按 eid 查询"""
        options = [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")]
        cache.save_options_by_eid(
            course_id=100,
            exam_id="exam1",
            eid="eid_abc",
            question_type=1,
            options=options,
            content="题目文本",
            course_name="测试课程",
        )
        entry = cache.get(100, "exam1", "eid_abc")
        assert entry is not None
        assert entry.question_type == 1
        assert entry.content == "题目文本"
        assert len(entry.options) == 2

    def test_save_by_id_and_get(self, cache: ZhidaoHomeworkCache) -> None:
        """save_options_by_id 保存后，按数字 id 查询"""
        options = [HomeworkCacheOption(id=1, content="A")]
        cache.save_options_by_id(
            course_id=100,
            exam_id="exam1",
            question_id="12345",
            question_type=1,
            options=options,
            content="题目",
            course_name="课程",
        )
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert entry.options[0].id == 1

    def test_get_nonexistent_returns_none(self, cache: ZhidaoHomeworkCache) -> None:
        """查询不存在的 key 返回 None"""
        assert cache.get(100, "exam1", "nonexistent") is None


class TestSaveByEidSkip:
    """save_options_by_eid 已有记录时跳过"""

    def test_skip_existing_eid(self, cache: ZhidaoHomeworkCache) -> None:
        """已有 eid 记录 → 跳过（不覆盖）"""
        options1 = [HomeworkCacheOption(id=1, content="A")]
        cache.save_options_by_eid(
            100,
            "exam1",
            "eid_abc",
            1,
            options1,
            "题目",
            "课程",
        )
        # 第二次保存不同选项 → 应跳过
        options2 = [HomeworkCacheOption(id=2, content="B")]
        cache.save_options_by_eid(
            100,
            "exam1",
            "eid_abc",
            1,
            options2,
            "新题目",
            "课程",
        )
        entry = cache.get(100, "exam1", "eid_abc")
        assert entry is not None
        assert entry.options[0].id == 1  # 保持第一次的选项


class TestBridgeOnSaveById:
    """save_options_by_id 桥接写入"""

    def test_bridge_finds_eid_record(self, cache: ZhidaoHomeworkCache) -> None:
        """id 保存时桥接找到之前的 eid 记录 → UPDATE（补上 question_id）"""
        options = [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")]
        # 先保存 eid
        cache.save_options_by_eid(100, "exam1", "eid_abc", 1, options, "题目", "课程")
        # 再保存 id（选项相同 → 桥接命中）
        cache.save_options_by_id(100, "exam1", "12345", 1, options, "题目", "课程")
        # 按 id 查询
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        # 按 eid 查询也能找到（同一条记录）
        entry_eid = cache.get(100, "exam1", "eid_abc")
        assert entry_eid is not None

    def test_bridge_fill_blank_by_content(self, cache: ZhidaoHomeworkCache) -> None:
        """填空题（无选项）按 content 桥接"""
        cache.save_options_by_eid(
            100,
            "exam1",
            "eid_fill",
            3,
            [],
            "填空题内容",
            "课程",
        )
        cache.save_options_by_id(
            100,
            "exam1",
            "67890",
            3,
            [],
            "填空题内容",
            "课程",
        )
        entry = cache.get(100, "exam1", "67890")
        assert entry is not None
        assert entry.content == "填空题内容"

    def test_no_bridge_inserts_new(self, cache: ZhidaoHomeworkCache) -> None:
        """桥接没找到 → INSERT 新记录（eid=NULL）"""
        cache.save_options_by_id(
            100,
            "exam1",
            "12345",
            1,
            [HomeworkCacheOption(id=1, content="A")],
            "题目",
            "课程",
        )
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None


class TestMarkCorrect:
    """mark_correct"""

    def test_mark_correct_adds_option(self, cache: ZhidaoHomeworkCache) -> None:
        """标记正确选项"""
        cache.save_options_by_id(
            100,
            "exam1",
            "12345",
            1,
            [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            "题目",
            "课程",
        )
        cache.mark_correct(100, "exam1", "12345", [1])
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert 1 in entry.correct_options

    def test_mark_correct_merges(self, cache: ZhidaoHomeworkCache) -> None:
        """多次 mark_correct 合并"""
        cache.save_options_by_id(100, "exam1", "12345", 1, [], "题目", "课程")
        cache.mark_correct(100, "exam1", "12345", [1])
        cache.mark_correct(100, "exam1", "12345", [2])
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert set(entry.correct_options) == {1, 2}


class TestMarkWrong:
    """mark_wrong"""

    def test_mark_wrong_choice(self, cache: ZhidaoHomeworkCache) -> None:
        """标记错误选择题组合"""
        cache.save_options_by_id(100, "exam1", "12345", 1, [], "题目", "课程")
        cache.mark_wrong(100, "exam1", "12345", [1, 2])
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert [1, 2] in entry.wrong_options

    def test_mark_wrong_dedup(self, cache: ZhidaoHomeworkCache) -> None:
        """相同错误组合不重复追加"""
        cache.save_options_by_id(100, "exam1", "12345", 1, [], "题目", "课程")
        cache.mark_wrong(100, "exam1", "12345", [1, 2])
        cache.mark_wrong(100, "exam1", "12345", [2, 1])  # 顺序不同但相同
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert len(entry.wrong_options) == 1


class TestFindKey:
    """find_key_by_options / find_key_by_content"""

    def test_find_by_options(self, cache: ZhidaoHomeworkCache) -> None:
        """按选项 ID 集合查找 key"""
        options = [HomeworkCacheOption(id=10, content="A"), HomeworkCacheOption(id=20, content="B")]
        cache.save_options_by_eid(100, "exam1", "eid_x", 1, options, "题目", "课程")
        key = cache.find_key_by_options(100, "exam1", [20, 10])
        assert key == "eid_x"

    def test_find_by_content(self, cache: ZhidaoHomeworkCache) -> None:
        """按内容查找 key"""
        cache.save_options_by_eid(100, "exam1", "eid_y", 3, [], "填空题", "课程")
        key = cache.find_key_by_content(100, "exam1", "填空题")
        assert key == "eid_y"

    def test_find_by_options_no_match(self, cache: ZhidaoHomeworkCache) -> None:
        """未匹配返回 None"""
        cache.save_options_by_eid(100, "exam1", "eid_x", 1, [HomeworkCacheOption(id=1, content="A")], "题目", "课程")
        assert cache.find_key_by_options(100, "exam1", [999]) is None


class TestSearchInCourse:
    """search_in_course 跨 exam 搜索"""

    def test_search_by_options_cross_exam(self, cache: ZhidaoHomeworkCache) -> None:
        """跨 exam 按选项搜索"""
        options = [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")]
        cache.save_options_by_id(100, "exam1", "111", 1, options, "题目A", "课程")
        cache.mark_correct(100, "exam1", "111", [1])
        # 在 exam2 中搜索 → 命中 exam1 的记录
        result = cache.search_in_course(100, option_ids=[1, 2])
        assert result is not None
        assert 1 in result.correct_options

    def test_search_by_content_cross_exam(self, cache: ZhidaoHomeworkCache) -> None:
        """跨 exam 按内容搜索"""
        cache.save_options_by_id(100, "exam1", "222", 3, [], "填空题X", "课程")
        cache.mark_correct(100, "exam1", "222", [1])
        result = cache.search_in_course(100, content="填空题X")
        assert result is not None

    def test_search_no_answer_skipped(self, cache: ZhidaoHomeworkCache) -> None:
        """没有答案的题目不被返回"""
        cache.save_options_by_id(100, "exam1", "333", 1, [HomeworkCacheOption(id=1, content="A")], "题目", "课程")
        # 没有标记 correct/wrong/ai_analysis → 不应返回
        result = cache.search_in_course(100, option_ids=[1])
        assert result is None


class TestSaveAiAnalysis:
    """save_ai_analysis"""

    def test_save_analysis(self, cache: ZhidaoHomeworkCache) -> None:
        """保存 AI 解析"""
        cache.save_options_by_id(100, "exam1", "12345", 1, [], "题目", "课程")
        cache.save_ai_analysis(100, "exam1", "12345", "解析内容")
        entry = cache.get(100, "exam1", "12345")
        assert entry is not None
        assert entry.ai_analysis == "解析内容"


class TestExportImport:
    """导出导入"""

    def test_export_course(self, cache: ZhidaoHomeworkCache) -> None:
        """导出课程数据"""
        cache.save_options_by_id(100, "exam1", "111", 1, [HomeworkCacheOption(id=1, content="A")], "题目", "课程名")
        cache.mark_correct(100, "exam1", "111", [1])
        data = cache.export_course(100)
        assert data["version"] == 2
        assert data["type"] == "zhidao"
        assert data["course_id"] == 100
        assert data["course_name"] == "课程名"
        assert len(data["exams"]) == 1
        assert data["exams"][0]["exam_id"] == "exam1"
        assert len(data["exams"][0]["questions"]) == 1

    def test_import_course(self, cache: ZhidaoHomeworkCache) -> None:
        """导入课程数据"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 200,
            "course_name": "导入课程",
            "exams": [
                {
                    "exam_id": "ex1",
                    "questions": [
                        {
                            "eid": "eid_imp",
                            "question_id": "999",
                            "questionType": 1,
                            "content": "导入题目",
                            "options": [{"id": 1, "content": "A"}],
                            "correctOptions": [1],
                            "wrongOptions": [],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        entry = cache.get(200, "ex1", "999")
        assert entry is not None
        assert entry.content == "导入题目"
        assert 1 in entry.correct_options

    def test_export_import_roundtrip(self, cache: ZhidaoHomeworkCache) -> None:
        """导出→导入往返"""
        cache.save_options_by_id(100, "exam1", "111", 1, [HomeworkCacheOption(id=1, content="A")], "题目", "课程")
        cache.mark_correct(100, "exam1", "111", [1])
        exported = cache.export_course(100)

        # 导入到另一个 cache
        cache2 = ZhidaoHomeworkCache(cache_dir=cache._cache_dir)
        cache2.import_course(exported)
        entry = cache2.get(100, "exam1", "111")
        assert entry is not None
        assert 1 in entry.correct_options


class TestImportBothKeys:
    """导入时同时存在 eid 和 question_id — 应同时保留两个 key"""

    def test_import_both_keys_preserves_both(self, cache: ZhidaoHomeworkCache) -> None:
        """同时有 eid 和 question_id → 两个 key 都能查到同一条记录"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_both",
                            "question_id": "8888",
                            "questionType": 1,
                            "content": "双键题目",
                            "options": [{"id": 1, "content": "A"}],
                            "correctOptions": [1],
                            "wrongOptions": [],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        # 两个 key 都能查到
        entry_by_id = cache.get(100, "exam1", "8888")
        entry_by_eid = cache.get(100, "exam1", "eid_both")
        assert entry_by_id is not None
        assert entry_by_eid is not None
        assert entry_by_id.content == "双键题目"
        assert entry_by_eid.content == "双键题目"
        assert 1 in entry_by_id.correct_options
        assert 1 in entry_by_eid.correct_options

    def test_import_both_keys_single_row(self, cache: ZhidaoHomeworkCache) -> None:
        """同时有 eid 和 question_id → 数据库只有一行（不重复）"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_single",
                            "question_id": "7777",
                            "questionType": 1,
                            "content": "单行题目",
                            "options": [{"id": 1, "content": "A"}],
                            "correctOptions": [1],
                            "wrongOptions": [],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        import sqlite3

        conn = sqlite3.connect(cache._cache_dir / "questions_bank.db")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND (eid=? OR question_id=?)",
            (100, "exam1", "eid_single", "7777"),
        ).fetchall()
        conn.close()
        assert len(rows) == 1  # 只有一行
        assert rows[0]["eid"] == "eid_single"
        assert rows[0]["question_id"] == "7777"

    def test_import_both_keys_merges_existing_eid_row(self, cache: ZhidaoHomeworkCache) -> None:
        """已有 eid 行 + 导入同时含 eid 和 question_id → 合并为一行，保留 eid 行的答案"""
        # 先用 save_options_by_eid 建立一条 eid 记录，并标记正确选项
        cache.save_options_by_eid(
            100,
            "exam1",
            "eid_exist",
            1,
            [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            "已有题目",
            "课程",
        )
        cache.mark_correct(100, "exam1", "eid_exist", [1, 2])

        # 导入：选项不同（无法桥接），但 eid 相同 + question_id 也有
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_exist",
                            "question_id": "6666",
                            "questionType": 1,
                            "content": "已有题目",
                            "options": [{"id": 10, "content": "X"}],  # 不同选项
                            "correctOptions": [],
                            "wrongOptions": [],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        # 合并后：两个 key 都能查到，且原有 correct_options 保留
        entry_by_id = cache.get(100, "exam1", "6666")
        entry_by_eid = cache.get(100, "exam1", "eid_exist")
        assert entry_by_id is not None
        assert entry_by_eid is not None
        # 原有正确选项应保留（合并）
        assert set(entry_by_id.correct_options) == {1, 2}


class TestImportWrongOptions:
    """导入 wrongOptions — 无 correct 时应导入 wrong"""

    def test_import_wrong_options_no_correct(self, cache: ZhidaoHomeworkCache) -> None:
        """无 correctOptions + 有 wrongOptions → wrong 被导入"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_w",
                            "question_id": "5555",
                            "questionType": 1,
                            "content": "错题",
                            "options": [{"id": 1, "content": "A"}, {"id": 2, "content": "B"}],
                            "correctOptions": [],
                            "wrongOptions": [[1, 2], [2]],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        entry = cache.get(100, "exam1", "5555")
        assert entry is not None
        assert entry.correct_options == []
        assert len(entry.wrong_options) == 2
        assert sorted(entry.wrong_options[0]) == [1, 2]
        assert entry.wrong_options[1] == [2]

    def test_import_wrong_options_fill_blank(self, cache: ZhidaoHomeworkCache) -> None:
        """填空题 wrongOptions（list[str]）→ 正确导入"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_fill",
                            "question_id": "6666",
                            "questionType": 3,
                            "content": "填空题",
                            "options": [],
                            "correctOptions": [],
                            "wrongOptions": [["错误答案1"], ["错误答案2"]],
                            "aiAnalysis": "解析",
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        entry = cache.get(100, "exam1", "6666")
        assert entry is not None
        assert len(entry.wrong_options) == 2
        assert ["错误答案1"] in entry.wrong_options
        assert ["错误答案2"] in entry.wrong_options
        assert entry.ai_analysis == "解析"

    def test_import_wrong_options_eid_only(self, cache: ZhidaoHomeworkCache) -> None:
        """仅有 eid（无 question_id）的 wrongOptions → 正确导入"""
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_only",
                            "question_id": None,
                            "questionType": 1,
                            "content": "仅 eid 题目",
                            "options": [{"id": 1, "content": "A"}],
                            "correctOptions": [],
                            "wrongOptions": [[1]],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)
        entry = cache.get(100, "exam1", "eid_only")
        assert entry is not None
        assert [1] in entry.wrong_options


class TestReImportEid:
    """重新导入时 eid 关联"""

    def test_re_import_links_eid_on_existing_null(self, cache: ZhidaoHomeworkCache) -> None:
        """已有 qid 行（eid=NULL，旧代码导入）→ 重新导入补上 eid"""
        # 模拟旧代码导入：直接 save_options_by_id（eid=NULL）
        cache.save_options_by_id(
            100,
            "exam1",
            "8888",
            1,
            [HomeworkCacheOption(id=1, content="A")],
            "题目",
            "课程",
        )
        cache.mark_correct(100, "exam1", "8888", [1])
        # 确认 eid 为 NULL
        import sqlite3

        conn = sqlite3.connect(cache._cache_dir / "questions_bank.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT eid FROM zhidao_questions WHERE course_id=? AND question_id=?",
            (100, "8888"),
        ).fetchone()
        assert row["eid"] is None
        conn.close()

        # 重新导入（新代码，有 eid）
        export_data = {
            "version": 2,
            "type": "zhidao",
            "course_id": 100,
            "course_name": "课程",
            "exams": [
                {
                    "exam_id": "exam1",
                    "questions": [
                        {
                            "eid": "eid_relink",
                            "question_id": "8888",
                            "questionType": 1,
                            "content": "题目",
                            "options": [{"id": 1, "content": "A"}],
                            "correctOptions": [1],
                            "wrongOptions": [],
                            "aiAnalysis": None,
                            "lastUpdated": "2026-01-01T00:00:00",
                        }
                    ],
                }
            ],
        }
        cache.import_course(export_data)

        # eid 应被补上
        entry_by_id = cache.get(100, "exam1", "8888")
        entry_by_eid = cache.get(100, "exam1", "eid_relink")
        assert entry_by_id is not None
        assert entry_by_eid is not None
        assert 1 in entry_by_id.correct_options  # 原有 correct 保留


class TestExportOptimization:
    """导出优化 — 有 correct 时跳过 wrong/ai"""

    def test_export_skips_wrong_when_correct_exists(self, cache: ZhidaoHomeworkCache) -> None:
        """有 correctOptions → 导出时 wrongOptions=[], aiAnalysis=None"""
        cache.save_options_by_id(
            100,
            "exam1",
            "111",
            1,
            [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            "题目",
            "课程",
        )
        cache.mark_wrong(100, "exam1", "111", [2])
        cache.save_ai_analysis(100, "exam1", "111", "AI 解析内容")
        cache.mark_correct(100, "exam1", "111", [1])

        data = cache.export_course(100)
        q = data["exams"][0]["questions"][0]
        assert q["correctOptions"] == [1]
        # 有正确选项时，wrong 和 ai 应被清空（节省内存）
        assert q["wrongOptions"] == []
        assert q["aiAnalysis"] is None

    def test_export_keeps_wrong_when_no_correct(self, cache: ZhidaoHomeworkCache) -> None:
        """无 correctOptions → 导出时保留 wrongOptions 和 aiAnalysis"""
        cache.save_options_by_id(
            100,
            "exam1",
            "222",
            1,
            [HomeworkCacheOption(id=1, content="A")],
            "题目",
            "课程",
        )
        cache.mark_wrong(100, "exam1", "222", [1])
        cache.save_ai_analysis(100, "exam1", "222", "AI 解析内容")

        data = cache.export_course(100)
        q = data["exams"][0]["questions"][0]
        assert q["correctOptions"] == []
        # 无正确选项时，wrong 和 ai 应保留
        assert len(q["wrongOptions"]) == 1
        assert q["aiAnalysis"] == "AI 解析内容"


class TestMarkCorrectAutoClearWrong:
    """mark_correct 的 auto_clear_wrong 参数"""

    def test_first_correct_no_clear(self, cache: ZhidaoHomeworkCache) -> None:
        """首次做对（之前无 wrong）→ auto_clear_wrong=True 也不影响"""
        cache.save_options_by_id(
            100,
            "exam1",
            "111",
            1,
            [HomeworkCacheOption(id=1, content="A")],
            "题目",
            "课程",
        )
        cache.mark_correct(100, "exam1", "111", [1], auto_clear_wrong=True)
        entry = cache.get(100, "exam1", "111")
        assert entry is not None
        assert 1 in entry.correct_options
        assert entry.wrong_options == []  # 本来就没有

    def test_re_correct_clears_wrong_and_ai(self, cache: ZhidaoHomeworkCache) -> None:
        """再次做对（之前做错）→ auto_clear_wrong=True 清除 wrong 和 ai_analysis"""
        cache.save_options_by_id(
            100,
            "exam1",
            "222",
            1,
            [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            "题目",
            "课程",
        )
        # 先做错
        cache.mark_wrong(100, "exam1", "222", [2])
        cache.save_ai_analysis(100, "exam1", "222", "错题解析")
        # 再次做对
        cache.mark_correct(100, "exam1", "222", [1], auto_clear_wrong=True)
        entry = cache.get(100, "exam1", "222")
        assert entry is not None
        assert 1 in entry.correct_options
        # wrong 和 ai 应被清除
        assert entry.wrong_options == []
        assert entry.ai_analysis is None

    def test_re_correct_no_auto_clear_keeps_wrong(self, cache: ZhidaoHomeworkCache) -> None:
        """再次做对但 auto_clear_wrong=False（默认）→ 保留 wrong（仅移除匹配的组合）"""
        cache.save_options_by_id(
            100,
            "exam1",
            "333",
            1,
            [HomeworkCacheOption(id=1, content="A"), HomeworkCacheOption(id=2, content="B")],
            "题目",
            "课程",
        )
        cache.mark_wrong(100, "exam1", "333", [2])
        cache.save_ai_analysis(100, "exam1", "333", "错题解析")
        # 默认 auto_clear_wrong=False
        cache.mark_correct(100, "exam1", "333", [1])
        entry = cache.get(100, "exam1", "333")
        assert entry is not None
        assert 1 in entry.correct_options
        # wrong 应保留（[2] 不匹配 correct [1]）
        assert [2] in entry.wrong_options
        # ai 应保留
        assert entry.ai_analysis == "错题解析"

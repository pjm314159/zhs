"""测试 AI 解析传递流程的集成测试

验证从缓存获取 AI 解析 → 传递给 LLM → 加入 prompt 的完整流程。
"""

from pathlib import Path

from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.llm.prompts import build_choice_prompt, build_fill_blank_prompt
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption


class TestAIAnalysisCache:
    """测试 AI 解析缓存保存和获取"""

    def test_save_ai_analysis(self, tmp_path: Path) -> None:
        """测试保存 AI 解析到缓存"""
        cache = ZhidaoHomeworkCache(cache_dir=tmp_path)
        course_id = 123
        exam_id = "exam_001"
        question_key = "test_eid_123"
        ai_analysis = "正确答案是 A，因为..."

        cache.save_ai_analysis(course_id, exam_id, question_key, ai_analysis)

        # 验证能获取到
        entry = cache.get(course_id, exam_id, question_key)
        assert entry is not None
        assert entry.ai_analysis == ai_analysis

    def test_get_ai_analysis_from_cache(self, tmp_path: Path) -> None:
        """测试从缓存获取 AI 解析"""
        cache = ZhidaoHomeworkCache(cache_dir=tmp_path)
        course_id = 123
        exam_id = "exam_001"
        question_key = "test_eid_123"

        # 先保存一个带 AI 解析的 entry
        entry = HomeworkCacheEntry(
            questionType=1,
            options=[HomeworkCacheOption(id=1, content="A")],
            correct_options=[],
            wrong_options=[2],
            ai_analysis="这道题的正确答案是 A 选项，因为...",
            lastUpdated="2024-01-01T00:00:00",
        )
        cache.put(course_id, exam_id, question_key, entry)

        # 验证能获取到 AI 解析
        retrieved = cache.get(course_id, exam_id, question_key)
        assert retrieved is not None
        assert retrieved.ai_analysis == "这道题的正确答案是 A 选项，因为..."

    def test_ai_analysis_persisted(self, tmp_path: Path) -> None:
        """测试 AI 解析持久化到文件"""
        cache = ZhidaoHomeworkCache(cache_dir=tmp_path)
        course_id = 123
        exam_id = "exam_001"
        question_key = "test_eid_123"
        ai_analysis = "正确答案是 B，理由是..."

        cache.save_ai_analysis(course_id, exam_id, question_key, ai_analysis)

        # 重新加载缓存
        cache2 = ZhidaoHomeworkCache(cache_dir=tmp_path)
        entry = cache2.get(course_id, exam_id, question_key)
        assert entry is not None
        assert entry.ai_analysis == ai_analysis


class TestAIAnalysisInPrompt:
    """测试 AI 解析加入 Prompt"""

    def test_extra_unknown_keys_in_prompt(self) -> None:
        """测试 extra 中未识别的 key 加入 prompt"""
        question = "关于理想和信念的关系，下列叙述正确的是？"
        choices = [{"id": 1, "content": "A. 理想是信念的根据"}, {"id": 2, "content": "B. 信念是理想实现的重要保障"}]
        extra = {
            "courseName": "马克思主义基本原理",
            "排除选项": "以下选项已知是错误的，请勿选择: C, D",
            "历史AI解析": "之前 AI 对此题的分析（仅供参考）:\n正确答案是 A 和 B，因为理想和信念是相互依存的关系。",
        }

        prompt = build_choice_prompt(question, choices, "多选题", extra=extra)

        # 验证 prompt 包含历史 AI 解析
        assert "历史AI解析" in prompt
        assert "正确答案是 A 和 B" in prompt
        assert "排除选项" in prompt
        assert "C, D" in prompt

    def test_fill_blank_prompt_with_ai_analysis(self) -> None:
        """测试填空题 prompt 包含 AI 解析"""
        question = "理想是信念的____，信念是理想实现的____。"
        extra = {
            "courseName": "马克思主义基本原理",
            "历史AI解析": "这道题的答案是：根据、保障。理想和信念是辩证统一的关系。",
        }

        prompt = build_fill_blank_prompt(question, extra=extra)

        # 验证 prompt 包含历史 AI 解析
        assert "历史AI解析" in prompt
        assert "根据、保障" in prompt

    def test_extra_empty_value_not_included(self) -> None:
        """测试 extra 中空值不加入 prompt"""
        question = "测试题目"
        choices = [{"id": 1, "content": "A"}]
        extra: dict[str, str] = {
            "courseName": "测试课程",
        }
        # 空值和 None 值不加入 extra

        prompt = build_choice_prompt(question, choices, "单选题", extra=extra)

        # 验证只有 courseName 加入 prompt
        assert "测试课程" in prompt


class TestAIAnalysisFlow:
    """测试完整的 AI 解析传递流程"""

    def test_full_flow_simulation(self, tmp_path: Path) -> None:
        """模拟完整流程：保存 AI 解析 → 获取 → 传递给 prompt"""
        cache = ZhidaoHomeworkCache(cache_dir=tmp_path)
        course_id = 123
        exam_id = "exam_001"
        question_key = "test_eid_123"

        # 1. 保存 AI 解析（模拟 _save_ai_analysis_for_wrong）
        ai_analysis = (
            "这道题考察理想与信念的关系。正确答案是 A 和 B，因为理想是信念的根据和前提，信念是理想实现的重要保障。"
        )
        cache.save_ai_analysis(course_id, exam_id, question_key, ai_analysis)

        # 2. 获取 AI 解析（模拟 _generate_answer_with_source）
        entry = cache.get(course_id, exam_id, question_key)
        retrieved_analysis = entry.ai_analysis if entry else None
        assert retrieved_analysis == ai_analysis

        # 3. 构建 extra（模拟 _generate_answer_with_llm）
        extra = {"courseName": "马克思主义基本原理"}
        wrong_options = [3, 4]  # 模拟已知错误选项
        if wrong_options:
            extra["排除选项"] = "以下选项已知是错误的，请勿选择: C, D"
        if retrieved_analysis:
            extra["历史AI解析"] = f"之前 AI 对此题的分析（仅供参考）:\n{retrieved_analysis}"

        # 4. 构建 prompt（模拟 build_choice_prompt）
        question = "关于理想和信念的关系，下列叙述正确的是？"
        choices = [
            {"id": 1, "content": "A. 理想是信念的根据和前提"},
            {"id": 2, "content": "B. 信念是理想实现的重要保障"},
            {"id": 3, "content": "C. 理想是信念的延伸"},
            {"id": 4, "content": "D. 信念是理想的定向机制"},
        ]
        prompt = build_choice_prompt(question, choices, "多选题", extra=extra)

        # 5. 验证 prompt 包含所有信息
        assert "历史AI解析" in prompt
        assert "理想是信念的根据和前提" in prompt
        assert "排除选项" in prompt
        assert "C, D" in prompt
        assert "马克思主义基本原理" in prompt

        print(f"\n生成的 Prompt:\n{prompt}")

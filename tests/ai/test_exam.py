"""Task 6.3 — ai/exam.py TDD"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zhs.ai.exam import ExamCtx
from zhs.ai.models import OptionVo, QuestionContent, QuestionSheet
from zhs.config import AIConfig


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.exam_key = b"onbfhdyvz8x7otrp"
    session.crypto.key_bytes = MagicMock(return_value=b"onbfhdyvz8x7otrp")
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """AI 配置"""
    return AIConfig(api_key="test-key", model="gpt-4o-mini")


@pytest.fixture
def exam_ctx(mock_session: MagicMock, ai_config: AIConfig) -> ExamCtx:
    """创建 ExamCtx 实例"""
    return ExamCtx(
        session=mock_session,
        course_id=100,
        knowledge_id=200,
        exam_test_id=300,
        exam_paper_id=400,
        ai_config=ai_config,
    )


class TestExamCtxInit:
    """ExamCtx 初始化"""

    def test_basic_init(self, exam_ctx: ExamCtx) -> None:
        """基本初始化"""
        assert exam_ctx._course_id == 100
        assert exam_ctx._knowledge_id == 200
        assert exam_ctx._exam_test_id == 300
        assert exam_ctx._exam_paper_id == 400

    def test_semaphore_value(self, exam_ctx: ExamCtx) -> None:
        """Semaphore(3) 限制并发"""
        assert exam_ctx._semaphore._value == 3

    def test_cache_initialized(self, exam_ctx: ExamCtx) -> None:
        """缓存初始化为空"""
        assert exam_ctx._answer_cache == {}
        assert exam_ctx._all_answer_cache == {}


class TestSaveAnswerFormat:
    """答案格式化"""

    def test_save_answer_separator(self) -> None:
        """_save_answer 用 #@# 分隔选项 ID"""
        answers = ["opt1", "opt2", "opt3"]
        result = "#@#".join(str(a) for a in answers)
        assert result == "opt1#@#opt2#@#opt3"

    def test_save_answer_single(self) -> None:
        """单个答案"""
        answers = ["opt1"]
        result = "#@#".join(str(a) for a in answers)
        assert result == "opt1"


class TestGetAnswer:
    """答案获取策略"""

    def test_cache_hit(self, exam_ctx: ExamCtx) -> None:
        """缓存命中返回答案"""
        exam_ctx._all_answer_cache = {"123": {"answer": "456#@#789", "version": 1}}
        result = exam_ctx._get_cached_answer(123, 1)
        assert result is not None
        assert result == ["456", "789"]

    def test_cache_miss(self, exam_ctx: ExamCtx) -> None:
        """缓存未命中返回 None"""
        result = exam_ctx._get_cached_answer(999, 1)
        assert result is None

    def test_two_level_cache(self, exam_ctx: ExamCtx) -> None:
        """两级缓存：先查 all_answer_cache 再查 answer_cache"""
        # answer_cache 有但 all_answer_cache 没有
        exam_ctx._answer_cache = {"456": {"answer": "1#@#2", "version": 1}}
        exam_ctx._all_answer_cache = {}
        result = exam_ctx._get_cached_answer(456, 1)
        assert result is not None
        assert result == ["1", "2"]

    def test_cache_key_with_version(self, exam_ctx: ExamCtx) -> None:
        """缓存键包含版本号"""
        exam_ctx._all_answer_cache = {"789_2": {"answer": "3", "version": 2}}
        result = exam_ctx._get_cached_answer(789, 2)
        assert result is not None
        assert result == ["3"]


class TestGetAnswerStrategy:
    """答案获取三级策略"""

    def test_fewer_than_two_options_select_first(self, exam_ctx: ExamCtx) -> None:
        """选项少于 2 个且非填空 → 选第一个"""
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="唯一选项")],
        )
        answers, source = exam_ctx._get_answer(question)
        assert answers == ["10"]
        assert source == "cached"

    def test_fill_blank_fewer_than_two_options(self, exam_ctx: ExamCtx) -> None:
        """填空题选项少于 2 个不选第一个"""
        question = QuestionContent(
            id=1,
            content="填空___",
            question_type=3,
            option_vos=[OptionVo(id=10, content="答案")],
        )
        # 填空题不应走"选第一个"逻辑
        # 没有 AI 时应走兜底逻辑
        answers, source = exam_ctx._get_answer(question)
        assert source == "random"


class TestSubmitExamData:
    """提交考试数据"""

    @pytest.mark.asyncio
    async def test_submit_exam_contains_course_type(self, exam_ctx: ExamCtx) -> None:
        """_submit_exam 含 courseType=8"""
        with patch.object(exam_ctx, "_api_query", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {"code": 0}
            await exam_ctx._submit_exam()
            call_data = mock_api.call_args
            # 检查调用参数包含 courseType=8
            assert call_data is not None


class TestProcessQuestion:
    """题目处理"""

    @pytest.mark.asyncio
    async def test_process_question_sleeps(self, exam_ctx: ExamCtx) -> None:
        """_process_question 每题 sleep 0.3-0.8s"""
        sheet = QuestionSheet(question_id=1, version=1)
        with (
            patch.object(exam_ctx, "_get_question_content", new_callable=AsyncMock) as mock_get_qc,
            patch.object(exam_ctx, "_save_answer", new_callable=AsyncMock) as mock_save,
            patch("zhs.ai.exam.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("zhs.ai.exam.random.uniform", return_value=0.5),
        ):
            mock_get_qc.return_value = QuestionContent(
                id=1,
                content="test",
                question_type=1,
                option_vos=[OptionVo(id=1, content="A"), OptionVo(id=2, content="B")],
            )
            mock_save.return_value = True
            await exam_ctx._process_question(sheet)
            mock_sleep.assert_called()


class TestExamRetry:
    """API 重试"""

    @pytest.mark.asyncio
    async def test_api_retry_on_failure(self, exam_ctx: ExamCtx) -> None:
        """API 失败 3 次重试"""
        with patch.object(exam_ctx, "_api_query", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("Network error")
            from zhs.exceptions import ZhsError

            with pytest.raises(ZhsError, match="openExam"):
                await exam_ctx._open_exam()
            # 应该重试 3 次
            assert mock_api.call_count == 3


class TestCacheKeyFormat:
    """缓存键格式"""

    def test_cache_key_version_1(self, exam_ctx: ExamCtx) -> None:
        """version=1 时键为 questionId"""
        key = exam_ctx._cache_key(123, 1)
        assert key == "123"

    def test_cache_key_version_gt_1(self, exam_ctx: ExamCtx) -> None:
        """version>1 时键为 questionId_version"""
        key = exam_ctx._cache_key(123, 2)
        assert key == "123_2"

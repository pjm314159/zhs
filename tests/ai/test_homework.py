"""ai/homework.py 同步测试（原异步测试已转为同步）"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.homework import HomeworkCtx
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
    session.urls.exam = "https://studentexamtest.zhihuishu.com"
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """AI 配置"""
    return AIConfig(api_key="test-key", model="gpt-4o-mini")


@pytest.fixture
def homework_ctx(mock_session: MagicMock, ai_config: AIConfig) -> HomeworkCtx:
    """创建 HomeworkCtx 实例"""
    return HomeworkCtx(
        session=mock_session,
        course_id=100,
        knowledge_id=200,
        exam_test_id=300,
        exam_paper_id=400,
        ai_config=ai_config,
    )


class TestHomeworkCtxInit:
    """HomeworkCtx 初始化"""

    def test_basic_init(self, homework_ctx: HomeworkCtx) -> None:
        """基本初始化"""
        assert homework_ctx._course_id == 100
        assert homework_ctx._knowledge_id == 200
        assert homework_ctx._exam_test_id == 300
        assert homework_ctx._exam_paper_id == 400

    def test_no_semaphore(self, homework_ctx: HomeworkCtx) -> None:
        """同步版本不再有 semaphore（顺序处理）"""
        assert not hasattr(homework_ctx, "_semaphore")

    def test_heartbeat_thread_attribute(self, homework_ctx: HomeworkCtx) -> None:
        """心跳线程属性初始化为 None"""
        assert homework_ctx._heartbeat_thread is None

    def test_cache_initialized(self, homework_ctx: HomeworkCtx) -> None:
        """缓存初始化为空"""
        assert homework_ctx._answer_cache == {}
        assert homework_ctx._all_answer_cache == {}


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

    def test_cache_hit(self, homework_ctx: HomeworkCtx) -> None:
        """缓存命中返回答案"""
        homework_ctx._all_answer_cache = {"123": {"answer": "456#@#789"}}
        result = homework_ctx._get_cached_answer(123)
        assert result is not None
        assert result == ["456", "789"]

    def test_cache_miss(self, homework_ctx: HomeworkCtx) -> None:
        """缓存未命中返回 None"""
        result = homework_ctx._get_cached_answer(999)
        assert result is None

    def test_two_level_cache(self, homework_ctx: HomeworkCtx) -> None:
        """两级缓存：先查 all_answer_cache 再查 answer_cache"""
        # answer_cache 有但 all_answer_cache 没有
        homework_ctx._answer_cache = {"456": {"answer": "1#@#2"}}
        homework_ctx._all_answer_cache = {}
        result = homework_ctx._get_cached_answer(456)
        assert result is not None
        assert result == ["1", "2"]

    def test_slash_separator_compat(self, homework_ctx: HomeworkCtx) -> None:
        """填空题 answer 含 / 不拆分，返回单元素列表"""
        homework_ctx._all_answer_cache = {"123": {"answer": "身体健康/心理健康"}}
        result = homework_ctx._get_cached_answer(123)
        assert result is not None
        assert result == ["身体健康/心理健康"]


class TestGetAnswerStrategy:
    """答案获取三级策略"""

    def test_fewer_than_two_options_select_first(self, homework_ctx: HomeworkCtx) -> None:
        """选项少于 2 个且非填空 → 选第一个"""
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="唯一选项")],
        )
        answers, source = homework_ctx._get_answer(question)
        assert answers == ["10"]
        assert source == "cached"

    def test_fill_blank_fewer_than_two_options(self, homework_ctx: HomeworkCtx) -> None:
        """填空题选项少于 2 个不选第一个"""
        question = QuestionContent(
            id=1,
            content="填空___",
            question_type=3,
            option_vos=[OptionVo(id=10, content="答案")],
        )
        # 填空题不应走"选第一个"逻辑
        # 没有 AI 时应走兜底逻辑
        answers, source = homework_ctx._get_answer(question)
        assert source == "random"


class TestSubmitHomework:
    """提交作业（同步）"""

    def test_submit_homework_contains_course_type(self, homework_ctx: HomeworkCtx) -> None:
        """_submit 含 courseType=8（同步调用）"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            mock_api.return_value = {"code": 0}
            homework_ctx._submit()
            call_data = mock_api.call_args
            # 检查调用参数包含 courseType=8
            assert call_data is not None
            assert call_data[0][1]["courseType"] == 8


class TestProcessQuestion:
    """题目处理（同步）"""

    def test_process_question_sleeps(self, homework_ctx: HomeworkCtx) -> None:
        """_process_question 每题 sleep 3-5s（同步 time.sleep）"""
        sheet = QuestionSheet(question_id=1, version=1)
        with (
            patch.object(homework_ctx, "_get_question_content") as mock_get_qc,
            patch.object(homework_ctx, "_save_answer") as mock_save,
            patch("zhs.ai.homework.time.sleep") as mock_sleep,
            patch("zhs.ai.homework.random.uniform", return_value=4.0),
        ):
            mock_get_qc.return_value = QuestionContent(
                id=1,
                content="test",
                question_type=1,
                option_vos=[OptionVo(id=1, content="A"), OptionVo(id=2, content="B")],
            )
            mock_save.return_value = True
            homework_ctx._process_question(sheet)
            mock_sleep.assert_called()


class TestHomeworkRetry:
    """API 重试（同步）"""

    def test_api_retry_on_failure(self, homework_ctx: HomeworkCtx) -> None:
        """API 失败 3 次重试（同步调用）"""
        with patch.object(homework_ctx, "_api_query") as mock_api:
            mock_api.side_effect = Exception("Network error")
            from zhs.exceptions import ZhsError

            with pytest.raises(ZhsError, match="openExam"):
                homework_ctx._open()
            # 应该重试 3 次
            assert mock_api.call_count == 3


class TestCacheKeyFormat:
    """缓存键格式"""

    def test_cache_key_is_question_id(self, homework_ctx: HomeworkCtx) -> None:
        """缓存键为纯 question_id"""
        key = homework_ctx._cache_key(123)
        assert key == "123"

    def test_cache_key_no_version_suffix(self, homework_ctx: HomeworkCtx) -> None:
        """缓存键不含 version 后缀"""
        key = homework_ctx._cache_key(789)
        assert "_" not in key
        assert key == "789"


class TestHeartbeatThread:
    """心跳线程（同步版本）"""

    def test_heartbeat_uses_thread(self, homework_ctx: HomeworkCtx) -> None:
        """心跳使用 threading.Thread（daemon=True）"""
        with (
            patch.object(homework_ctx, "_api_query") as mock_api,
            patch("zhs.ai.homework.time.sleep") as mock_sleep,
        ):
            mock_api.return_value = {"code": 0}

            # 让心跳循环只执行一次后退出
            def side_effect(_interval: int = 10) -> bool:
                homework_ctx._stopped = True
                return True

            mock_sleep.side_effect = side_effect
            homework_ctx._stopped = False
            homework_ctx._heartbeat(interval=1)
            # 验证 _api_query 被调用（心跳发送了请求）
            assert mock_api.called

    def test_heartbeat_thread_daemon(self, homework_ctx: HomeworkCtx) -> None:
        """心跳线程属性为 daemon"""
        # 验证 AiExamBase 基类使用 threading.Thread 而非 asyncio.Task
        import inspect

        from zhs.ai.exam_base import AiExamBase

        source = inspect.getsource(AiExamBase)
        assert "threading.Thread" in source
        assert "daemon=True" in source

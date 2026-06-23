"""AiExamBase 契约测试

验证 AiExamBase 提供的公共方法行为，HomeworkCtx 和 ExamCtx 通过继承获得这些行为。
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.exam_base import AiExamBase
from zhs.ai.models import OptionVo, QuestionContent, QuestionSheet
from zhs.config import AIConfig


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.exam_key = b"onbfhdyvz8x7otrp"
    session.crypto.ai_key = b"hw2fdlwcj4cs1mx7"
    session.crypto.key_bytes = MagicMock(side_effect=lambda name: getattr(session.crypto, name))
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.exam = "https://studentexamtest.zhihuishu.com"
    return session


@pytest.fixture
def ai_config() -> AIConfig:
    """禁用 AI 的配置（避免初始化 LLM）"""
    return AIConfig(enabled=False)


class _ConcreteExamBase(AiExamBase):
    """用于测试的具体子类（实现所有抽象方法）"""

    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        return {}

    def _open(self) -> None:
        pass

    def _get_sheet_content(self) -> list[QuestionSheet]:
        return []

    def _get_question_content(self, question_id: int, version: int) -> QuestionContent | None:
        return None

    def _save_answer(self, question_id: int, answers: list[str]) -> bool:
        return True

    def _submit(self, submit: bool) -> None:
        pass

    def _answer_questions(self, sheets: list[QuestionSheet]) -> None:
        pass

    @property
    def _exam_base_url(self) -> str:
        return self._session.urls.exam


@pytest.fixture
def exam_base(mock_session: MagicMock, ai_config: AIConfig) -> AiExamBase:
    """创建 AiExamBase 实例（通过具体子类）"""
    return _ConcreteExamBase(
        session=mock_session,
        course_id=100,
        exam_test_id=300,
        exam_paper_id=400,
        ai_config=ai_config,
    )


class TestAiExamBaseInit:
    """AiExamBase 初始化"""

    def test_init_basic_fields(self, exam_base: AiExamBase) -> None:
        """基本字段初始化"""
        assert exam_base._course_id == 100
        assert exam_base._exam_test_id == 300
        assert exam_base._exam_paper_id == 400

    def test_init_cache_empty(self, exam_base: AiExamBase) -> None:
        """缓存初始化为空"""
        assert exam_base._answer_cache == {}
        assert exam_base._all_answer_cache == {}

    def test_init_stopped_false(self, exam_base: AiExamBase) -> None:
        """stopped 标志初始化为 False"""
        assert exam_base._stopped is False

    def test_init_heartbeat_thread_none(self, exam_base: AiExamBase) -> None:
        """心跳线程初始化为 None"""
        assert exam_base._heartbeat_thread is None

    def test_init_provider_none_when_disabled(self, exam_base: AiExamBase) -> None:
        """AI 禁用时 provider 为 None"""
        assert exam_base._provider is None

    def test_init_progress_fields(self, exam_base: AiExamBase) -> None:
        """进度字段初始化"""
        assert exam_base._progress_total == 0
        assert exam_base._progress_current == 0
        assert exam_base._progress_sources == []


class TestCacheKey:
    """缓存键生成"""

    def test_cache_key_is_question_id(self, exam_base: AiExamBase) -> None:
        """缓存键为纯 question_id"""
        assert exam_base._cache_key(123) == "123"

    def test_cache_key_no_version_suffix(self, exam_base: AiExamBase) -> None:
        """缓存键不含 version 后缀"""
        key = exam_base._cache_key(789)
        assert "_" not in key
        assert key == "789"


class TestParseCachedAnswer:
    """缓存答案解析"""

    def test_empty_returns_none(self, exam_base: AiExamBase) -> None:
        """空字符串返回 None"""
        assert exam_base._parse_cached_answer("") is None

    def test_with_separator_splits(self, exam_base: AiExamBase) -> None:
        """含 #@# 分隔符→拆分"""
        assert exam_base._parse_cached_answer("1#@#2#@#3") == ["1", "2", "3"]

    def test_without_separator_single_element(self, exam_base: AiExamBase) -> None:
        """不含 #@# → 单元素列表"""
        assert exam_base._parse_cached_answer("答案") == ["答案"]

    def test_slash_not_split(self, exam_base: AiExamBase) -> None:
        """填空题 answer 含 / 不拆分"""
        result = exam_base._parse_cached_answer("身体健康/心理健康")
        assert result == ["身体健康/心理健康"]


class TestGetCachedAnswer:
    """两级缓存查询"""

    def test_cache_hit_all_answer_cache(self, exam_base: AiExamBase) -> None:
        """all_answer_cache 命中"""
        exam_base._all_answer_cache = {"123": {"answer": "456#@#789"}}
        assert exam_base._get_cached_answer(123) == ["456", "789"]

    def test_cache_hit_answer_cache(self, exam_base: AiExamBase) -> None:
        """answer_cache 命中（all_answer_cache 未命中）"""
        exam_base._answer_cache = {"456": {"answer": "1"}}
        exam_base._all_answer_cache = {}
        assert exam_base._get_cached_answer(456) == ["1"]

    def test_cache_miss(self, exam_base: AiExamBase) -> None:
        """缓存未命中返回 None"""
        assert exam_base._get_cached_answer(999) is None

    def test_all_answer_cache_priority(self, exam_base: AiExamBase) -> None:
        """all_answer_cache 优先于 answer_cache"""
        exam_base._all_answer_cache = {"123": {"answer": "from_all"}}
        exam_base._answer_cache = {"123": {"answer": "from_current"}}
        # 应返回 all_answer_cache 的值
        assert exam_base._get_cached_answer(123) == ["from_all"]


class TestSetCachedAnswer:
    """设置缓存"""

    def test_set_writes_both_caches(self, exam_base: AiExamBase) -> None:
        """设置缓存同时写入两级缓存"""
        exam_base._set_cached_answer(
            123,
            {
                "question": "题目",
                "answer": "456",
                "answer_content": "选项A",
                "questionDict": {"id": 123},
            },
        )
        assert "123" in exam_base._answer_cache
        assert "123" in exam_base._all_answer_cache
        assert exam_base._answer_cache["123"]["answer"] == "456"
        assert exam_base._all_answer_cache["123"]["answer"] == "456"

    def test_set_preserves_fields(self, exam_base: AiExamBase) -> None:
        """设置缓存保留所有字段"""
        exam_base._set_cached_answer(
            1,
            {
                "question": "Q1",
                "answer": "A1",
                "answer_content": "C1",
                "questionDict": {"k": "v"},
            },
        )
        entry = exam_base._answer_cache["1"]
        assert entry["question"] == "Q1"
        assert entry["answer"] == "A1"
        assert entry["answer_content"] == "C1"
        assert entry["questionDict"] == {"k": "v"}


class TestGetAnswerStrategy:
    """三级答案策略：缓存 → AI → 随机"""

    def test_fewer_than_two_options_select_first(self, exam_base: AiExamBase) -> None:
        """选项少于 2 个且非填空 → 选第一个"""
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="唯一选项")],
        )
        answers, source = exam_base._get_answer(question)
        assert answers == ["10"]
        assert source == "cached"

    def test_fill_blank_fewer_than_two_options(self, exam_base: AiExamBase) -> None:
        """填空题选项少于 2 个不选第一个"""
        question = QuestionContent(
            id=1,
            content="填空___",
            question_type=3,
            option_vos=[OptionVo(id=10, content="答案")],
        )
        answers, source = exam_base._get_answer(question)
        assert source == "random"

    def test_cache_hit_returns_cached(self, exam_base: AiExamBase) -> None:
        """缓存命中返回缓存答案"""
        exam_base._all_answer_cache = {"1": {"answer": "10"}}
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="A"), OptionVo(id=11, content="B")],
        )
        answers, source = exam_base._get_answer(question)
        assert answers == ["10"]
        assert source == "cached"

    def test_random_fallback_single_choice(self, exam_base: AiExamBase) -> None:
        """无 AI 时单选题走随机兜底"""
        question = QuestionContent(
            id=1,
            content="test",
            question_type=1,
            option_vos=[OptionVo(id=10, content="A"), OptionVo(id=11, content="B")],
        )
        with patch("zhs.ai.exam_base.random.choice", return_value={"id": 11}):
            answers, source = exam_base._get_answer(question)
        assert answers == ["11"]
        assert source == "random"

    def test_random_fallback_fill_blank(self, exam_base: AiExamBase) -> None:
        """无 AI 时填空题走随机兜底返回'未知'"""
        question = QuestionContent(
            id=1,
            content="填空___",
            question_type=3,
            option_vos=[],
        )
        answers, source = exam_base._get_answer(question)
        assert answers == ["未知"]
        assert source == "random"

    def test_random_fallback_judgement(self, exam_base: AiExamBase) -> None:
        """无 AI 时判断题走随机兜底"""
        question = QuestionContent(
            id=1,
            content="判断题",
            question_type=14,
            option_vos=[OptionVo(id=10, content="对"), OptionVo(id=11, content="错")],
        )
        with patch("zhs.ai.exam_base.random.choice", return_value={"id": 10}):
            answers, source = exam_base._get_answer(question)
        assert answers == ["10"]
        assert source == "random"

    def test_random_fallback_multiple_choice(self, exam_base: AiExamBase) -> None:
        """无 AI 时多选题走随机兜底"""
        question = QuestionContent(
            id=1,
            content="多选",
            question_type=2,
            option_vos=[
                OptionVo(id=10, content="A"),
                OptionVo(id=11, content="B"),
                OptionVo(id=12, content="C"),
            ],
        )
        with (
            patch("zhs.ai.exam_base.random.sample", return_value=[{"id": 10}, {"id": 11}]),
            patch("zhs.ai.exam_base.random.choice", return_value={"id": 10}),
        ):
            answers, source = exam_base._get_answer(question)
        assert set(answers) == {"10", "11"}
        assert source == "random"


class TestCheckResults:
    """结果检查与缓存更新"""

    def test_check_results_correct_count(self, exam_base: AiExamBase) -> None:
        """正确统计答对题数"""
        sheets = [QuestionSheet(question_id=1, version=1), QuestionSheet(question_id=2, version=1)]
        questions = {
            1: QuestionContent(
                id=1,
                content="Q1",
                question_type=1,
                option_vos=[OptionVo(id=10, content="A", is_correct=1)],
                user_answer_vos=[],
            ),
            2: QuestionContent(
                id=2,
                content="Q2",
                question_type=1,
                option_vos=[OptionVo(id=20, content="B", is_correct=1)],
                user_answer_vos=[],
            ),
        }

        def mock_get_qc(qid: int, version: int) -> QuestionContent | None:
            return questions.get(qid)

        with (
            patch.object(exam_base, "_get_question_content", side_effect=mock_get_qc),
            patch.object(exam_base, "_save_cache"),
        ):
            correct, total = exam_base._check_results(sheets)
        assert total == 2
        assert correct == 0  # user_answer_vos 为空，is_correct=False

    def test_check_results_updates_cache(self, exam_base: AiExamBase) -> None:
        """检查结果时更新缓存"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        question = QuestionContent(
            id=1,
            content="Q1",
            question_type=1,
            option_vos=[OptionVo(id=10, content="A", is_correct=1)],
            user_answer_vos=[],
        )
        with (
            patch.object(exam_base, "_get_question_content", return_value=question),
            patch.object(exam_base, "_save_cache"),
        ):
            exam_base._check_results(sheets)
        assert "1" in exam_base._answer_cache
        assert exam_base._answer_cache["1"]["answer"] == "10"

    def test_check_results_fill_blank_with_options(self, exam_base: AiExamBase) -> None:
        """填空题检查结果用 / 合并"""
        sheets = [QuestionSheet(question_id=1, version=1)]
        question = QuestionContent(
            id=1,
            content="填空",
            question_type=3,
            option_vos=[
                OptionVo(id=10, content="答案1", is_correct=1),
                OptionVo(id=11, content="答案2", is_correct=1),
            ],
            user_answer_vos=[],
        )
        with (
            patch.object(exam_base, "_get_question_content", return_value=question),
            patch.object(exam_base, "_save_cache"),
        ):
            exam_base._check_results(sheets)
        assert exam_base._answer_cache["1"]["answer"] == "答案1/答案2"


class TestHeartbeat:
    """心跳（基类默认实现）"""

    def test_heartbeat_loop_exits_on_stopped(self, exam_base: AiExamBase) -> None:
        """stopped=True 时心跳循环退出"""
        exam_base._stopped = True
        with patch.object(exam_base, "_api_query") as mock_api:
            exam_base._heartbeat(interval=1)
            mock_api.assert_not_called()

    def test_heartbeat_calls_api(self, exam_base: AiExamBase) -> None:
        """心跳调用 API"""
        with (
            patch.object(exam_base, "_api_query") as mock_api,
            patch("zhs.ai.exam_base.time.sleep") as mock_sleep,
        ):
            mock_api.return_value = {"code": 0}

            def stop_loop(_interval: int) -> bool:
                exam_base._stopped = True
                return True

            mock_sleep.side_effect = stop_loop
            exam_base._stopped = False
            exam_base._heartbeat(interval=1)
            assert mock_api.called


class TestUpdateProgress:
    """进度更新"""

    def test_update_progress_no_error(self, exam_base: AiExamBase) -> None:
        """进度更新不抛异常"""
        exam_base._progress_total = 5
        exam_base._progress_current = 2
        exam_base._progress_sources = ["cached", "AI generated"]
        # 不抛异常即可
        exam_base._update_progress("cached")

    def test_update_progress_pending_state(self, exam_base: AiExamBase) -> None:
        """pending 状态显示总题数"""
        exam_base._progress_total = 10
        exam_base._progress_current = 0
        exam_base._update_progress("pending")
        # 不抛异常即可


class TestAbstractMethods:
    """抽象方法验证"""

    def test_cannot_instantiate_abstract(self) -> None:
        """不能直接实例化抽象类"""
        with pytest.raises(TypeError):
            AiExamBase(  # type: ignore[abstract]
                session=MagicMock(),
                course_id=1,
                exam_test_id=2,
                exam_paper_id=3,
                ai_config=AIConfig(enabled=False),
            )

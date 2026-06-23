"""AI 作业/考试基类（模板方法模式）

封装 HomeworkCtx 与 ExamCtx 的公共流程与状态：
- LLM 提供者初始化（通过 LLMProviderFactory）
- 两级缓存（_answer_cache / _all_answer_cache），持久化通过 AiExamCache
- 三级答案策略（缓存 → AI → 随机）
- 心跳（daemon 线程）
- 进度条更新
- 结果检查与缓存更新

子类只需实现差异化的抽象方法（_open / _get_sheet_content / _save_answer 等）。
"""

import contextlib
import random
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.cache.ai_cache import AiExamCache
from zhs.config import AIConfig
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.llm.factory import LLMProviderFactory
from zhs.reporter import ConsoleReporter, ProgressReporter
from zhs.session import ZhsSession
from zhs.utils.display import _C, progress_bar, styled


class AiExamBase(ABC):
    """AI 作业/考试基类（模板方法模式）

    子类 HomeworkCtx（逐题保存）与 ExamCtx（批量保存）共享此基类。
    """

    def __init__(
        self,
        session: ZhsSession,
        course_id: int | str,
        exam_test_id: int | str,
        exam_paper_id: int | str,
        ai_config: AIConfig,
        op_extra: dict[str, Any] | None = None,
        progress_view: bool = True,
        reporter: ProgressReporter | None = None,
        cache: AiExamCache | None = None,
    ) -> None:
        self._session = session
        self._course_id = course_id
        self._exam_test_id = exam_test_id
        self._exam_paper_id = exam_paper_id
        self._ai_config = ai_config
        self._op_extra = op_extra or {}
        self._progress_view = progress_view
        self._reporter = reporter or ConsoleReporter()
        self._cache = cache or AiExamCache()

        # 缓存（内存中的两级缓存，持久化通过 self._cache）
        self._answer_cache: dict[str, dict[str, Any]] = {}
        self._all_answer_cache: dict[str, dict[str, Any]] = {}

        # 状态
        self._sheet_content: list[QuestionSheet] | None = None
        self._stopped = False
        self._heartbeat_thread: threading.Thread | None = None
        self._reference_materials: list[dict[str, str]] = []

        # 进度
        self._progress_total = 0
        self._progress_current = 0
        self._progress_sources: list[str] = []

        # LLM 提供者（统一通过工厂创建）
        self._provider: LLMProvider | None = LLMProviderFactory.create(
            ai_config,
            session=session,
            course_id=str(course_id),
            course_name=str(self._op_extra.get("courseName", "")) if self._op_extra else "",
        )

    # --- 模板方法 ---

    def start(
        self,
        reference_materials: list[dict[str, str]] | None = None,
        submit: bool = False,
    ) -> tuple[bool, int, int]:
        """执行完整流程，返回 (是否全对, 正确数, 总题数)

        Args:
            reference_materials: 参考资料（PPT 等）
            submit: 是否提交（子类决定是否使用）
        """
        self._reference_materials = reference_materials or []

        self._load_cache()
        self._open()

        # 启动心跳（daemon 线程）
        self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

        sheets = self._get_sheet_content()
        if not sheets:
            self._stopped = True
            raise ZhsError("答题卡内容为空")

        # 答题
        total = len(sheets)
        self._progress_total = total
        self._progress_current = 0
        self._progress_sources = []
        self._update_progress("pending")
        self._answer_questions(sheets)

        self._reporter.wipe_line()

        # 提交与结果检查（子类决定具体行为）
        result = self._finish(submit, sheets)
        self._stopped = True
        return result

    def _finish(self, submit: bool, sheets: list[QuestionSheet]) -> tuple[bool, int, int]:
        """结束流程（提交 + 结果检查）。默认实现：不提交，返回 (False, 0, total)。

        子类可重写以实现提交逻辑。
        """
        return False, 0, len(sheets)

    # --- 公共实现（子类一般不重写）---

    @property
    @abstractmethod
    def _exam_base_url(self) -> str:
        """考试 API 基础 URL"""
        ...

    @abstractmethod
    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """同步 API 查询（子类决定使用哪个 session 方法）"""
        ...

    @abstractmethod
    def _open(self) -> None:
        """打开作业/考试"""
        ...

    @abstractmethod
    def _get_sheet_content(self) -> list[QuestionSheet]:
        """获取答题卡内容"""
        ...

    @abstractmethod
    def _get_question_content(self, question_id: int, version: int) -> QuestionContent | None:
        """获取题目详情"""
        ...

    @abstractmethod
    def _save_answer(self, question_id: int, answers: list[str]) -> bool:
        """保存单题答案"""
        ...

    @abstractmethod
    def _submit(self, submit: bool) -> None:
        """提交"""
        ...

    @abstractmethod
    def _answer_questions(self, sheets: list[QuestionSheet]) -> None:
        """答题流程（子类决定逐题或批量）"""
        ...

    # --- 缓存键 ---

    @staticmethod
    def _cache_key(question_id: int) -> str:
        """生成缓存键（仅用 question_id，不含 version）"""
        return str(question_id)

    # --- 缓存查询 ---

    def _get_cached_answer(self, question_id: int) -> list[str] | None:
        """从两级缓存获取答案（all_answer_cache 优先）"""
        key = self._cache_key(question_id)
        for cache in (self._all_answer_cache, self._answer_cache):
            entry = cache.get(key)
            if entry is not None:
                return self._parse_cached_answer(entry.get("answer", ""))
        return None

    @staticmethod
    def _parse_cached_answer(answer_str: str) -> list[str] | None:
        """解析缓存中的 answer 字段（委托给 AiExamCache.parse_answer）

        - 含 #@# → 按 #@# 分隔（多选题选项 ID）
        - 不含 #@# → 返回单元素列表（单选/判断/填空题）
        填空题多个空用 / 合并存储，不拆分。
        """
        return AiExamCache.parse_answer(answer_str)

    def _set_cached_answer(self, question_id: int, data: dict[str, Any]) -> None:
        """设置缓存（同时写入两级缓存）"""
        key = self._cache_key(question_id)
        cache_entry = {
            "question": data.get("question", ""),
            "answer": data.get("answer", ""),
            "answer_content": data.get("answer_content", ""),
            "questionDict": data.get("questionDict", {}),
        }
        self._answer_cache[key] = cache_entry
        self._all_answer_cache[key] = cache_entry

    # --- 三级答案策略 ---

    def _get_answer(self, question: QuestionContent) -> tuple[list[str], str]:
        """获取答案，返回 (答案列表, 来源标记)

        三级策略：1. 缓存命中 2. AI 生成 3. 兜底随机
        """
        question_id = question.id
        question_type = question.question_type

        # 1. 查缓存
        cached = self._get_cached_answer(question_id)
        if cached is not None:
            return cached, "cached"

        # 选项
        choices = [{"id": opt.id, "content": opt.content} for opt in question.option_vos]

        # 选项少于 2 个且非填空 → 选第一个
        if len(choices) < 2 and question_type != 3:
            return [str(choices[0]["id"])], "cached"

        # 2. AI 生成
        if self._provider is not None:
            try:
                if question_type == 1:
                    ids = self._provider.single_choice(
                        question.content, choices, self._reference_materials, self._op_extra
                    )
                    if ids:
                        return [str(i) for i in ids], "AI generated"
                    logger.warning(f"{question.content} {question_id} AI provide empty")
                elif question_type == 2:
                    ids = self._provider.multiple_choice(
                        question.content, choices, self._reference_materials, self._op_extra
                    )
                    if ids:
                        return [str(i) for i in ids], "AI generated"
                elif question_type == 14:
                    ids = self._provider.judgement(question.content, choices, self._reference_materials, self._op_extra)
                    if ids:
                        return [str(i) for i in ids], "AI generated"
                elif question_type == 3:
                    answers = self._provider.fill_blank(question.content, self._reference_materials, self._op_extra)
                    if answers:
                        return answers, "AI generated"
            except Exception as e:
                logger.error(f"AI 生成答案失败: {e}")

        # 3. 兜底随机
        if question_type == 3:
            return ["未知"], "random"
        elif question_type == 1 and choices:
            return [str(random.choice(choices)["id"])], "random"
        elif question_type == 2 and choices:
            n = min(2, len(choices))
            selected = random.sample(choices, n)
            return [str(c["id"]) for c in selected], "random"
        elif question_type == 14 and choices:
            return [str(random.choice(choices)["id"])], "random"
        return [], "random"

    # --- 进度条 ---

    def _update_progress(self, source: str) -> None:
        """更新控制台底部进度条"""
        current = self._progress_current
        total = self._progress_total

        # 来源统计
        cache_count = self._progress_sources.count("cached")
        ai_count = sum(1 for s in self._progress_sources if s == "AI generated")
        random_count = sum(1 for s in self._progress_sources if s == "random")

        # 来源标签
        source_parts: list[str] = []
        if cache_count:
            source_parts.append(styled(f"cache:{cache_count}", _C.CYAN))
        if ai_count:
            source_parts.append(styled(f"AI:{ai_count}", _C.BRIGHT_MAGENTA))
        if random_count:
            source_parts.append(styled(f"random:{random_count}", _C.YELLOW))
        source_str = " ".join(source_parts) if source_parts else ""

        # 当前题来源
        if source == "cached":
            cur_tag = styled("[cache]", _C.CYAN)
        elif source == "AI generated":
            cur_tag = styled("[AI]", _C.BRIGHT_MAGENTA)
        elif source == "random":
            cur_tag = styled("[random]", _C.YELLOW)
        elif source == "error":
            cur_tag = styled("[error]", _C.RED)
        else:
            cur_tag = styled(f"{total}题", _C.DIM)

        bar = progress_bar(current, total)
        line = f"  {bar} {cur_tag} {source_str}"
        with contextlib.suppress(Exception):
            self._reporter.progress(line)

    # --- 心跳 ---

    def _heartbeat(self, interval: int = 10) -> None:
        """同步心跳（daemon 线程），定期更新用时

        默认实现：循环调用 _heartbeat_once，间隔 interval 秒。
        子类可重写 _heartbeat_once 实现具体心跳逻辑。
        """
        while not self._stopped:
            try:
                self._heartbeat_once(interval)
            except Exception as e:
                logger.error(f"心跳失败: {e}")
            time.sleep(interval)

    def _heartbeat_once(self, interval: int = 10) -> None:
        """单次心跳（默认实现：调用 updateUserUsedTime）

        子类可重写以自定义心跳逻辑。
        """
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/updateUserUsedTime"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "heartbeatTime": interval,
        }
        self._api_query(url, data)

    # --- 结果检查 ---

    def _check_results(self, sheets: list[QuestionSheet]) -> tuple[int, int]:
        """检查结果并更新缓存，返回 (正确数, 总题数)"""
        correct_count = 0
        total_count = len(sheets)

        for sheet in sheets:
            question = self._get_question_content(sheet.question_id, sheet.version)
            if question is None:
                continue

            # 检查用户是否答对
            user_answers = question.user_answer_vos
            is_correct = bool(user_answers) and user_answers[0].is_correct == 1
            if is_correct:
                correct_count += 1

            # 获取正确选项（用于缓存更新）
            correct_opts = [opt for opt in question.option_vos if opt.is_correct == 1]

            # 更新缓存
            if question.question_type == 3:
                # 填空题：多个空用 / 合并存储
                if correct_opts:
                    answer_str = "/".join(opt.content for opt in correct_opts)
                    answer_content_str = "\n".join(opt.content for opt in correct_opts)
                elif user_answers:
                    correct_answers = [a.answer for a in user_answers if a.is_correct == 1]
                    answer_str = "/".join(correct_answers)
                    answer_content_str = "\n".join(correct_answers)
                else:
                    answer_str = ""
                    answer_content_str = ""
            else:
                answer_str = "#@#".join(str(opt.id) for opt in correct_opts)
                answer_content_str = "\n".join(opt.content for opt in correct_opts)

            self._set_cached_answer(
                sheet.question_id,
                {
                    "question": question.content,
                    "answer": answer_str,
                    "answer_content": answer_content_str,
                    "questionDict": question.model_dump(),
                },
            )

        self._save_cache()
        return correct_count, total_count

    # --- 缓存持久化（通过 AiExamCache）---

    def _load_cache(self) -> None:
        """加载缓存（通过 AiExamCache 读取新格式）

        - _all_answer_cache: 合并课程下所有 exam 的缓存
        - _answer_cache: 当前 exam 的缓存
        """
        # 加载课程下所有 exam 的缓存（合并）
        self._all_answer_cache = dict(self._cache.load_all_for_course(self._course_id))

        # 加载当前 exam 的缓存
        self._answer_cache = {}
        exam_entries = self._cache._load_exam(self._course_id, self._exam_test_id)
        for key, value in exam_entries.items():
            if isinstance(value, dict):
                self._answer_cache[key] = value

    def _save_cache(self) -> None:
        """保存缓存（通过 AiExamCache 写入新格式）

        仅保存当前 exam 的缓存到 {course_id}/{exam_id}.json。
        _all_answer_cache 在 _set_cached_answer 时同步更新，无需单独持久化。
        """
        for question_id_str, entry in self._answer_cache.items():
            try:
                question_id = int(question_id_str)
                self._cache.put(self._course_id, self._exam_test_id, question_id, entry)
            except (ValueError, TypeError) as e:
                logger.error(f"保存缓存失败 question_id={question_id_str}: {e}")

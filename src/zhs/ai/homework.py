"""AI 作业上下文（异步执行）

使用 LLM 提供者自动答题，支持两级缓存、并发控制和心跳。
AI 课程的"考试"实际上是作业，统一命名为 homework。
"""

import asyncio
import json
import random
from typing import Any

from loguru import logger

from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.config import AIConfig
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.llm.openai import OpenAIProvider
from zhs.llm.zhidao import ZhidaoAIProvider
from zhs.session import ZhsSession
from zhs.utils.path import get_data_dir


class HomeworkCtx:
    """AI 作业上下文（异步执行）

    使用 LLM 提供者自动答题，支持两级缓存、并发控制和心跳。
    """

    _semaphore: asyncio.Semaphore = asyncio.Semaphore(3)

    def __init__(
        self,
        session: ZhsSession,
        course_id: int,
        knowledge_id: int,
        exam_test_id: int,
        exam_paper_id: int,
        ai_config: AIConfig,
        op_extra: dict[str, Any] | None = None,
        progress_view: bool = True,
    ) -> None:
        self._session = session
        self._course_id = course_id
        self._knowledge_id = knowledge_id
        self._exam_test_id = exam_test_id
        self._exam_paper_id = exam_paper_id
        self._ai_config = ai_config
        self._op_extra = op_extra or {}
        self._progress_view = progress_view

        self._answer_cache: dict[str, dict[str, Any]] = {}
        self._all_answer_cache: dict[str, dict[str, Any]] = {}
        self._sheet_content: list[QuestionSheet] | None = None
        self._stopped = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reference_materials: list[dict[str, str]] = []

        # 初始化 LLM 提供者
        self._provider: LLMProvider | None = None
        if not ai_config.enabled:
            self._provider = None
        elif ai_config.use_zhidao_ai:
            self._provider = ZhidaoAIProvider(session)
        elif ai_config.api_key:
            self._provider = OpenAIProvider(
                api_key=ai_config.api_key,
                base_url=ai_config.base_url,
                model_name=ai_config.model,
            )

    async def start(self, reference_materials: list[dict[str, str]] | None = None) -> tuple[bool, int, int]:
        """执行完整作业流程，返回 (是否全对, 正确数, 总题数)"""
        self._reference_materials = reference_materials or []

        # 加载缓存
        self._load_cache()

        # 打开作业
        await self._open_homework()

        # 启动心跳
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

        # 获取试卷内容
        sheets = await self._get_sheet_content()
        if not sheets:
            self._stopped = True
            raise ZhsError("试卷内容为空")

        # 并发答题
        tasks = [self._process_question(sheet) for sheet in sheets]
        await asyncio.gather(*tasks)

        # 提交作业
        await self._submit_homework()

        # 检查结果并更新缓存
        correct_count, total_count = await self._check_results(sheets)

        # 取消心跳
        self._stopped = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        return correct_count == total_count, correct_count, total_count

    # --- 作业 API ---

    @property
    def _homework_base_url(self) -> str:
        """作业 API 基础 URL"""
        return self._session.urls.exam

    async def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """异步作业 API 查询"""
        return await self._session.ai_exam_query(url, data, method=method)

    async def _open_homework(self, _retries: int = 0) -> None:
        """打开作业"""
        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/openExam"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "courseId": self._course_id,
        }
        try:
            await self._api_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"openExam 失败，重试 {_retries + 1}/3")
                await self._open_homework(_retries + 1)
            else:
                raise ZhsError("openExam 失败，已重试 3 次") from e

    async def _get_sheet_content(self, _retries: int = 0) -> list[QuestionSheet]:
        """获取试卷内容"""
        if self._sheet_content is not None:
            return self._sheet_content

        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/getExamSheetInfo"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
        }
        try:
            result = await self._api_query(url, data, method="GET")
            raw_sheets = result["data"]["partSheetVos"][0]["questionSheetVos"]
            self._sheet_content = [QuestionSheet.model_validate(s) for s in raw_sheets]
        except Exception as e:
            if _retries < 2:
                logger.error(f"getSheetContent 失败，重试 {_retries + 1}/3")
                return await self._get_sheet_content(_retries + 1)
            else:
                raise ZhsError("getSheetContent 失败，已重试 3 次") from e

        return self._sheet_content

    async def _get_question_content(self, question_id: int, version: int, _retries: int = 0) -> QuestionContent | None:
        """获取题目内容"""
        url = f"{self._homework_base_url}/gateway/t/v1/question/getExamQuestionInfo"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "questionId": question_id,
            "version": version,
        }
        try:
            result = await self._api_query(url, data, method="GET")
            return QuestionContent.model_validate(result["data"])
        except Exception as e:
            if _retries < 2:
                logger.error(f"getQuestionContent 失败，重试 {_retries + 1}/3")
                return await self._get_question_content(question_id, version, _retries + 1)
            else:
                logger.error(f"getQuestionContent 失败，已重试 3 次: {e}")
                return None

    async def _save_answer(self, question_id: int, answers: list[str]) -> bool:
        """保存答案"""
        if not answers:
            return False
        url = f"{self._homework_base_url}/gateway/t/v1/answer/saveAnswer"
        data = {
            "recruitId": self._course_id,
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "questionId": question_id,
            "dataVos": None,
            "answer": "#@#".join(str(a) for a in answers),
        }
        try:
            await self._api_query(url, data)
            return True
        except Exception as e:
            logger.error(f"saveAnswer 失败: {e}")
            return False

    async def _submit_homework(self, _retries: int = 0) -> None:
        """提交作业"""
        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/submit"
        data = {
            "examTestId": self._exam_test_id,
            "courseId": self._course_id,
            "courseType": 8,
            "examPaperId": self._exam_paper_id,
            "aiKnlowledgeId": self._knowledge_id,
        }
        try:
            await self._api_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"submitExam 失败，重试 {_retries + 1}/3")
                await self._submit_homework(_retries + 1)
            else:
                raise ZhsError("submitExam 失败，已重试 3 次") from e
        finally:
            self._stopped = True

    # --- 心跳 ---

    async def _heartbeat(self, interval: int = 10) -> None:
        """异步心跳，定期更新作业用时"""
        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/updateUserUsedTime"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "heartbeatTime": interval,
        }
        while not self._stopped:
            try:
                await self._api_query(url, data)
            except Exception as e:
                logger.error(f"心跳失败: {e}")
            await asyncio.sleep(interval)

    # --- 答题 ---

    def _cache_key(self, question_id: int, version: int) -> str:
        """生成缓存键"""
        return str(question_id) if version == 1 else f"{question_id}_{version}"

    def _get_cached_answer(self, question_id: int, version: int) -> list[str] | None:
        """从缓存获取答案（两级缓存）"""
        key = self._cache_key(question_id, version)
        # 先查 all_answer_cache
        cached = self._all_answer_cache.get(key)
        if cached is not None:
            answer_str = cached.get("answer", "")
            return answer_str.split("#@#") if answer_str else None
        # 再查 answer_cache
        cached = self._answer_cache.get(key)
        if cached is not None:
            answer_str = cached.get("answer", "")
            return answer_str.split("#@#") if answer_str else None
        return None

    def _set_cached_answer(self, question_id: int, version: int, data: dict[str, Any]) -> None:
        """设置缓存"""
        key = self._cache_key(question_id, version)
        cache_entry = {
            "version": version,
            "question": data.get("question", ""),
            "answer": data.get("answer", ""),
            "answer_content": data.get("answer_content", ""),
            "questionDict": data.get("questionDict", {}),
        }
        self._answer_cache[key] = cache_entry
        self._all_answer_cache[key] = cache_entry

    def _get_answer(self, question: QuestionContent) -> tuple[list[str], str]:
        """获取答案，返回 (答案列表, 来源标记)

        三级策略：1. 缓存命中 2. AI 生成 3. 兜底随机
        """
        question_id = question.id
        question_type = question.question_type
        version = question.version

        # 1. 查缓存
        cached = self._get_cached_answer(question_id, version)
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

    async def _process_question(self, sheet: QuestionSheet) -> None:
        """处理单道题目（含并发控制和延迟）"""
        async with self._semaphore:
            await asyncio.sleep(random.uniform(3, 5))

            question = await self._get_question_content(sheet.question_id, sheet.version)
            if question is None:
                logger.error(f"获取题目失败: {sheet.question_id}")
                return

            answers, source = self._get_answer(question)
            if answers:
                await self._save_answer(sheet.question_id, answers)

            if self._progress_view:
                logger.info(f"题目 {sheet.question_id}: {source}")

    # --- 缓存 ---

    def _load_cache(self) -> None:
        """加载缓存（扫描同课程目录下所有 JSON 文件）"""
        cache_dir = get_data_dir() / "aiexamAnswer" / str(self._course_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 扫描目录下所有 JSON 文件（排除 data.json），合并为 all_answer_cache
        merged: dict[str, dict[str, Any]] = {}
        for json_file in cache_dir.glob("*.json"):
            if json_file.name == "data.json":
                continue
            try:
                with open(json_file, encoding="utf-8") as f:
                    cache = json.load(f)
                    if isinstance(cache, dict):
                        merged.update(cache)
            except (json.JSONDecodeError, OSError):
                pass

        # 处理版本号
        self._all_answer_cache = {}
        for key, value in merged.items():
            if not isinstance(value, dict):
                continue
            if "_" not in key:
                value.setdefault("version", 1)
            self._all_answer_cache[key] = value

        # 加载 data.json（如果存在，优先使用）
        all_path = cache_dir / "data.json"
        if all_path.exists():
            try:
                with open(all_path, encoding="utf-8") as f:
                    data_cache = json.load(f)
                    if isinstance(data_cache, dict):
                        self._all_answer_cache.update(data_cache)
            except (json.JSONDecodeError, OSError):
                pass

        # 加载 answer_cache（当前作业）
        exam_path = cache_dir / f"{self._exam_test_id}.json"
        if exam_path.exists():
            try:
                with open(exam_path, encoding="utf-8") as f:
                    exam_cache = json.load(f)
                    if isinstance(exam_cache, dict):
                        self._answer_cache = exam_cache
            except (json.JSONDecodeError, OSError):
                self._answer_cache = {}

    def _save_cache(self) -> None:
        """保存缓存"""
        cache_dir = get_data_dir() / "aiexamAnswer" / str(self._course_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        exam_path = cache_dir / f"{self._exam_test_id}.json"
        with open(exam_path, "w", encoding="utf-8") as f:
            json.dump(self._answer_cache, f, ensure_ascii=False, indent=4)

        all_path = cache_dir / "data.json"
        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(self._all_answer_cache, f, ensure_ascii=False, indent=4)

    async def _check_results(self, sheets: list[QuestionSheet]) -> tuple[int, int]:
        """检查作业结果并更新缓存"""
        correct_count = 0
        total_count = len(sheets)

        for sheet in sheets:
            version = sheet.version
            question = await self._get_question_content(sheet.question_id, version)
            if question is None:
                continue

            # 检查用户是否答对（使用 userAnswerVo[0].isCorrect）
            user_answers = question.user_answer_vos
            is_correct = bool(user_answers) and user_answers[0].is_correct == 1
            if is_correct:
                correct_count += 1

            # 获取正确选项（用于缓存更新）
            correct_opts = [opt for opt in question.option_vos if opt.is_correct == 1]

            # 更新缓存
            if question.question_type == 3:
                if correct_opts:
                    answer_str = "#@#".join(opt.content for opt in correct_opts)
                    answer_content_str = "\n".join(opt.content for opt in correct_opts)
                elif user_answers:
                    # 没有 optionVos 时，从 userAnswerVo 获取正确答案
                    correct_answers = [a.answer for a in user_answers if a.is_correct == 1]
                    answer_str = "#@#".join(correct_answers)
                    answer_content_str = "\n".join(correct_answers)
                else:
                    answer_str = ""
                    answer_content_str = ""
            else:
                answer_str = "#@#".join(str(opt.id) for opt in correct_opts)
                answer_content_str = "\n".join(opt.content for opt in correct_opts)

            self._set_cached_answer(
                sheet.question_id,
                version,
                {
                    "question": question.content,
                    "answer": answer_str,
                    "answer_content": answer_content_str,
                    "questionDict": question.model_dump(),
                },
            )

        self._save_cache()
        return correct_count, total_count

"""AI 考试上下文（同步执行）

与 HomeworkCtx 的区别：
- taskList 使用 ai_key 加密（ai_task_query）
- openExam / getAnswerSheetInformation / getExamQuestionInfo / saveBatchAnswer /
  updateUserUsedTime / submit 使用 exam_key（ai_exam_query / ai_exam_submit）
- openExamDetail 使用 ai_key（ai_task_query），用于提交后判断是否可查看答案
- 批量保存 saveBatchAnswer（每 save_nums 题保存一次）
- 填空题 answer 用 / 分隔
- submit 后若可查看答案（isLookAnswer/isAllowShowDetail=1）则保存正确答案到缓存
"""

import contextlib
import json
import random
import threading
import time
from typing import Any

from loguru import logger

from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.config import AIConfig, ExamConfig
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.llm.openai import OpenAIProvider
from zhs.llm.zhidao import ZhidaoAIProvider
from zhs.session import ZhsSession
from zhs.utils.display import _C, progress_bar, styled, wipe_line
from zhs.utils.path import get_data_dir


class ExamCtx:
    """AI 考试上下文（同步执行）

    使用 LLM 提供者自动答题，支持缓存、批量保存和心跳。
    """

    def __init__(
        self,
        session: ZhsSession,
        course_id: str,
        class_id: str,
        exam_test_id: str,
        exam_paper_id: str,
        ai_config: AIConfig,
        exam_config: ExamConfig,
        op_extra: dict[str, Any] | None = None,
        progress_view: bool = True,
        student_id: int = 0,
        task_id: str = "",
    ) -> None:
        self._session = session
        self._course_id = course_id
        self._class_id = class_id
        self._exam_test_id = exam_test_id
        self._exam_paper_id = exam_paper_id
        self._ai_config = ai_config
        self._exam_config = exam_config
        self._op_extra = op_extra or {}
        self._progress_view = progress_view
        self._student_id = student_id
        self._task_id = task_id

        self._save_nums = exam_config.save_nums
        self._answer_cache: dict[str, dict[str, Any]] = {}
        self._all_answer_cache: dict[str, dict[str, Any]] = {}
        self._sheet_content: list[QuestionSheet] | None = None
        self._stopped = False
        self._heartbeat_thread: threading.Thread | None = None
        self._reference_materials: list[dict[str, str]] = []
        self._progress_total = 0
        self._progress_current = 0
        self._progress_sources: list[str] = []

        # 初始化 LLM 提供者
        self._provider: LLMProvider | None = None
        if not ai_config.enabled:
            self._provider = None
        elif ai_config.use_zhidao_ai:
            self._provider = ZhidaoAIProvider(
                session=session,
                course_id=str(course_id),
                course_name=str(op_extra.get("courseName", "")) if op_extra else "",
            )
        elif ai_config.api_key:
            self._provider = OpenAIProvider(
                api_key=ai_config.api_key,
                base_url=ai_config.base_url,
                model_name=ai_config.model,
            )

    def start(
        self,
        reference_materials: list[dict[str, str]] | None = None,
        submit: bool = False,
    ) -> tuple[bool, int, int]:
        """执行完整考试流程，返回 (是否全对, 正确数, 总题数)

        Args:
            reference_materials: 参考资料（PPT 等）
            submit: 是否提交考试。提交后若可查看答案则保存缓存。
        """
        self._reference_materials = reference_materials or []

        # 加载缓存
        self._load_cache()

        # 打开考试
        self._open_exam()

        # 启动心跳（daemon 线程）
        self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

        # 获取答题卡
        sheets = self._get_sheet_content()
        if not sheets:
            self._stopped = True
            raise ZhsError("答题卡内容为空")

        # 顺序答题（批量保存）
        total = len(sheets)
        self._progress_total = total
        self._progress_current = 0
        self._progress_sources = []
        self._update_progress("pending")
        self._process_questions(sheets)

        # 清除进度行
        wipe_line()

        # 提交流程
        if submit:
            self._submit()
            detail = self._open_exam_detail()
            can_see = detail.get("isLookAnswer") == 1 or detail.get("isAllowShowDetail") == 1
            if can_see:
                correct_count, total_count = self._check_results(sheets)
                self._stopped = True
                return correct_count == total_count, correct_count, total_count
            else:
                logger.info("考试已提交，但无法查看答案，不保存缓存")
                self._stopped = True
                return False, 0, total

        # 不提交
        self._stopped = True
        return False, 0, total

    # --- 考试 API（exam_key） ---

    @property
    def _exam_base_url(self) -> str:
        """考试 API 基础 URL"""
        return self._session.urls.exam

    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """同步考试 API 查询（exam_key 加密）"""
        return self._session.ai_exam_query(url, data, method=method)

    def _open_exam(self, _retries: int = 0) -> None:
        """打开考试"""
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/openExam"
        data = {
            "examTestId": self._exam_test_id,
            "courseId": self._course_id,
        }
        try:
            self._api_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"openExam 失败，重试 {_retries + 1}/3")
                self._open_exam(_retries + 1)
            else:
                raise ZhsError("openExam 失败，已重试 3 次") from e

    def _get_sheet_content(self, _retries: int = 0) -> list[QuestionSheet]:
        """获取答题卡信息（getAnswerSheetInformation）"""
        if self._sheet_content is not None:
            return self._sheet_content

        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/getAnswerSheetInformation"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
        }
        try:
            result = self._api_query(url, data, method="GET")
            sheets: list[QuestionSheet] = []
            for part in result["data"]["partSheetVos"]:
                for q in part["questionSheetVos"]:
                    sheets.append(QuestionSheet.model_validate(q))
            self._sheet_content = sheets
        except Exception as e:
            if _retries < 2:
                logger.error(f"getAnswerSheetInformation 失败，重试 {_retries + 1}/3")
                return self._get_sheet_content(_retries + 1)
            else:
                raise ZhsError("getAnswerSheetInformation 失败，已重试 3 次") from e

        return self._sheet_content

    def _get_question_content(self, question_id: int, version: int, _retries: int = 0) -> QuestionContent | None:
        """获取题目详情（getExamQuestionInfo）"""
        url = f"{self._exam_base_url}/gateway/t/v1/question/getExamQuestionInfo"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "questionId": question_id,
            "version": version,
        }
        try:
            result = self._api_query(url, data, method="GET")
            return QuestionContent.model_validate(result["data"])
        except Exception as e:
            if _retries < 2:
                logger.error(f"getExamQuestionInfo 失败，重试 {_retries + 1}/3")
                return self._get_question_content(question_id, version, _retries + 1)
            else:
                logger.error(f"getExamQuestionInfo 失败，已重试 3 次: {e}")
                return None

    def _save_batch_answer(self, answers: list[dict[str, Any]]) -> bool:
        """批量保存答案（saveBatchAnswer）

        Args:
            answers: 答案列表，每个元素包含 questionId, answer, questionType
        """
        if not answers:
            return False
        url = f"{self._exam_base_url}/gateway/t/v1/answer/saveBatchAnswer"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "recruitId": self._course_id,
            "answerList": [
                {
                    "recruitId": self._course_id,
                    "examTestId": self._exam_test_id,
                    "examPaperId": self._exam_paper_id,
                    "questionId": a["questionId"],
                    "answer": a["answer"],
                    "questionType": a["questionType"],
                    "dataVos": None,
                }
                for a in answers
            ],
        }
        try:
            self._api_query(url, data)
            return True
        except Exception as e:
            logger.error(f"saveBatchAnswer 失败: {e}")
            return False

    def _submit(self) -> None:
        """提交考试（submit，exam_key 加密，无返回体）"""
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/submit"
        data = {
            "examTestId": self._exam_test_id,
            "recruitId": self._course_id,
            "examPaperId": self._exam_paper_id,
        }
        try:
            self._session.ai_exam_submit(url, data)
            logger.info("考试已提交")
        except Exception as e:
            raise ZhsError("submit 失败") from e

    def _open_exam_detail(self) -> dict[str, Any]:
        """获取考试详情（openExamDetail，ai_key 加密）

        用于提交后判断是否可查看答案（isLookAnswer / isAllowShowDetail）。
        失败时返回空字典。
        """
        url = f"{self._session.urls.ai}/run/gateway/t/task/exam/openExamDetail"
        data = {
            "classId": self._class_id,
            "courseId": self._course_id,
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "examId": self._exam_paper_id,
            "studentId": self._student_id,
            "taskId": self._task_id,
            "taskType": None,
        }
        try:
            result = self._session.ai_task_query(url, data)
            data_dict: dict[str, Any] = result.get("data", {})
            if isinstance(data_dict, dict):
                return data_dict
            return {}
        except Exception as e:
            logger.error(f"openExamDetail 失败: {e}")
            return {}

    # --- 心跳 ---

    def _heartbeat(self, interval: int = 10) -> None:
        """同步心跳（daemon 线程），定期更新考试用时"""
        while not self._stopped:
            self._heartbeat_once()
            time.sleep(interval)

    def _heartbeat_once(self) -> None:
        """单次心跳"""
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/updateUserUsedTime"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "heartbeatTime": 5,
        }
        try:
            self._api_query(url, data)
        except Exception as e:
            logger.error(f"心跳失败: {e}")

    # --- 答题 ---

    @staticmethod
    def _cache_key(question_id: int) -> str:
        """生成缓存键（仅用 question_id）"""
        return str(question_id)

    def _get_cached_answer(self, question_id: int) -> list[str] | None:
        """从缓存获取答案（两级缓存）"""
        key = self._cache_key(question_id)
        for cache in (self._all_answer_cache, self._answer_cache):
            entry = cache.get(key)
            if entry is not None:
                return self._parse_cached_answer(entry.get("answer", ""))
        return None

    @staticmethod
    def _parse_cached_answer(answer_str: str) -> list[str] | None:
        """解析缓存中的 answer 字段

        - 含 #@# → 按 #@# 分隔（多选题选项 ID）
        - 不含 #@# → 返回单元素列表（单选/判断/填空题）
        填空题多个空用 / 合并存储，不拆分。
        """
        if not answer_str:
            return None
        if "#@#" in answer_str:
            return answer_str.split("#@#")
        return [answer_str]

    def _set_cached_answer(self, question_id: int, data: dict[str, Any]) -> None:
        """设置缓存"""
        key = self._cache_key(question_id)
        cache_entry = {
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
                    else:
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

    @staticmethod
    def _format_answer(answers: list[str], question_type: int) -> str:
        """格式化答案为字符串

        - 选择题/判断题：用 #@# 分隔选项 ID
        - 填空题：用 / 分隔多个答案
        """
        if question_type == 3:
            return "/".join(str(a) for a in answers)
        return "#@#".join(str(a) for a in answers)

    def _process_questions(self, sheets: list[QuestionSheet]) -> None:
        """处理所有题目（批量保存，每 save_nums 题保存一次）"""
        pending: list[dict[str, Any]] = []

        for sheet in sheets:
            time.sleep(random.uniform(self._exam_config.delay_min, self._exam_config.delay_max))

            question = self._get_question_content(sheet.question_id, sheet.version)
            if question is None:
                logger.error(f"获取题目失败: {sheet.question_id}")
                self._progress_current += 1
                self._update_progress("error")
                continue

            answers, source = self._get_answer(question)
            if answers:
                answer_str = self._format_answer(answers, question.question_type)
                pending.append(
                    {
                        "questionId": sheet.question_id,
                        "answer": answer_str,
                        "questionType": question.question_type,
                    }
                )

            self._progress_current += 1
            self._progress_sources.append(source)
            self._update_progress(source)

            if self._progress_view:
                logger.info(f"题目 {sheet.question_id}: {source}")

            # 达到 save_nums 题时批量保存
            if len(pending) >= self._save_nums:
                self._save_batch_answer(pending)
                pending = []

        # 保存剩余题目
        if pending:
            self._save_batch_answer(pending)

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
        line = f"\r  {bar} {cur_tag} {source_str}"
        with contextlib.suppress(Exception):
            print(line, end="", flush=True)

    # --- 缓存 ---

    def _load_cache(self) -> None:
        """加载缓存（复用 ai_homework_cache 目录）"""
        cache_dir = get_data_dir() / "cache" / "ai_homework_cache" / str(self._course_id)
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
                logger.error("jsonDecodeError")

        self._all_answer_cache = {}
        for key, value in merged.items():
            if isinstance(value, dict):
                self._all_answer_cache[key] = value

        # 加载 data.json（如果存在，优先使用）
        all_path = cache_dir / "data.json"
        if all_path.exists():
            try:
                with open(all_path, encoding="utf-8") as f:
                    data_cache = json.load(f)
                    if isinstance(data_cache, dict):
                        for key, value in data_cache.items():
                            if isinstance(value, dict):
                                self._all_answer_cache[key] = value
            except (json.JSONDecodeError, OSError):
                logger.error("jsonDecodeError")

        # 加载 answer_cache（当前考试）
        exam_path = cache_dir / f"{self._exam_test_id}.json"
        if exam_path.exists():
            try:
                with open(exam_path, encoding="utf-8") as f:
                    exam_cache = json.load(f)
                    if isinstance(exam_cache, dict):
                        self._answer_cache = {k: v for k, v in exam_cache.items() if isinstance(v, dict)}
            except (json.JSONDecodeError, OSError):
                self._answer_cache = {}

    def _save_cache(self) -> None:
        """保存缓存"""
        cache_dir = get_data_dir() / "cache" / "ai_homework_cache" / str(self._course_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        exam_path = cache_dir / f"{self._exam_test_id}.json"
        with open(exam_path, "w", encoding="utf-8") as f:
            json.dump(self._answer_cache, f, ensure_ascii=False, indent=4)

        all_path = cache_dir / "data.json"
        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(self._all_answer_cache, f, ensure_ascii=False, indent=4)

    def _check_results(self, sheets: list[QuestionSheet]) -> tuple[int, int]:
        """检查考试结果并更新缓存"""
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

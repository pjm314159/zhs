"""AI 作业上下文（同步执行）

使用 LLM 提供者自动答题，支持两级缓存、顺序处理和心跳。
AI 课程的"考试"实际上是作业，统一命名为 homework。

同步实现说明：
- 顺序处理题目（不再并发），避免作业 API 限流
- 心跳使用 daemon 线程
- 延迟使用 time.sleep()
"""

import contextlib
import json
import random
import threading
import time
from typing import Any

from loguru import logger

from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.config import AIConfig
from zhs.exceptions import ZhsError
from zhs.llm.base import LLMProvider
from zhs.llm.openai import OpenAIProvider
from zhs.llm.zhidao import ZhidaoAIProvider
from zhs.session import ZhsSession
from zhs.utils.display import _C, progress_bar, styled, wipe_line
from zhs.utils.path import get_data_dir


class HomeworkCtx:
    """AI 作业上下文（同步执行）

    使用 LLM 提供者自动答题，支持两级缓存、顺序处理和心跳。
    """

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

    def start(self, reference_materials: list[dict[str, str]] | None = None) -> tuple[bool, int, int]:
        """执行完整作业流程，返回 (是否全对, 正确数, 总题数)"""
        self._reference_materials = reference_materials or []

        # 加载缓存
        self._load_cache()

        # 打开作业
        self._open_homework()

        # 启动心跳（daemon 线程）
        self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

        # 获取试卷内容
        sheets = self._get_sheet_content()
        if not sheets:
            self._stopped = True
            raise ZhsError("试卷内容为空")

        # 顺序答题（避免 API 限流）
        total = len(sheets)
        self._progress_total = total
        self._progress_current = 0
        self._progress_sources = []
        self._update_progress("pending")
        for sheet in sheets:
            self._process_question(sheet)

        # 清除进度行
        wipe_line()

        # 提交作业
        self._submit_homework()

        # 检查结果并更新缓存
        correct_count, total_count = self._check_results(sheets)

        # 停止心跳
        self._stopped = True

        return correct_count == total_count, correct_count, total_count

    # --- 作业 API ---

    @property
    def _homework_base_url(self) -> str:
        """作业 API 基础 URL"""
        return self._session.urls.exam

    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """同步作业 API 查询"""
        return self._session.ai_exam_query(url, data, method=method)

    def _open_homework(self, _retries: int = 0) -> None:
        """打开作业"""
        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/openExam"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "courseId": self._course_id,
        }
        try:
            self._api_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"openExam 失败，重试 {_retries + 1}/3")
                self._open_homework(_retries + 1)
            else:
                raise ZhsError("openExam 失败，已重试 3 次") from e

    def _get_sheet_content(self, _retries: int = 0) -> list[QuestionSheet]:
        """获取试卷内容"""
        if self._sheet_content is not None:
            return self._sheet_content

        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/getExamSheetInfo"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
        }
        try:
            result = self._api_query(url, data, method="GET")
            raw_sheets = result["data"]["partSheetVos"][0]["questionSheetVos"]
            self._sheet_content = [QuestionSheet.model_validate(s) for s in raw_sheets]
        except Exception as e:
            if _retries < 2:
                logger.error(f"getSheetContent 失败，重试 {_retries + 1}/3")
                return self._get_sheet_content(_retries + 1)
            else:
                raise ZhsError("getSheetContent 失败，已重试 3 次") from e

        return self._sheet_content

    def _get_question_content(self, question_id: int, version: int, _retries: int = 0) -> QuestionContent | None:
        """获取题目内容"""
        url = f"{self._homework_base_url}/gateway/t/v1/question/getExamQuestionInfo"
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
                logger.error(f"getQuestionContent 失败，重试 {_retries + 1}/3")
                return self._get_question_content(question_id, version, _retries + 1)
            else:
                logger.error(f"getQuestionContent 失败，已重试 3 次: {e}")
                return None

    def _save_answer(self, question_id: int, answers: list[str]) -> bool:
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
            self._api_query(url, data)
            return True
        except Exception as e:
            logger.error(f"saveAnswer 失败: {e}")
            return False

    def _submit_homework(self, _retries: int = 0) -> None:
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
            self._api_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"submitExam 失败，重试 {_retries + 1}/3")
                self._submit_homework(_retries + 1)
            else:
                raise ZhsError("submitExam 失败，已重试 3 次") from e
        finally:
            self._stopped = True

    # --- 心跳 ---

    def _heartbeat(self, interval: int = 10) -> None:
        """同步心跳（daemon 线程），定期更新作业用时"""
        url = f"{self._homework_base_url}/gateway/t/v1/exam/user/updateUserUsedTime"
        data = {
            "examTestId": self._exam_test_id,
            "examPaperId": self._exam_paper_id,
            "heartbeatTime": interval,
        }
        while not self._stopped:
            try:
                self._api_query(url, data)
            except Exception as e:
                logger.error(f"心跳失败: {e}")
            time.sleep(interval)

    # --- 答题 ---

    @staticmethod
    def _cache_key(question_id: int) -> str:
        """生成缓存键（仅用 question_id，不含 version）"""
        return str(question_id)

    def _get_cached_answer(self, question_id: int) -> list[str] | None:
        """从缓存获取答案（两级缓存，兼容旧 _version 后缀 key）"""
        key = self._cache_key(question_id)
        # 先查新 key（纯数字），再查旧 key（带 _version 后缀）
        for cache in (self._all_answer_cache, self._answer_cache):
            entry = cache.get(key)
            if entry is not None:
                return self._parse_cached_answer(entry.get("answer", ""))
            # 兼容旧缓存：遍历查找 _version 后缀的 key
            for old_key, old_entry in cache.items():
                if old_key.startswith(f"{question_id}_") and isinstance(old_entry, dict):
                    return self._parse_cached_answer(old_entry.get("answer", ""))
        return None

    @staticmethod
    def _parse_cached_answer(answer_str: str) -> list[str] | None:
        """解析缓存中的 answer 字段

        - 含 #@# → 按 #@# 分隔（选择题/多选题的选项 ID）
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

    def _process_question(self, sheet: QuestionSheet) -> None:
        """处理单道题目（顺序执行，含延迟防限流）"""
        time.sleep(random.uniform(3, 5))

        question = self._get_question_content(sheet.question_id, sheet.version)
        if question is None:
            logger.error(f"获取题目失败: {sheet.question_id}")
            self._progress_current += 1
            self._update_progress("error")
            return

        answers, source = self._get_answer(question)
        if answers:
            self._save_answer(sheet.question_id, answers)

        self._progress_current += 1
        self._update_progress(source)

        if self._progress_view:
            logger.info(f"题目 {sheet.question_id}: {source}")

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
        """加载缓存（扫描同课程目录下所有 JSON 文件）

        自动迁移旧格式：key 含 _version 后缀的转为纯 question_id，
        删除 version 字段，填空题 answer 中 #@# 还原为 /。
        """
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
                pass

        # 迁移旧格式并加载
        self._all_answer_cache = {}
        for key, value in merged.items():
            if not isinstance(value, dict):
                continue

            # 迁移 key：去掉 _version 后缀
            new_key = key.split("_")[0] if "_" in key else key

            # 删除 version 字段
            value.pop("version", None)

            # 填空题：#@# → /（修复之前错误迁移）
            qdict = value.get("questionDict")
            is_fill = isinstance(qdict, dict) and qdict.get("question_type") == 3
            if is_fill:
                answer = value.get("answer", "")
                if answer and "#@#" in answer:
                    value["answer"] = answer.replace("#@#", "/")

            self._all_answer_cache[new_key] = value

        # 加载 data.json（如果存在，优先使用）
        all_path = cache_dir / "data.json"
        if all_path.exists():
            try:
                with open(all_path, encoding="utf-8") as f:
                    data_cache = json.load(f)
                    if isinstance(data_cache, dict):
                        for key, value in data_cache.items():
                            if isinstance(value, dict):
                                new_key = key.split("_")[0] if "_" in key else key
                                if "version" in value:
                                    del value["version"]
                                qdict = value.get("questionDict")
                                is_fill = isinstance(qdict, dict) and qdict.get("question_type") == 3
                                if is_fill:
                                    answer = value.get("answer", "")
                                    if answer and "#@#" in answer:
                                        value["answer"] = answer.replace("#@#", "/")
                                self._all_answer_cache[new_key] = value
            except (json.JSONDecodeError, OSError):
                pass

        # 加载 answer_cache（当前作业）
        exam_path = cache_dir / f"{self._exam_test_id}.json"
        if exam_path.exists():
            try:
                with open(exam_path, encoding="utf-8") as f:
                    exam_cache = json.load(f)
                    if isinstance(exam_cache, dict):
                        # 迁移旧格式
                        migrated: dict[str, dict[str, Any]] = {}
                        for key, value in exam_cache.items():
                            if not isinstance(value, dict):
                                continue
                            new_key = key.split("_")[0] if "_" in key else key
                            if "version" in value:
                                del value["version"]
                            qdict = value.get("questionDict")
                            is_fill = isinstance(qdict, dict) and qdict.get("question_type") == 3
                            if is_fill:
                                answer = value.get("answer", "")
                                if answer and "#@#" in answer:
                                    value["answer"] = answer.replace("#@#", "/")
                            migrated[new_key] = value
                        self._answer_cache = migrated
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
        """检查作业结果并更新缓存"""
        correct_count = 0
        total_count = len(sheets)

        for sheet in sheets:
            version = sheet.version
            question = self._get_question_content(sheet.question_id, version)
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
                # 填空题：多个空用 / 合并存储为单个字符串
                if correct_opts:
                    answer_str = "/".join(opt.content for opt in correct_opts)
                    answer_content_str = "\n".join(opt.content for opt in correct_opts)
                elif user_answers:
                    # 没有 optionVos 时，从 userAnswerVo 获取正确答案
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

"""知识图谱课掌握度测验：使用明确答案，失败不视为完成。"""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

from zhs.config import HomeworkConfig
from zhs.exceptions import ApiError
from zhs.question_bank.client import QuestionBankClient
from zhs.question_bank.models import map_question_type
from zhs.utils.display import msg_done, msg_error, msg_info, msg_warn
from zhs.utils.html import extract_text

if TYPE_CHECKING:
    from zhs.llm.base import LLMProvider
    from zhs.session import ZhsSession
    from zhs.zhidao.models import MapLesson


class ExamPrinter(Protocol):
    """兼容播放器的带层级输出回调。"""

    def __call__(self, text: str, depth: int = 0) -> None: ...


QUESTION_LABELS = {1: "单选", 2: "多选", 14: "判断"}


class KgExamHandler:
    """仅在整套题均有合法答案后提交，不猜测默认选项。"""

    def __init__(
        self,
        session: "ZhsSession",
        homework_config: HomeworkConfig,
        question_bank: QuestionBankClient | None = None,
        llm: "LLMProvider | None" = None,
    ) -> None:
        self._session = session
        self._config = homework_config
        self._qb = question_bank
        self._llm = llm

    def try_handle_exam(
        self,
        recruit_id: str,
        lesson: "MapLesson",
        print_callback: ExamPrinter | None = None,
        *,
        course_id: int,
    ) -> bool:
        if not self._config.enable_kg_exam:
            return True

        def report(message: str) -> None:
            if print_callback:
                print_callback(message, depth=3)

        knowledge_id = lesson.id_hash
        report(msg_info("掌握度 · 正在获取题目"))
        for retry in range(self._config.kg_exam_max_retries + 1):
            try:
                # 每次重新开始，不能复用上次的 examId 或题目。
                exam = self._session.kg_exam_start(recruit_id, course_id, knowledge_id)
                questions = exam.get("questions")
                if not isinstance(questions, list) or not questions or not exam.get("examId"):
                    raise ValueError("测验未返回有效 examId/题目，无法确认掌握度")
                if exam.get("knowledgeId", knowledge_id) != knowledge_id:
                    raise ValueError("测验返回的知识点与请求不一致，未提交")
                source = "题库参考 + AI" if self._qb is not None else "AI"
                report(f"掌握度 · {len(questions)} 题 · {source} · 目标 {self._config.kg_exam_threshold}%")
                mastery = self._do_exam_once(recruit_id, exam["examId"], knowledge_id, questions, report)
                rate = float(mastery["rate"])
                if not 0 <= rate <= 100:
                    raise ValueError("掌握度不在 0-100 范围")
                if rate >= self._config.kg_exam_threshold:
                    report(msg_done(f"掌握度达标: {rate:g}% / 目标 {self._config.kg_exam_threshold}%"))
                    return True
                if retry < self._config.kg_exam_max_retries:
                    report(
                        msg_warn(f"掌握度 {rate:g}% 未达标 · 准备重做 {retry + 1}/{self._config.kg_exam_max_retries}")
                    )
                    time.sleep(1)
                else:
                    report(msg_warn(f"掌握度 {rate:g}% 未达标 · 已用完 {self._config.kg_exam_max_retries} 次重做机会"))
            except Exception as exc:
                # 没有抓包依据将 404/500 等错误解释为“无测验”。
                logger.error(f"KG 测验失败 ({knowledge_id}): {exc}")
                report(msg_error(f"掌握度测验失败: {exc}"))
                return False
        return False

    def _do_exam_once(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
        questions: list[dict[str, Any]],
        report: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        answers = []
        for index, question in enumerate(questions, 1):
            if report:
                label = QUESTION_LABELS.get(question.get("questionType", 0), "未知题型")
                report(f"  答题 {index}/{len(questions)} · {label}")
            answer = self._get_answer(question)
            if answer is None:
                raise ValueError(f"题目 {question.get('questionId')} 无可靠答案，未提交整套测验")
            answers.append({"questionId": question["questionId"], "answer": answer})
        if report:
            report(msg_info("答题完成 · 正在提交并确认掌握度"))
        if not self._session.kg_exam_submit(recruit_id, exam_id, knowledge_id, answers):
            raise ApiError(-1, "提交答案失败")
        return self._session.kg_exam_get_mastery_info(recruit_id, exam_id, knowledge_id)

    def _get_answer(self, question: dict[str, Any]) -> int | str | None:
        qtype = question["questionType"]
        if qtype not in (1, 2, 14) or self._llm is None:
            return None
        options = question.get("optionVos") or []
        if not options:
            return None
        choices: list[dict[str, object]] = [{"id": opt["id"], "content": extract_text(opt["name"])} for opt in options]
        title = extract_text(question["questionName"])
        extra: dict[str, str] = {}
        if self._qb is not None:
            try:
                result = self._qb.query(
                    title, "\n".join(extract_text(opt["name"]) for opt in options), map_question_type(qtype)
                )
                if result is not None:
                    extra["题库参考"] = result.format_hint()
            except Exception as exc:
                logger.warning(f"KG 题库查询失败，回退 LLM: {exc}")
        if qtype == 1:
            selected = self._llm.single_choice(title, choices, extra=extra)
        elif qtype == 2:
            selected = self._llm.multiple_choice(title, choices, extra=extra)
        else:
            selected = self._llm.judgement(title, choices, extra=extra)
        valid_ids = {opt["id"] for opt in options}
        if not selected or any(type(i) is not int or i not in valid_ids for i in selected):
            return None
        if len(set(selected)) != len(selected) or (qtype != 2 and len(selected) != 1):
            return None
        return ",".join(str(i) for i in selected) if qtype == 2 else selected[0]

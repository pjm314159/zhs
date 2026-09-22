"""知到考试做题器

提供 ExamWorker 类，实现做考试的完整流程：
doExam → 生成答案（缓存/LLM/随机）→ saveStudentAnswer → [可选] submit

与 HomeworkWorker 的关键差异：
- **无心跳**：已抓包确认考试无心跳机制（不像 AI 考试有 updateUserUsedTime）
- **可选提交**：默认不提交（仅保存答案），用户指定 --submit 时调用 submit API
- **无检查对错**：无 lookExam/getStuAnswerInfo，不做错题分析和重做循环
- **源感知延迟**：仅缓存/随机答案延迟（避免 API 限流），LLM 答案不延迟（LLM API 本身有延迟）
- **examType=1**：saveStudentAnswer 中 examType 为整数 1（作业为空字符串 ""）
- **source=1**：saveStudentAnswer 额外发送 source=1 明文字段（由 API 层处理）

继承 HomeworkWorker 复用答案生成逻辑（缓存 → LLM → 随机）。
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from zhs.config import AppConfig
from zhs.exceptions import ZhsError
from zhs.reporter import ProgressReporter
from zhs.session import ZhsSession
from zhs.utils.display import _C, msg_done, msg_error, msg_info, msg_warn, progress_bar, styled
from zhs.utils.html import extract_text
from zhs.zhidao.exam.models import ExamInfo
from zhs.zhidao.homework.models import (
    HomeworkDetail,
    HomeworkQuestion,
)
from zhs.zhidao.homework.worker import HomeworkWorker

if TYPE_CHECKING:
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache as HomeworkCache
    from zhs.llm.base import LLMProvider
    from zhs.question_bank.client import QuestionBankClient


# 需要延迟的答案来源（缓存/随机，不含 LLM）
_SLEEP_SOURCES = frozenset({"缓存正确", "缓存排除直接", "无LLM随机"})


def _should_sleep(source: str) -> bool:
    """判断答案来源是否需要延迟（缓存/随机需延迟，LLM 不延迟）"""
    base = source.removesuffix("+题库")
    return base in _SLEEP_SOURCES


class ExamWorker(HomeworkWorker):
    """知到考试做题器

    继承 HomeworkWorker 的答案生成逻辑（缓存 → LLM → 随机），
    覆盖做题流程：doExam → 生成答案 → saveStudentAnswer（不提交）。

    关键差异见模块文档字符串。
    """

    def __init__(
        self,
        session: ZhsSession,
        config: AppConfig,
        cache: HomeworkCache,
        llm: LLMProvider | None = None,
        reporter: ProgressReporter | None = None,
        question_bank: QuestionBankClient | None = None,
    ) -> None:
        super().__init__(session, config, cache, llm=llm, reporter=reporter, question_bank=question_bank)

    def run_exam(self, exam: ExamInfo, recruit_id: str, school_id: str, submit: bool = False) -> int:
        """运行考试做题流程（doExam → 生成答案 → saveStudentAnswer → [可选] submit）

        无心跳、无检查对错。
        默认不提交，仅当 submit=True 时调用 submit API。

        Args:
            exam: 考试信息
            recruit_id: 招募 ID
            school_id: 学校 ID
            submit: 是否自动提交考试（默认 False，仅保存答案）

        Returns:
            已保存答案数量
        """
        # 考试标题
        self._reporter.print()
        self._reporter.print(styled("=" * 60, _C.DIM))
        self._reporter.print(styled(f"考试: {exam.exam_name}", _C.BOLD, _C.BRIGHT_CYAN))
        self._reporter.print(styled("=" * 60, _C.DIM))
        self._reporter.print(f"  课程: {styled(exam.course_name, _C.CYAN)}")
        self._reporter.print(f"  状态: state={exam.state}, 时限={exam.limit_time}分钟")
        self._reporter.print(f"  剩余次数: {exam.fa_student_exam_remain_count}")

        # 1. 获取题目
        self._reporter.print()
        self._reporter.print(msg_info("获取题目..."))
        detail = self._fetch_exam_detail(exam, recruit_id, school_id)
        questions = self._extract_questions(detail)

        if not questions:
            logger.warning(f"考试 {exam.exam_name} 无题目，跳过")
            self._reporter.print(f"  {msg_error('无题目，跳过')}")
            return 0

        self._reporter.print(f"  共 {styled(str(len(questions)), _C.BRIGHT_CYAN)} 题")

        # 2. 逐题生成答案并保存
        self._reporter.print()
        self._reporter.print(msg_info("开始答题..."))
        answer_count = 0
        for i, question in enumerate(questions, 1):
            # 保存选项到缓存
            self._save_options_to_cache(question, exam)  # type: ignore[arg-type]

            # 显示固定进度条
            qt_name = self._get_question_type_name(question.question_type_id)
            question_text = extract_text(question.name)[:30]
            bar_str = progress_bar(i - 1, len(questions), width=30)
            self._reporter.progress(f"  {bar_str} [{styled(qt_name, _C.CYAN)}] {question_text}... ")

            # 生成答案
            answer, source = self._generate_answer_with_source(question, exam)  # type: ignore[arg-type]
            if answer is None:
                self._reporter.wipe_line()
                self._reporter.print(
                    f"  {progress_bar(i, len(questions), width=30)} [{styled(qt_name, _C.CYAN)}] {question_text}"
                )
                self._reporter.print(f"    {msg_warn('无法生成答案，跳过')}")
                logger.warning(f"第 {i} 题无法生成答案，跳过")
                continue

            # 显示答案来源和内容
            answer_display = self._format_answer_display(answer, question)
            source_styled = self._style_source(source)
            self._reporter.wipe_line()
            self._reporter.print(
                f"  {progress_bar(i, len(questions), width=30)} [{styled(qt_name, _C.CYAN)}] {question_text}"
            )
            self._reporter.print(f"    来源: {source_styled}, 答案: {styled(answer_display, _C.BRIGHT_CYAN)}")

            # 保存答案
            try:
                self._save_answer(question, answer, exam, recruit_id, school_id)
                answer_count += 1
                self._reporter.print(f"    {msg_done('已保存')}")
                logger.debug(f"第 {i} 题答案已保存: {answer}")
            except Exception as e:
                self._reporter.print(f"    {msg_error(f'保存失败: {e}')}")
                logger.error(f"第 {i} 题保存答案失败: {e}")

            # 源感知延迟：仅缓存/随机答案延迟，LLM 不延迟
            if _should_sleep(source):
                delay = random.uniform(self._config.exam.delay_min, self._config.exam.delay_max)
                time.sleep(delay)
                logger.debug(f"答案来源={source}, 延迟 {delay:.1f}s")
            else:
                logger.debug(f"答案来源={source}, 不延迟（LLM 答案）")

        # 3. 完成（按需提交）
        self._reporter.print()
        self._reporter.print(styled("=" * 60, _C.DIM))
        self._reporter.print(msg_done(f"答题完成: {exam.exam_name} ({answer_count}/{len(questions)} 题)"))

        if submit and answer_count > 0:
            # 自动提交
            self._reporter.print(msg_info("正在提交考试..."))
            try:
                self._submit_exam(exam, recruit_id, answer_count)
                self._reporter.print(msg_done("考试已提交"))
                logger.info(f"考试 {exam.exam_name}: 已提交（achieveCount={answer_count}）")
            except Exception as e:
                self._reporter.print(f"  {msg_error(f'提交失败: {e}')}")
                self._reporter.print(f"  {msg_warn('请手动提交考试')}")
                logger.error(f"考试 {exam.exam_name}: 提交失败: {e}")
        else:
            # 不提交，提示用户手动提交
            self._reporter.print(f"  {msg_warn('请手动提交考试（未指定 --submit）')}")
        self._reporter.print(styled("=" * 60, _C.DIM))

        # 题库使用统计
        if self._question_bank is not None:
            success, total = self._question_bank.get_usage_stats()
            if total > 0:
                self._reporter.print(msg_info(f"题库使用: 成功 {success} 次 / 总查询 {total} 次"))

        logger.info(f"考试 {exam.exam_name}: 答题完成，已保存 {answer_count}/{len(questions)} 题")
        return answer_count

    def _fetch_exam_detail(self, exam: ExamInfo, recruit_id: str, school_id: str) -> HomeworkDetail:
        """调用 doExam 获取题目详情

        响应结构与 doHomework 一致（rt.examBase.workExamParts[].questionDtos[]），
        复用 HomeworkDetail 模型解析。
        """
        result = self._session.exam_do(
            recruit_id=recruit_id,
            exam_id=exam.exam_id,
            student_exam_id=exam.id,
            school_id=school_id,
            course_id=str(exam.course_id),
        )
        return HomeworkDetail.model_validate(result)

    def _save_answer(
        self,
        question: HomeworkQuestion,
        answer: int | str,
        exam: ExamInfo,  # type: ignore[override]
        recruit_id: str,
        school_id: str,
    ) -> None:
        """保存单题答案（saveStudentAnswer）

        与 HomeworkWorker._save_answer 的差异：
        - 使用 session.exam_save_answer（而非 homework_save_answer）
        - examType=1（整数），作业为 ""（空字符串）
        - source=1 明文字段由 API 层自动添加

        注意：故意窄化参数类型为 ExamInfo（父类为 HomeworkItem），违反 LSP。
        ExamWorker 仅通过 run_exam 调用此方法（不继承 do_homework 流程），
        故实际不会传入 HomeworkItem，LSP 违规安全。
        """
        if not question.eid:
            raise ZhsError(f"题目无 eid，无法保存答案: {extract_text(question.name)[:30]}")

        answer_item: dict[str, Any] = {
            "examId": exam.exam_id,
            "recruitId": recruit_id,
            "stuExamId": exam.id,
            "eid": question.eid,
            "schoolId": school_id,
            "deviceId": "",
            "examType": 1,  # 考试为 1（整数），作业为 ""（空字符串）
            "fromType": 3,
            "answer": answer,
            "dataIds": "",
            "questionType": question.question_type_id,
        }

        self._session.exam_save_answer(answer_item, recruit_id)

    def _submit_exam(self, exam: ExamInfo, recruit_id: str, answer_count: int) -> None:
        """提交考试（submit）

        调用 session.exam_submit 提交考试。
        achieveCount 为已答题数量（字符串型）。

        Args:
            exam: 考试信息
            recruit_id: 招募 ID
            answer_count: 已答题数量

        Raises:
            ZhsError: 提交失败时抛出（statu != "1" 或 API 异常）
        """
        result = self._session.exam_submit(
            recruit_id=recruit_id,
            exam_id=exam.exam_id,
            stu_exam_id=exam.id,
            achieve_count=str(answer_count),
        )
        statu = result.get("statu", "")
        if statu != "1":
            raise ZhsError(f"提交失败: rt.statu={statu}, msg={result.get('msg', '')}")
        logger.debug(f"考试 {exam.exam_name} 提交成功: {result.get('msg', '')}")

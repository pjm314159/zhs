"""AI 作业上下文（同步执行）

继承 AiExamBase，实现逐题保存的作业流程。
AI 课程的"考试"实际上是作业，统一命名为 homework。

与 ExamCtx 的区别：
- 逐题保存（saveAnswer）而非批量保存
- openExam 包含 examPaperId 字段
- getExamSheetInfo 取 partSheetVos[0]
- submit 包含 courseType=8 和 aiKnlowledgeId
"""

import random
import time
from typing import Any

from loguru import logger

from zhs.ai.exam_base import AiExamBase
from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.config import AIConfig
from zhs.exceptions import ZhsError
from zhs.session import ZhsSession


class HomeworkCtx(AiExamBase):
    """AI 作业上下文（逐题保存）"""

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
        super().__init__(
            session=session,
            course_id=course_id,
            exam_test_id=exam_test_id,
            exam_paper_id=exam_paper_id,
            ai_config=ai_config,
            op_extra=op_extra,
            progress_view=progress_view,
        )
        self._knowledge_id = knowledge_id

    # --- API ---

    @property
    def _exam_base_url(self) -> str:
        """作业 API 基础 URL"""
        return self._session.urls.exam

    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """同步作业 API 查询"""
        return self._session.ai_exam_query(url, data, method=method)

    def _open(self, _retries: int = 0) -> None:
        """打开作业"""
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/openExam"
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
                self._open(_retries + 1)
            else:
                raise ZhsError("openExam 失败，已重试 3 次") from e

    def _get_sheet_content(self, _retries: int = 0) -> list[QuestionSheet]:
        """获取试卷内容（getExamSheetInfo，取 partSheetVos[0]）"""
        if self._sheet_content is not None:
            return self._sheet_content

        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/getExamSheetInfo"
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
                logger.error(f"getQuestionContent 失败，重试 {_retries + 1}/3")
                return self._get_question_content(question_id, version, _retries + 1)
            else:
                logger.error(f"getQuestionContent 失败，已重试 3 次: {e}")
                return None

    def _save_answer(self, question_id: int, answers: list[str]) -> bool:
        """保存单题答案（saveAnswer）"""
        if not answers:
            return False
        url = f"{self._exam_base_url}/gateway/t/v1/answer/saveAnswer"
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

    def _submit(self, submit: bool = True, _retries: int = 0) -> None:
        """提交作业（含 courseType=8 和 aiKnlowledgeId）"""
        url = f"{self._exam_base_url}/gateway/t/v1/exam/user/submit"
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
                self._submit(submit, _retries + 1)
            else:
                raise ZhsError("submitExam 失败，已重试 3 次") from e
        finally:
            self._stopped = True

    def _answer_questions(self, sheets: list[QuestionSheet]) -> None:
        """逐题顺序处理（含延迟防限流）"""
        for sheet in sheets:
            self._process_question(sheet)

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
        self._progress_sources.append(source)
        self._update_progress(source)

        if self._progress_view:
            logger.info(f"题目 {sheet.question_id}: {source}")

    def _finish(self, submit: bool, sheets: list[QuestionSheet]) -> tuple[bool, int, int]:
        """作业直接提交并检查结果"""
        self._submit(submit)
        correct_count, total_count = self._check_results(sheets)
        return correct_count == total_count, correct_count, total_count

    def start(
        self,
        reference_materials: list[dict[str, str]] | None = None,
        submit: bool = True,
    ) -> tuple[bool, int, int]:
        """执行完整作业流程，返回 (是否全对, 正确数, 总题数)

        Args:
            reference_materials: 参考资料（PPT 等）
            submit: 是否提交（作业默认提交）
        """
        return super().start(reference_materials, submit=submit)

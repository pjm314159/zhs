"""AI 考试上下文（同步执行）

继承 AiExamBase，实现批量保存的考试流程。

与 HomeworkCtx 的区别：
- taskList 使用 ai_key 加密（ai_task_query）
- startPullPaper 使用 ai_key（ai_task_query），openExam 前调用
- openExam / getAnswerSheetInformation / getExamQuestionInfo / saveBatchAnswer /
  updateUserUsedTime / submit 使用 exam_key（ai_exam_query / ai_exam_submit）
- openExamDetail 使用 ai_key（ai_task_query），用于提交后判断是否可查看答案
- 批量保存 saveBatchAnswer（每 save_nums 题保存一次）
- 填空题 answer 用 / 分隔
- submit 后若可查看答案（isLookAnswer/isAllowShowDetail=1）则保存正确答案到缓存
"""

import random
import time
from typing import Any

from loguru import logger

from zhs.ai.exam_base import AiExamBase
from zhs.ai.models import QuestionContent, QuestionSheet
from zhs.config import AIConfig, ExamConfig
from zhs.exceptions import ZhsError
from zhs.session import ZhsSession


class ExamCtx(AiExamBase):
    """AI 考试上下文（批量保存）"""

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
        super().__init__(
            session=session,
            course_id=course_id,
            exam_test_id=exam_test_id,
            exam_paper_id=exam_paper_id,
            ai_config=ai_config,
            op_extra=op_extra,
            progress_view=progress_view,
        )
        self._class_id = class_id
        self._exam_config = exam_config
        self._student_id = student_id
        self._task_id = task_id
        self._save_nums = exam_config.save_nums

    # --- API ---

    @property
    def _exam_base_url(self) -> str:
        """考试 API 基础 URL"""
        return self._session.urls.exam

    def _api_query(self, url: str, data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """同步考试 API 查询（exam_key 加密）"""
        return self._session.ai_exam_query(url, data, method=method)

    def _start_pull_paper(self, _retries: int = 0) -> None:
        """拉取试卷（startPullPaper，ai_key 加密，openExam 前调用）"""
        url = f"{self._session.urls.ai}/run/gateway/t/task/exam/start-pull-paper"
        data = {
            "courseId": self._course_id,
            "classId": self._class_id,
            "examTestId": self._exam_test_id,
            "pageNumber": 1,
            "pageSize": 10,
        }
        try:
            self._session.ai_task_query(url, data)
        except Exception as e:
            if _retries < 2:
                logger.error(f"startPullPaper 失败，重试 {_retries + 1}/3")
                self._start_pull_paper(_retries + 1)
            else:
                raise ZhsError("startPullPaper 失败，已重试 3 次") from e

    def _open(self, _retries: int = 0) -> None:
        """打开考试（startPullPaper + openExam）"""
        # 首次调用时先拉取试卷（重试时不重复拉取）
        if _retries == 0:
            self._start_pull_paper()
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
                self._open(_retries + 1)
            else:
                raise ZhsError("openExam 失败，已重试 3 次") from e

    def _get_sheet_content(self, _retries: int = 0) -> list[QuestionSheet]:
        """获取答题卡信息（getAnswerSheetInformation，遍历所有 partSheetVos）"""
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

    def _save_answer(self, question_id: int, answers: list[str]) -> bool:
        """单题保存（ExamCtx 使用批量保存，此方法不被调用）"""
        raise NotImplementedError("ExamCtx 使用 _save_batch_answer 批量保存")

    def _submit(self, submit: bool = True) -> None:
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

    def _heartbeat_once(self, interval: int = 5) -> None:
        """单次心跳（ExamCtx 使用 heartbeatTime=5）"""
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
    def _format_answer(answers: list[str], question_type: int) -> str:
        """格式化答案为字符串

        - 选择题/判断题：用 #@# 分隔选项 ID
        - 填空题：用 / 分隔多个答案
        """
        if question_type == 3:
            return "/".join(str(a) for a in answers)
        return "#@#".join(str(a) for a in answers)

    def _answer_questions(self, sheets: list[QuestionSheet]) -> None:
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

    def _finish(self, submit: bool, sheets: list[QuestionSheet]) -> tuple[bool, int, int]:
        """提交流程：submit → openExamDetail → 可查看则检查结果"""
        if not submit:
            return False, 0, len(sheets)

        self._submit(submit)
        detail = self._open_exam_detail()
        can_see = detail.get("isLookAnswer") == 1 or detail.get("isAllowShowDetail") == 1
        if can_see:
            correct_count, total_count = self._check_results(sheets)
            return correct_count == total_count, correct_count, total_count
        logger.info("考试已提交，但无法查看答案，不保存缓存")
        return False, 0, len(sheets)

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
        return super().start(reference_materials, submit=submit)

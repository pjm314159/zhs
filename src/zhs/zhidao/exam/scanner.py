"""知到考试扫描器

提供 ExamScanner 类，扫描知到课程的考试列表。
API: getStudentFinalExam（AES-128-CBC 加密，exam_key，无 dateFormate）

与知到作业 HomeworkScanner 的主要区别：
- 作业使用 getStudentHomework（flag=1 未提交/2 已提交），rt 为 {studentHomeworkList}
- 考试使用 getStudentFinalExam（flag=1 未完成/0 已完成），rt 为数组
- 考试无分页参数，作业有 pageSize/pageNum
- 考试需 SSO 认证 taurusexam-api 域名（与作业的 studentexam-api 不同）
"""

from loguru import logger

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.exam.models import ExamInfo, ExamListResult


class ExamScanner:
    """知到考试扫描器"""

    def __init__(self, session: ZhsSession, config: AppConfig) -> None:
        self._session = session
        self._config = config
        self._sso_done = False

    def _ensure_sso(self) -> None:
        """确保 taurusexam-api 已通过 CAS SSO 认证

        注意：taurusexam-api 与 studentexam-api 是否共享 SSO 认证需确认，
        若不共享则需扩展 SsoAuthenticator 支持多域名认证。
        当前复用 exam_sso_login（基于同域 SSO 假设）。
        """
        if not self._sso_done:
            self._session.exam_sso_login()
            self._sso_done = True

    def scan_exams(self, recruit_id: str, course_id: int) -> ExamListResult:
        """扫描指定课程的所有考试（未完成 + 已完成）

        Args:
            recruit_id: 招募 ID（课程注册 ID）
            course_id: 课程 ID

        Returns:
            ExamListResult（含 uncompleted 和 completed 两个列表）
        """
        self._ensure_sso()
        uncompleted = self._get_student_final_exam(recruit_id, course_id, flag=1)
        completed = self._get_student_final_exam(recruit_id, course_id, flag=0)

        logger.info(
            f"课程 {course_id}: 扫描到 {len(uncompleted)} 个未完成考试, "
            f"{len(completed)} 个已完成考试, 共 {len(uncompleted) + len(completed)} 个"
        )

        return ExamListResult(
            uncompleted=uncompleted,
            completed=completed,
        )

    def _get_student_final_exam(
        self,
        recruit_id: str,
        course_id: int,
        flag: int,
    ) -> list[ExamInfo]:
        """调用 getStudentFinalExam API 并解析为 ExamInfo 列表

        Args:
            recruit_id: 招募 ID
            course_id: 课程 ID
            flag: 1=未完成考试, 0=已完成考试

        Returns:
            ExamInfo 列表（API 异常时返回空列表）
        """
        try:
            items_data = self._session.exam_list(course_id, recruit_id, flag=flag)
        except Exception as e:
            logger.error(f"获取考试列表失败 (flag={flag}): {e}")
            return []

        if not items_data:
            return []

        items: list[ExamInfo] = []
        for d in items_data:
            try:
                items.append(ExamInfo.from_api(d))
            except Exception as e:
                logger.warning(f"解析考试项失败: {e}, data={d}")

        return items

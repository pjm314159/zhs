"""知到作业扫描器

提供 HomeworkScanner 类，扫描知到课程的作业列表并筛选需要处理的作业。
API: getStudentHomework（AES-128-CBC 加密，exam_key，无 dateFormate）
"""

from loguru import logger

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.models import HomeworkItem


class HomeworkScanner:
    """知到作业扫描器"""

    def __init__(self, session: ZhsSession, config: AppConfig) -> None:
        self._session = session
        self._config = config
        self._sso_done = False

    def _ensure_sso(self) -> None:
        """确保 studentexam-api 已通过 CAS SSO 认证"""
        if not self._sso_done:
            self._session.exam_sso_login()
            self._sso_done = True

    def scan_homework(self, recruit_id: str, course_id: int) -> list[HomeworkItem]:
        """扫描指定课程的所有作业（未提交 + 已提交）

        Args:
            recruit_id: 招募 ID
            course_id: 课程 ID

        Returns:
            所有作业列表（未提交 + 已提交）
        """
        self._ensure_sso()
        unsubmitted = self._get_student_homework(recruit_id, course_id, flag=1)
        submitted = self._get_student_homework(recruit_id, course_id, flag=2)
        all_items = unsubmitted + submitted

        logger.info(
            f"课程 {course_id}: 扫描到 {len(unsubmitted)} 个未提交作业, "
            f"{len(submitted)} 个已提交作业, 共 {len(all_items)} 个"
        )

        return all_items

    def filter_pending(self, items: list[HomeworkItem]) -> list[HomeworkItem]:
        """筛选需要处理的作业

        筛选规则：
        - 未提交（state=1）：必须做
        - 已提交但未达标（state=4, score < totalScore × homework_threshold%）：需要重做
          - 但 remaining_redo=0（无剩余重做次数）→ 跳过
          - 但 is_marking >= max_submit（已重做次数达上限）→ 跳过
        - 已提交且达标：跳过

        backNum 含义：总计重做次数。
        is_marking 含义：已重做次数（isMarking 字段）。
        remaining_redo 含义：剩余重做次数 = backNum - is_marking。
        """
        pending: list[HomeworkItem] = []

        for item in items:
            if item.state == 1:
                # 未提交，检查重做次数
                if self._config.max_submit > 0 and item.is_marking >= self._config.max_submit:
                    logger.debug(f"跳过: {item.exam_name} (已达最大重做次数 {self._config.max_submit})")
                    continue
                pending.append(item)
                logger.debug(f"需要做: {item.exam_name} (未提交)")
            elif item.state == 4:
                # 已提交，检查是否达标
                if self._is_achieved(item):
                    logger.debug(f"跳过: {item.exam_name} (已达标)")
                    continue
                if item.remaining_redo <= 0:
                    logger.debug(f"跳过: {item.exam_name} (无剩余重做次数)")
                    continue
                if self._config.max_submit > 0 and item.is_marking >= self._config.max_submit:
                    logger.debug(f"跳过: {item.exam_name} (已达最大重做次数 {self._config.max_submit})")
                    continue
                pending.append(item)
                logger.debug(f"需要重做: {item.exam_name} (未达标, score={item.score})")
            else:
                logger.debug(f"跳过: {item.exam_name} (未知状态 {item.state})")

        logger.info(f"筛选后需要处理 {len(pending)}/{len(items)} 个作业")
        return pending

    def _is_achieved(self, item: HomeworkItem) -> bool:
        """检查已提交作业是否达标"""
        if item.score is None:
            return False
        try:
            score = float(item.score)
            total = float(item.total_score)
            if total <= 0:
                return True
            rate = (score / total) * 100
            return rate >= self._config.homework_threshold
        except (ValueError, ZeroDivisionError):
            return False

    def _get_student_homework(self, recruit_id: str, course_id: int, flag: int) -> list[HomeworkItem]:
        """调用 getStudentHomework API

        Args:
            recruit_id: 招募 ID
            course_id: 课程 ID
            flag: 1=未提交作业，2=已提交作业
        """
        url = f"{self._session.urls.homework}/studentExam/gateway/t/v1/student/getStudentHomework"
        data = {
            "recruitId": recruit_id,
            "courseId": course_id,
            "flag": flag,
            "pageSize": self._config.homework_page_size,
            "pageNum": 0,
        }

        try:
            result = self._session.homework_query(url, data)
        except Exception as e:
            logger.error(f"获取作业列表失败 (flag={flag}): {e}")
            return []

        rt = result.get("rt", {})
        items_data = rt.get("studentHomeworkList", [])
        if not items_data:
            return []

        items: list[HomeworkItem] = []
        for d in items_data:
            try:
                items.append(HomeworkItem.model_validate(d))
            except Exception as e:
                logger.warning(f"解析作业项失败: {e}, data={d}")

        return items

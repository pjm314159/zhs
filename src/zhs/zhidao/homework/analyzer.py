"""知到作业错题分析器

提供 HomeworkAnalyzer 类，实现提交后检查和错题分析：
lookHomework → getStuAnswerInfo → 保存对错到缓存 → 判断是否重做
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.homework.models import (
    HomeworkAnswerInfo,
    HomeworkDetail,
    HomeworkItem,
    HomeworkQuestion,
)

if TYPE_CHECKING:
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache as HomeworkCache


class HomeworkAnalyzer:
    """知到作业错题分析器"""

    def __init__(
        self,
        session: ZhsSession,
        config: AppConfig,
        cache: HomeworkCache,
    ) -> None:
        self._session = session
        self._config = config
        self._cache = cache

    def check_result(
        self,
        item: HomeworkItem,
        recruit_id: str,
        school_id: str,
    ) -> tuple[list[HomeworkQuestion], dict[str, HomeworkAnswerInfo]]:
        """检查提交结果

        流程:
        1. lookHomework 获取题目详情（数字型 id）
        2. getStuAnswerInfo 获取每题对错信息
        3. 返回 (题目列表, {question_id: answer_info})

        Args:
            item: 作业项
            recruit_id: 招募 ID
            school_id: 学校 ID

        Returns:
            (题目列表, 答案信息字典)
        """
        # 1. lookHomework 获取题目详情
        detail = self._look_homework(item, recruit_id, school_id)
        questions = self._extract_questions(detail)

        if not questions:
            logger.warning(f"作业 {item.exam_name} 查看题目为空")
            return [], {}

        # 2. getStuAnswerInfo 获取对错信息
        question_ids = [q.id for q in questions if q.id is not None]
        if not question_ids:
            logger.warning(f"作业 {item.exam_name} 题目无数字型 id")
            return questions, {}

        answers = self._get_answer_info(item, recruit_id, school_id, question_ids)

        logger.info(
            f"作业 {item.exam_name}: {len(questions)} 题, "
            f"{sum(1 for a in answers.values() if a.is_correct)} 正确, "
            f"{sum(1 for a in answers.values() if a.is_wrong)} 错误, "
            f"{sum(1 for a in answers.values() if a.is_unanswered)} 未答"
        )

        return questions, answers

    def save_to_cache(
        self,
        item: HomeworkItem,
        questions: list[HomeworkQuestion],
        answers: dict[str, HomeworkAnswerInfo],
    ) -> None:
        """保存对错信息到本地缓存

        - 正确的题: mark_correct（记录学生选择的选项）
        - 错误的题: mark_wrong（记录学生选择的选项）
        - 未答的题: 不处理

        同时用 eid 和数字型 id 保存对错信息，确保重做时通过 eid 能查到对错。
        对于 lookHomework 返回的题目（有 id 无 eid），同时保存 options 到 id key，
        以便 find_key_by_options 能通过选项匹配找到 eid key。

        Args:
            item: 作业项
            questions: 题目列表
            answers: 答案信息字典
        """
        for question in questions:
            qid = str(question.id) if question.id is not None else ""
            if not qid:
                continue

            answer_info = answers.get(qid)
            if answer_info is None:
                continue

            # lookHomework 返回的题目有 options 但无 eid，保存 options 到 id key
            if question.question_options and not question.eid:
                self._save_question_options_to_cache(question, item)

            # 收集所有缓存 key：数字型 id + eid（如果有）
            keys: list[str] = [qid]
            if question.eid:
                keys.append(question.eid)
            else:
                # lookHomework 返回的题目没有 eid，通过选项匹配查找
                option_ids = [opt.id for opt in question.question_options]
                if option_ids:
                    eid_key = self._cache.find_key_by_options(item.course_id, item.exam_id, option_ids)
                    if eid_key:
                        keys.append(eid_key)
                        logger.debug(f"题目 {qid} 通过选项匹配找到 eid: {eid_key[:30]}")

            if answer_info.is_correct:
                # 正确 → 标记选择的选项为正确
                option_ids = self._parse_answer_option_ids(answer_info.answer)
                if option_ids:
                    for key in keys:
                        self._cache.mark_correct(item.course_id, item.exam_id, key, option_ids)
                    logger.debug(f"题目 {qid} 正确: 选项 {option_ids}")

            elif answer_info.is_wrong:
                # 错误 → 标记选择的选项为错误
                option_ids = self._parse_answer_option_ids(answer_info.answer)
                if option_ids:
                    for key in keys:
                        self._cache.mark_wrong(item.course_id, item.exam_id, key, option_ids)
                    logger.debug(f"题目 {qid} 错误: 选项 {option_ids}")

    def _save_question_options_to_cache(self, question: HomeworkQuestion, item: HomeworkItem) -> None:
        """保存 lookHomework 返回的题目选项到缓存（id key）"""
        from zhs.zhidao.homework.models import HomeworkCacheOption

        qid = str(question.id) if question.id is not None else ""
        if not qid:
            return

        options = [HomeworkCacheOption(id=opt.id, content=opt.content) for opt in question.question_options]
        self._cache.save_options(
            course_id=item.course_id,
            exam_id=item.exam_id,
            question_key=qid,
            question_type=question.question_type_id,
            options=options,
        )

    def should_redo(self, item: HomeworkItem, score_rate: float) -> bool:
        """判断是否需要重做

        条件:
        - score_rate < homework_threshold
        - remaining_redo > 0（剩余重做次数 > 0）
        - is_marking < max_submit（已重做次数未达上限）

        Args:
            item: 作业项
            score_rate: 得分率（0-100）

        Returns:
            是否需要重做
        """
        if score_rate >= self._config.homework.threshold:
            return False

        if item.remaining_redo <= 0:
            logger.debug(f"作业 {item.exam_name}: 无剩余重做次数")
            return False

        if self._config.homework.max_submit > 0 and item.is_marking >= self._config.homework.max_submit:
            logger.debug(f"作业 {item.exam_name}: 已达最大重做次数")
            return False

        return True

    def _look_homework(self, item: HomeworkItem, recruit_id: str, school_id: str) -> HomeworkDetail:
        """调用 lookHomework 获取题目详情"""
        result = self._session.homework_look(
            recruit_id=recruit_id,
            student_exam_id=item.id,
            exam_id=item.exam_id,
            school_id=school_id,
            course_id=str(item.course_id),
        )
        rt = result.get("rt", {})
        return HomeworkDetail.model_validate(rt)

    def _extract_questions(self, detail: HomeworkDetail) -> list[HomeworkQuestion]:
        """从 HomeworkDetail 中提取所有题目"""
        questions: list[HomeworkQuestion] = []
        for part in detail.exam_base.work_exam_parts:
            questions.extend(part.question_dtos)
        return questions

    def _get_answer_info(
        self,
        item: HomeworkItem,
        recruit_id: str,
        school_id: str,
        question_ids: list[int],
    ) -> dict[str, HomeworkAnswerInfo]:
        """调用 getStuAnswerInfo 获取对错信息"""
        result = self._session.homework_get_answer(
            recruit_id=recruit_id,
            stu_exam_id=item.id,
            exam_id=item.exam_id,
            school_id=school_id,
            course_id=str(item.course_id),
            question_ids=question_ids,
        )

        rt = result.get("rt", {})
        answers: dict[str, HomeworkAnswerInfo] = {}
        for qid_str, info_data in rt.items():
            if isinstance(info_data, dict):
                try:
                    answers[qid_str] = HomeworkAnswerInfo.model_validate(info_data)
                except Exception as e:
                    logger.warning(f"解析答案信息失败 (qid={qid_str}): {e}")

        return answers

    @staticmethod
    def _parse_answer_option_ids(answer: str) -> list[int]:
        """解析答案字符串为选项 ID 列表

        单选题: "440703134" → [440703134]
        多选题: "440703126,440703127" → [440703126, 440703127]
        未答: "" → []
        """
        if not answer:
            return []

        option_ids: list[int] = []
        for part in answer.split(","):
            part = part.strip()
            if part:
                try:
                    option_ids.append(int(part))
                except ValueError:
                    continue
        return option_ids

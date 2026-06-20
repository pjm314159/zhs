"""知到作业做题器

提供 HomeworkWorker 类，实现做作业的完整流程：
doHomework → 生成答案（缓存/LLM）→ saveStudentAnswer → submit
→ 提交后检查 → 错题分析 → 保存到缓存 → 重做循环
"""

import random
import re
import time
from typing import Any

from loguru import logger

from zhs.config import AppConfig
from zhs.exceptions import SliderVerificationRequired, ZhsError
from zhs.llm.base import LLMProvider
from zhs.session import ZhsSession
from zhs.utils.display import _C, msg_done, msg_error, msg_info, msg_warn, progress_bar, styled, wipe_line
from zhs.zhidao.homework.analyzer import HomeworkAnalyzer
from zhs.zhidao.homework.cache import HomeworkCache
from zhs.zhidao.homework.models import (
    HomeworkAnswerInfo,
    HomeworkCacheOption,
    HomeworkDetail,
    HomeworkItem,
    HomeworkQuestion,
    HomeworkQuestionOption,
    HomeworkQuestionType,
)


def _strip_html(text: str) -> str:
    """移除 HTML 标签，保留纯文本"""
    return re.sub(r"<[^>]+>", "", text).strip()


class HomeworkWorker:
    """知到作业做题器"""

    def __init__(
        self,
        session: ZhsSession,
        config: AppConfig,
        cache: HomeworkCache,
        llm: LLMProvider | None = None,
    ) -> None:
        self._session = session
        self._config = config
        self._cache = cache
        self._llm = llm
        self._analyzer = HomeworkAnalyzer(session, config, cache)

    def run_homework(self, item: HomeworkItem, recruit_id: str, school_id: str) -> float:
        """运行完整作业流程（做 → 提交 → 检查 → 重做循环），返回最终得分率

        流程:
        1. doHomework → 生成答案 → saveStudentAnswer → submit
        2. 检查得分率 >= threshold → 完成
        3. 得分率 < threshold → lookHomework + getStuAnswerInfo → 保存对错到缓存 → 重做
        4. 循环直到达标或无法重做

        Args:
            item: 作业项
            recruit_id: 招募 ID
            school_id: 学校 ID

        Returns:
            最终得分率（0-100）
        """
        # 作业标题
        print()
        print(styled("=" * 60, _C.DIM))
        print(styled(f"作业: {item.exam_name}", _C.BOLD, _C.BRIGHT_CYAN))
        print(styled("=" * 60, _C.DIM))
        print(f"  课程: {styled(item.course_name, _C.CYAN)}")
        print(f"  状态: state={item.state}, score={item.score}/{item.total_score}")
        print(f"  重做: 已重做{item.is_marking}次, 总次数{item.back_num}, 剩余{item.remaining_redo}次")

        # 已提交的作业（state=4）需要先重置状态才能答题
        # state=5 是已重置状态，可直接做题
        if item.state == 4:
            print()
            print(msg_info("重置作业状态..."))
            self._redo_homework(item, recruit_id)

        score_rate = self.do_homework(item, recruit_id, school_id)
        attempt = 1

        while self._analyzer.should_redo(item, score_rate):
            attempt += 1
            print()
            print(styled("-" * 60, _C.DIM))
            print(msg_warn(f"第 {attempt} 次尝试（重做）"))
            print(styled("-" * 60, _C.DIM))

            # 提交后检查：分析错题并保存到缓存
            print(msg_info("分析错题..."))
            questions, answers = self._analyzer.check_result(item, recruit_id, school_id)
            if questions and answers:
                correct_count = sum(1 for a in answers.values() if a.is_correct)
                wrong_count = sum(1 for a in answers.values() if a.is_wrong)
                print(f"  正确: {msg_done(str(correct_count))} 题, 错误: {msg_error(str(wrong_count))} 题")
                self._analyzer.save_to_cache(item, questions, answers)

                # 为错题请求 AI 解析并保存到缓存
                self._save_ai_analysis_for_wrong(item, questions, answers, recruit_id)

            # 重做：先重置作业状态，再重新答题
            print(msg_info("重置作业状态..."))
            self._redo_homework(item, recruit_id)
            score_rate = self.do_homework(item, recruit_id, school_id)

        print()
        print(styled("=" * 60, _C.DIM))
        if score_rate >= self._config.homework.threshold:
            print(msg_done(f"作业完成: {item.exam_name}"))
            print(f"   得分率: {styled(f'{score_rate:.1f}%', _C.GREEN)} (达标)")
        else:
            print(msg_warn(f"作业完成: {item.exam_name}"))
            threshold_str = f"(未达标，阈值 {self._config.homework.threshold}%)"
            print(f"   得分率: {styled(f'{score_rate:.1f}%', _C.YELLOW)} {threshold_str}")
        print(styled("=" * 60, _C.DIM))

        return score_rate

    def do_homework(self, item: HomeworkItem, recruit_id: str, school_id: str) -> float:
        """做单个作业，返回得分率（0-100）

        流程:
        1. doHomework 获取题目
        2. 逐题生成答案（缓存 → LLM）
        3. saveStudentAnswer 逐题保存
        4. submit 提交

        Args:
            item: 作业项
            recruit_id: 招募 ID
            school_id: 学校 ID

        Returns:
            得分率（0-100）
        """
        # 1. 获取题目
        print()
        print(msg_info("获取题目..."))
        detail = self._fetch_homework_detail(item, recruit_id, school_id)
        questions = self._extract_questions(detail)

        if not questions:
            logger.warning(f"作业 {item.exam_name} 无题目，跳过")
            print(f"  {msg_error('无题目，跳过')}")
            return 0.0

        print(f"  共 {styled(str(len(questions)), _C.BRIGHT_CYAN)} 题")

        # 2. 保存选项到缓存 + 逐题生成答案并保存
        print()
        print(msg_info("开始答题..."))
        answer_count = 0
        for i, question in enumerate(questions, 1):
            # 保存选项到缓存
            self._save_options_to_cache(question, item)

            # 显示固定进度条
            qt_name = self._get_question_type_name(question.question_type_id)
            question_text = _strip_html(question.name)[:30]
            bar_str = progress_bar(i - 1, len(questions), width=30)
            print(
                f"\r  {bar_str} [{styled(qt_name, _C.CYAN)}] {question_text}... ",
                end="",
                flush=True,
            )

            # 生成答案
            answer, source = self._generate_answer_with_source(question, item)
            if answer is None:
                wipe_line()
                print(f"  {progress_bar(i, len(questions), width=30)} [{styled(qt_name, _C.CYAN)}] {question_text}")
                print(f"    {msg_warn('无法生成答案，跳过')}")
                logger.warning(f"第 {i} 题无法生成答案，跳过")
                continue

            # 显示答案来源和内容（清除进度条后显示）
            answer_display = self._format_answer_display(answer, question)
            source_styled = self._style_source(source)
            wipe_line()
            print(f"  {progress_bar(i, len(questions), width=30)} [{styled(qt_name, _C.CYAN)}] {question_text}")
            print(f"    来源: {source_styled}, 答案: {styled(answer_display, _C.BRIGHT_CYAN)}")

            # 保存答案
            try:
                self._save_answer(question, answer, item, recruit_id, school_id)
                answer_count += 1
                print(f"    {msg_done('已保存')}")
                logger.debug(f"第 {i} 题答案已保存: {answer}")
            except Exception as e:
                print(f"    {msg_error(f'保存失败: {e}')}")
                logger.error(f"第 {i} 题保存答案失败: {e}")

            # 随机休息（使用配置的延迟范围）
            delay = random.uniform(self._config.homework.delay_min, self._config.homework.delay_max)
            time.sleep(delay)

        # 3. 提交
        if answer_count == 0:
            logger.warning(f"作业 {item.exam_name} 无答案可提交")
            print()
            print(f"  {msg_error('无答案可提交')}")
            return 0.0

        print()
        print(msg_info(f"提交作业 ({answer_count}/{len(questions)} 题)..."))
        score_rate = self._submit(item, recruit_id, answer_count)
        score_color = _C.GREEN if score_rate >= self._config.homework.threshold else _C.YELLOW
        print(f"  得分率: {styled(f'{score_rate:.1f}%', score_color)}")
        logger.info(f"作业 {item.exam_name}: 提交成功，得分率 {score_rate:.1f}%")
        return score_rate

    def _redo_homework(self, item: HomeworkItem, recruit_id: str) -> None:
        """重置作业状态（saveCourseTran），允许重新答题

        已提交的作业（state=4）直接调用 doHomework 会返回"试卷已提交"，
        需要先调用 saveCourseTran 重置状态。
        """
        logger.info(f"重置作业状态: {item.exam_name}")
        self._session.homework_redo(
            recruit_id=recruit_id,
            exam_id=item.exam_id,
            course_id=item.course_id,
        )

    def _fetch_homework_detail(self, item: HomeworkItem, recruit_id: str, school_id: str) -> HomeworkDetail:
        """调用 doHomework 获取题目详情"""
        result = self._session.homework_do(
            recruit_id=recruit_id,
            exam_id=item.exam_id,
            student_exam_id=item.id,
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

    def _generate_answer_with_llm(
        self,
        question: HomeworkQuestion,
        item: HomeworkItem,
        wrong_options: list[int] | None = None,
        ai_analysis: str | None = None,
    ) -> int | str | None:
        """使用 LLM 生成答案

        Args:
            question: 题目
            item: 作业项
            wrong_options: 已知错误选项 ID 列表
            ai_analysis: 缓存中的 AI 解析内容
        """
        qt = question.question_type
        question_text = _strip_html(question.name)
        all_options = question.question_options

        logger.debug(
            f"生成答案: 题型={qt}, 题目={question_text[:30]}, "
            f"总选项={len(all_options)}, 错误选项={wrong_options}, "
            f"AI分析={ai_analysis[:50] if ai_analysis else None}"
        )

        if self._llm is None:
            logger.debug("无 LLM，使用随机选择")
            return self._random_answer(question, wrong_options)

        # 多选题：不排除选项，把所有选项给 AI，只是告诉 AI 错误选项
        # 其他题型：排除错误选项后给 AI
        if qt == HomeworkQuestionType.MULTI:
            available_options = all_options
            logger.debug(f"多选题: 不排除选项，所有 {len(available_options)} 个选项给 AI")
        elif qt == HomeworkQuestionType.FILL:
            # 填空题无选项，直接调用 LLM
            available_options = []
            logger.debug("填空题: 无选项，直接调用 LLM")
        else:
            # 单选题/判断题：排除错误选项
            available_options = (
                [opt for opt in all_options if opt.id not in wrong_options] if wrong_options else all_options
            )
            logger.debug(f"可用选项数量: {len(available_options)}")

            if not available_options:
                logger.warning(f"所有选项都被标记为错误，无法生成答案: {question_text[:30]}")
                return None

        choices = [{"id": opt.id, "content": _strip_html(opt.content)} for opt in available_options]

        # 构建额外信息（包含错误选项提示和 AI 分析）
        extra: dict[str, str] = {"courseName": item.course_name}

        if wrong_options:
            # 提示 AI 已排除的错误选项
            wrong_labels = self._get_option_labels(all_options, wrong_options)
            extra["排除选项"] = f"以下选项已知是错误的，请勿选择: {wrong_labels}"
            logger.debug(f"排除选项提示: {wrong_labels}")

        if ai_analysis:
            extra["历史AI解析"] = f"之前 AI 对此题的分析（仅供参考）:\n{ai_analysis}"
            logger.debug(f"历史AI解析: {ai_analysis[:100]}")

        # 多选题：最多尝试 3 次，如果 AI 选了错误选项则 rollback
        max_retries = 3 if qt == HomeworkQuestionType.MULTI else 1

        for attempt in range(max_retries):
            try:
                if qt == HomeworkQuestionType.SINGLE:
                    ids = self._llm.single_choice(question_text, choices, extra=extra)
                    logger.debug(f"LLM 单选题返回: {ids}")
                    return ids[0] if ids else self._random_answer(question, wrong_options)
                elif qt == HomeworkQuestionType.MULTI:
                    ids = self._llm.multiple_choice(question_text, choices, extra=extra)
                    logger.debug(f"LLM 多选题返回 (尝试 {attempt + 1}/{max_retries}): {ids}")

                    if not ids:
                        logger.warning("LLM 多选题返回空，尝试随机选择")
                        return self._random_answer(question, wrong_options)

                    # 检查是否包含错误选项
                    if wrong_options and ids and ids == wrong_options:
                        wrong_chosen = [id_ for id_ in ids if id_ in wrong_options]
                        wrong_labels = self._get_option_labels(all_options, wrong_chosen)
                        logger.warning(
                            f"AI 选了错误选项 {wrong_labels}，rollback 并重新选择 (尝试 {attempt + 1}/{max_retries})"
                        )
                        # 继续下一次尝试
                        continue

                    return ",".join(str(i) for i in ids)
                elif qt == HomeworkQuestionType.JUDGE:
                    ids = self._llm.judgement(question_text, choices, extra=extra)
                    logger.debug(f"LLM 判断题返回: {ids}")
                    return ids[0] if ids else self._random_answer(question, wrong_options)
                elif qt == HomeworkQuestionType.FILL:
                    # 填空题：传递 AI 分析作为参考
                    answers = self._llm.fill_blank(question_text, extra=extra)
                    logger.debug(f"LLM 填空题返回: {answers}")
                    return ",".join(answers) if answers else None
                else:
                    logger.warning(f"未知题型 {qt}，随机选择")
                    return self._random_answer(question, wrong_options)
            except Exception as e:
                logger.error(f"LLM 生成答案失败: {e}")
                return self._random_answer(question, wrong_options)

        # 多选题尝试次数用尽，随机选择
        logger.error(f"多选题尝试 {max_retries} 次后仍选了错误选项，使用随机选择")
        return self._random_answer(question, wrong_options)

    def _random_answer(self, question: HomeworkQuestion, wrong_options: list[int] | None = None) -> int | str | None:
        """随机选择答案（无 LLM 时的兜底策略）

        Args:
            question: 题目
            wrong_options: 已知错误选项 ID 列表（可选）
        """
        qt = question.question_type
        all_options = question.question_options

        if qt in (HomeworkQuestionType.SINGLE, HomeworkQuestionType.JUDGE):
            # 单选/判断题：排除错误选项
            available = [opt for opt in all_options if opt.id not in wrong_options] if wrong_options else all_options
            logger.debug(f"随机答案: 题型={qt}, 总选项={len(all_options)}, 可用选项={len(available)}")
            if available:
                chosen = random.choice(available).id
                logger.debug(f"随机选择单选/判断题: {chosen}")
                return chosen
            logger.warning("单选/判断题无可用选项，无法随机选择")
            return None
        elif qt == HomeworkQuestionType.MULTI:
            # 多选题：不排除选项，从所有选项中随机选
            logger.debug(f"随机答案: 题型=多选, 总选项={len(all_options)}, 错误选项={wrong_options}")
            if len(all_options) >= 2:
                count = random.randint(2, len(all_options))
                chosen_ids = random.sample([o.id for o in all_options], count)
                result = ",".join(str(o) for o in sorted(chosen_ids))
                logger.debug(f"随机选择多选题: {result} (选了 {count} 个)")
                return result
            logger.warning(f"多选题选项不足 2 个 ({len(all_options)} 个)，无法随机选择")
            return None
        elif qt == HomeworkQuestionType.FILL:
            logger.debug("填空题无法随机选择")
            return None  # 填空题无法随机
        logger.warning(f"未知题型 {qt}，无法随机选择")
        return None

    def _save_ai_analysis_for_wrong(
        self,
        item: HomeworkItem,
        questions: list[HomeworkQuestion],
        answers: dict[str, HomeworkAnswerInfo],
        recruit_id: str,
    ) -> None:
        """为错题请求知到 AI 解析并保存到缓存

        调用知到内置 AI 解析 API（ai-course-assistant-api），
        使用 SSE 流式接口获取解析内容，保存到缓存的 ai_analysis 字段，
        下次重做时传递给 LLM 作为参考。

        Args:
            item: 作业项
            questions: 题目列表
            answers: 答案信息字典
            recruit_id: 招募 ID
        """
        wrong_questions = [
            (q, answers[str(q.id)])
            for q in questions
            if q.id is not None and str(q.id) in answers and answers[str(q.id)].is_wrong
        ]

        if not wrong_questions:
            return

        print(msg_info(f"请求 AI 解析 {len(wrong_questions)} 道错题..."))

        for question, _answer_info in wrong_questions:
            question_key = question.eid or (str(question.id) if question.id is not None else "")
            if not question_key:
                continue

            # 检查是否已有 AI 解析
            entry = self._cache.get(item.course_id, item.exam_id, question_key)
            if entry and entry.ai_analysis:
                logger.debug(f"题目 {question_key[:20]} 已有 AI 解析，跳过")
                continue

            # 使用数字型 question.id 调用知到 AI 解析 API
            if question.id is None:
                logger.debug(f"题目 {question_key[:20]} 无数字型 id，跳过 AI 解析")
                continue

            try:
                analysis = self._session.ai_analysis_run(
                    course_id=item.course_id,
                    recruit_id=recruit_id,
                    question_id=question.id,
                )
                if not analysis:
                    logger.debug(f"题目 {question_key[:20]} AI 解析为空，跳过")
                    continue

                logger.debug(f"AI 解析: {analysis[:100]}")

                # 保存到所有 key（eid + id）
                keys: list[str] = [question_key]
                if question.eid and question.id is not None:
                    keys.append(str(question.id))
                elif not question.eid and question.id is not None:
                    option_ids = [opt.id for opt in question.question_options]
                    if option_ids:
                        eid_key = self._cache.find_key_by_options(item.course_id, item.exam_id, option_ids)
                        if eid_key:
                            keys.append(eid_key)

                for key in keys:
                    self._cache.save_ai_analysis(item.course_id, item.exam_id, key, analysis)

            except Exception as e:
                logger.error(f"AI 解析失败 (题目 {question_key[:20]}): {e}")

    def _save_answer(
        self,
        question: HomeworkQuestion,
        answer: int | str,
        item: HomeworkItem,
        recruit_id: str,
        school_id: str,
    ) -> None:
        """保存单题答案（saveStudentAnswer）"""
        if not question.eid:
            raise ZhsError(f"题目无 eid，无法保存答案: {question.name[:30]}")

        answer_item: dict[str, Any] = {
            "examId": item.exam_id,
            "recruitId": recruit_id,
            "stuExamId": item.id,
            "eid": question.eid,
            "schoolId": school_id,
            "deviceId": "",
            "examType": "",
            "fromType": 3,
            "answer": answer,
            "dataIds": "",
            "questionType": question.question_type_id,
        }

        try:
            self._session.homework_save_answer(answer_item, recruit_id)
        except Exception as e:
            error_msg = str(e)
            if "滑块" in error_msg or "验证" in error_msg:
                msg = (
                    f"作业 {item.exam_name} 需要滑块验证，请在浏览器中手动完成验证后重试。\n"
                    f"  1. 打开浏览器登录智慧树，进入该作业页面\n"
                    f"  2. 完成滑块验证\n"
                    f"  3. 重新运行程序"
                )
                print(f"\n⚠️ {msg}")
                logger.warning(msg)
                raise SliderVerificationRequired(msg) from e
            raise

    def _submit(self, item: HomeworkItem, recruit_id: str, answer_count: int) -> float:
        """提交作业，返回得分率（0-100）"""
        result = self._session.homework_submit(
            recruit_id=recruit_id,
            exam_id=item.exam_id,
            stu_exam_id=item.id,
            achieve_count=answer_count,
        )

        rt = result.get("rt", {})
        score_str = rt.get("score", "0")

        try:
            score = float(score_str)
        except (ValueError, TypeError):
            score = 0.0

        total = float(item.total_score) if item.total_score else 0.0
        if total <= 0:
            return 100.0

        return (score / total) * 100

    def _save_options_to_cache(self, question: HomeworkQuestion, item: HomeworkItem) -> None:
        """保存题目选项到缓存（首次做时调用）"""
        question_key = question.eid or (str(question.id) if question.id is not None else "")
        if not question_key:
            return

        options = [
            HomeworkCacheOption(id=opt.id, content=_strip_html(opt.content)) for opt in question.question_options
        ]
        self._cache.save_options(
            course_id=item.course_id,
            exam_id=item.exam_id,
            question_key=question_key,
            question_type=question.question_type_id,
            options=options,
        )

    def _get_question_type_name(self, qt_id: int) -> str:
        """获取题型名称"""
        names: dict[int, str] = {
            HomeworkQuestionType.SINGLE: "单选",
            HomeworkQuestionType.MULTI: "多选",
            HomeworkQuestionType.FILL: "填空",
            HomeworkQuestionType.JUDGE: "判断",
        }
        return names.get(qt_id, f"未知({qt_id})")

    def _generate_answer_with_source(
        self, question: HomeworkQuestion, item: HomeworkItem
    ) -> tuple[int | str | None, str]:
        """为单题生成答案，同时返回答案来源

        Returns:
            (答案, 来源描述)
            来源: "缓存正确" / "缓存排除直接" / "缓存排除AI" / "LLM" / "随机" / "无LLM随机"
        """
        question_key = question.eid or (str(question.id) if question.id is not None else "")
        if not question_key:
            logger.warning("题目无 eid 也无 id，无法生成答案")
            return None, "无ID"

        course_id = item.course_id
        exam_id = item.exam_id

        logger.debug(
            f"生成答案来源: question_key={question_key}, "
            f"题型={question.question_type}, 选项数={len(question.question_options)}"
        )

        # 1. 检查缓存中的正确选项
        correct = self._cache.get_correct_options(course_id, exam_id, question_key)
        if correct:
            logger.debug(f"缓存有正确选项: {correct}")
            qt = question.question_type
            if qt == HomeworkQuestionType.MULTI:
                return ",".join(str(o) for o in correct), "缓存正确"
            return correct[0], "缓存正确"

        # 2. 获取错误选项和 AI 分析
        wrong = self._cache.get_wrong_options(course_id, exam_id, question_key)
        entry = self._cache.get(course_id, exam_id, question_key)
        ai_analysis = entry.ai_analysis if entry else None

        logger.debug(f"缓存错误选项: {wrong}, AI分析: {ai_analysis[:50] if ai_analysis else None}")

        # 3. 根据题型和缓存情况决定策略
        qt = question.question_type
        options = question.question_options

        # 判断题：已知一个错误选项，直接选另一个
        if qt == HomeworkQuestionType.JUDGE and wrong and len(options) == 2:
            available = [opt.id for opt in options if opt.id not in wrong]
            logger.debug(f"判断题缓存排除: 可用选项={available}")
            if len(available) == 1:
                return available[0], "缓存排除直接"

        # 单选题（选项=2）：排除一个后只剩一个，直接选
        if qt == HomeworkQuestionType.SINGLE and wrong and len(options) == 2:
            available = [opt.id for opt in options if opt.id not in wrong]
            logger.debug(f"单选题缓存排除: 可用选项={available}")
            if len(available) == 1:
                return available[0], "缓存排除直接"

        # 其他情况：调用 AI，传递错误选项和 AI 分析
        logger.debug(f"调用 LLM: wrong={wrong}, ai_analysis={ai_analysis[:50] if ai_analysis else None}")
        answer = self._generate_answer_with_llm(question, item, wrong_options=wrong, ai_analysis=ai_analysis)
        if answer is not None:
            logger.debug(f"LLM 返回答案: {answer}")
            if self._llm is None:
                return answer, "无LLM随机"
            if wrong:
                return answer, "缓存排除AI"
            return answer, "LLM"

        logger.warning(f"无法生成答案: question_key={question_key}, 题型={qt}")
        return None, "无法生成"

    def _format_answer_display(self, answer: int | str, question: HomeworkQuestion) -> str:
        """格式化答案显示，将选项 ID 转换为选项内容"""
        if answer is None:
            return "无"

        # 填空题直接返回答案
        if question.question_type == HomeworkQuestionType.FILL:
            return str(answer)

        # 选择题/判断题：将 ID 转换为选项标签 (A/B/C/D)
        options = question.question_options
        if not options:
            return str(answer)

        # 构建选项 ID -> 标签的映射
        id_to_label: dict[int, str] = {}
        labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for i, opt in enumerate(options):
            if i < len(labels):
                id_to_label[opt.id] = labels[i]

        # 解析答案（可能是单个 ID 或逗号分隔的多个 ID）
        if isinstance(answer, int):
            return id_to_label.get(answer, str(answer))
        else:
            # 多选题答案格式: "1,2,3"
            try:
                ids = [int(x) for x in str(answer).split(",")]
                labels_str = [id_to_label.get(id, str(id)) for id in ids]
                return ",".join(labels_str)
            except ValueError:
                return str(answer)

    def _style_source(self, source: str) -> str:
        """美化答案来源显示"""
        if source == "缓存正确":
            return styled(source, _C.GREEN)
        elif source in ("缓存排除直接", "缓存排除AI"):
            return styled(source, _C.YELLOW)
        elif source == "LLM":
            return styled(source, _C.BRIGHT_MAGENTA)
        elif source == "无LLM随机":
            return styled(source, _C.DIM)
        else:
            return styled(source, _C.WHITE)

    def _get_option_labels(self, options: list[HomeworkQuestionOption], ids: list[int]) -> str:
        """将选项 ID 转换为标签字符串（如 A, B, C）

        Args:
            options: 选项列表
            ids: 需要转换的选项 ID 列表

        Returns:
            标签字符串，如 "A, B" 或 "C"
        """
        id_to_label: dict[int, str] = {}
        labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for i, opt in enumerate(options):
            if i < len(labels):
                id_to_label[opt.id] = labels[i]

        result = [id_to_label.get(id, str(id)) for id in ids]
        return ", ".join(result)

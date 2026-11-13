"""知识图谱课章节测验处理器

处理知识图谱课节点的章节测验（知识点掌握度）。
"""

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from zhs.config import HomeworkConfig
from zhs.exceptions import ApiError
from zhs.question_bank.client import QuestionBankClient
from zhs.utils.display import msg_done, msg_error, msg_skip, msg_warn

if TYPE_CHECKING:
    from zhs.session import ZhsSession
    from zhs.zhidao.models import MapLesson


class KgExamHandler:
    """知识图谱课章节测验处理器"""

    def __init__(
        self,
        session: "ZhsSession",
        homework_config: HomeworkConfig,
        question_bank: QuestionBankClient | None = None,
    ) -> None:
        self._session = session
        self._config = homework_config
        self._qb = question_bank

    def try_handle_exam(
        self,
        recruit_id: str,
        lesson: "MapLesson",
        print_callback: Any = None,
    ) -> bool:
        """尝试处理节点的章节测验（如果有）

        Args:
            recruit_id: 招募 ID
            lesson: 知识图谱节点
            print_callback: 打印回调函数（用于显示进度）

        Returns:
            是否成功处理了章节测验（如果节点没有测验，返回 True）
        """
        if not self._config.enable_kg_exam:
            return True

        knowledge_id = lesson.id_hash

        # 尝试开始答题
        try:
            exam_data = self._session.kg_exam_start(recruit_id, 0, knowledge_id)
        except ApiError as e:
            # 如果节点没有章节测验，API 会返回错误，这是正常情况
            if e.code in [500, 404]:  # 常见的"无测验"错误码
                return True
            logger.warning(f"检查章节测验失败: {e}")
            return True
        except Exception as e:
            logger.warning(f"检查章节测验异常: {e}")
            return True

        exam_id = exam_data.get("examId")
        questions = exam_data.get("questions", [])

        if not questions:
            return True

        if print_callback:
            print_callback(f"发现章节测验: {len(questions)} 题", depth=3)

        # 执行答题流程（带重试）
        for retry in range(self._config.kg_exam_max_retries + 1):
            try:
                mastery_info = self._do_exam_once(
                    recruit_id=recruit_id,
                    exam_id=exam_id,
                    knowledge_id=knowledge_id,
                    questions=questions,
                    print_callback=print_callback,
                )

                rate = int(mastery_info.get("rate", 0))

                if rate >= self._config.kg_exam_threshold:
                    if print_callback:
                        print_callback(msg_done(f"掌握度达标: {rate}% (阈值={self._config.kg_exam_threshold}%)"), depth=3)
                    return True

                if retry < self._config.kg_exam_max_retries:
                    if print_callback:
                        print_callback(
                            msg_warn(f"掌握度 {rate}% 低于阈值，重试 {retry + 1}/{self._config.kg_exam_max_retries}"),
                            depth=3,
                        )
                    time.sleep(1)
                else:
                    if print_callback:
                        print_callback(
                            msg_warn(f"掌握度 {rate}% 未达标，已达最大重试次数"),
                            depth=3,
                        )
                    return False

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"章节测验失败: {e}")
                if print_callback:
                    print_callback(msg_error(f"章节测验失败: {e}"), depth=3)
                return False

        return False

    def _do_exam_once(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
        questions: list[dict[str, Any]],
        print_callback: Any = None,
    ) -> dict[str, Any]:
        """执行一次章节测验（查题库/AI -> 提交 -> 查掌握度）

        Returns:
            掌握度信息 dict
        """
        answers = []

        for q in questions:
            question_id = q["questionId"]
            question_type = q["questionType"]
            question_name = q["questionName"]
            options = q.get("optionVos", [])

            # 查询答案
            answer_result = self._get_answer(question_name, options, question_type)

            if not answer_result:
                # 没有答案，使用默认策略（单选/判断选第一个，多选全选）
                if question_type in [1, 14]:
                    answer = options[0]["id"] if options else 0
                elif question_type == 2:
                    answer = ",".join(str(opt["id"]) for opt in options)
                else:
                    continue
            else:
                # 构造答案格式
                if question_type == 2:  # 多选
                    # 答案是选项内容列表，需要转为选项 ID 字符串
                    answer_ids = [str(opt["id"]) for opt in options if opt["name"] in answer_result]
                    answer = ",".join(answer_ids) if answer_ids else str(options[0]["id"])
                else:  # 单选或判断
                    # 答案是选项内容，需要转为选项 ID
                    answer = next(
                        (opt["id"] for opt in options if opt["name"] == answer_result),
                        options[0]["id"] if options else 0,
                    )

            answers.append({"questionId": question_id, "answer": answer})

        # 提交答案
        submit_ok = self._session.kg_exam_submit(recruit_id, exam_id, knowledge_id, answers)
        if not submit_ok:
            raise ApiError(-1, "提交答案失败")

        # 查询掌握度
        mastery_info = self._session.kg_exam_get_mastery_info(recruit_id, exam_id, knowledge_id)
        return mastery_info

    def _get_answer(
        self,
        question_name: str,
        options: list[dict[str, Any]],
        question_type: int,
    ) -> Any:
        """查询答案（题库或 AI）

        Returns:
            单选/判断: 选项内容字符串
            多选: 选项内容列表
            None: 没有找到答案
        """
        if not self._qb:
            return None

        try:
            # 使用题库查询
            result = self._qb.search_answer(
                question=question_name,
                options=[opt["name"] for opt in options],
                question_type=question_type,
            )
            return result
        except Exception as e:
            logger.debug(f"题库查询失败: {e}")
            return None

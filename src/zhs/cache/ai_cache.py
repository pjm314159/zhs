"""AI 作业/考试缓存 — 继承 BaseQuestionCache

缓存路径: {cache_dir}/ai/{course_id}/{exam_id}.json
缓存格式: {question_id_str: {question, answer, answer_content, questionDict}, ...}

HomeworkCtx 与 ExamCtx 共用此缓存（通过 exam_id 区分）。
"""

from __future__ import annotations

from typing import Any

from zhs.cache.base import BaseQuestionCache


class AiExamCache(BaseQuestionCache[dict[str, Any]]):
    """AI 作业/考试缓存

    条目格式: {"question": str, "answer": str, "answer_content": str, "questionDict": dict}
    key 为 question_id 的字符串形式。
    """

    course_type = "ai"

    def _deserialize_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        return dict(data)

    def _serialize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        return dict(entry)

    # --- 公共 API ---

    def get(self, course_id: int | str, exam_id: int | str, question_id: int) -> dict[str, Any] | None:
        """获取缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        return entries.get(str(question_id))

    def put(
        self,
        course_id: int | str,
        exam_id: int | str,
        question_id: int,
        entry: dict[str, Any],
    ) -> None:
        """写入缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        entries[str(question_id)] = entry
        self._save_exam(course_id, exam_id, entries)

    def load_all_for_course(self, course_id: int | str) -> dict[str, dict[str, Any]]:
        """加载课程下所有 exam 的缓存（合并）

        用于构建 _all_answer_cache：扫描课程目录下所有 JSON 文件并合并。
        """
        return self._load_all_exams(course_id)

    @staticmethod
    def parse_answer(answer_str: str) -> list[str] | None:
        """解析缓存中的 answer 字段

        - 含 #@# → 按 #@# 分隔（多选题选项 ID）
        - 不含 #@# → 返回单元素列表（单选/判断/填空题）
        填空题多个空用 / 合并存储，不拆分。
        """
        if not answer_str:
            return None
        if "#@#" in answer_str:
            return answer_str.split("#@#")
        return [answer_str]

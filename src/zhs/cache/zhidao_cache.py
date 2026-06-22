"""知到作业缓存 — 继承 BaseQuestionCache

缓存路径: {cache_dir}/zhidao/{course_id}/{exam_id}.json
缓存格式: {question_key: HomeworkCacheEntry_dict, ...}

与旧 HomeworkCache 的差异：
- 路径从 zhidao_homework_cache/ 改为 zhidao/
- key 从 courseId:examId:questionKey 改为纯 question_key
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from zhs.cache.base import BaseQuestionCache
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption


def _now_str() -> str:
    """当前时间 ISO 格式字符串"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class ZhidaoHomeworkCache(BaseQuestionCache[HomeworkCacheEntry]):
    """知到作业答案本地缓存"""

    course_type = "zhidao"

    def _deserialize_entry(self, data: dict[str, Any]) -> HomeworkCacheEntry:
        return HomeworkCacheEntry.model_validate(data)

    def _serialize_entry(self, entry: HomeworkCacheEntry) -> dict[str, Any]:
        return entry.model_dump(by_alias=True)

    # --- 公共 API ---

    def get(self, course_id: int, exam_id: str, question_key: str) -> HomeworkCacheEntry | None:
        """获取缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        return entries.get(question_key)

    def put(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        entry: HomeworkCacheEntry,
    ) -> None:
        """写入缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        entries[question_key] = entry
        self._save_exam(course_id, exam_id, entries)

    def mark_correct(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        option_ids: list[int],
    ) -> None:
        """标记正确选项"""
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(questionType=0, lastUpdated=_now_str())
        # 合并正确选项（去重）
        correct = set(entry.correct_options) | set(option_ids)
        # 从错误选项中移除已确认正确的
        wrong = set(entry.wrong_options) - correct
        entry.correct_options = sorted(correct)
        entry.wrong_options = sorted(wrong)
        entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def mark_wrong(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        option_ids: list[int],
    ) -> None:
        """标记错误选项"""
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(questionType=0, lastUpdated=_now_str())
        # 合并错误选项（去重）
        wrong = set(entry.wrong_options) | set(option_ids)
        # 从正确选项中移除已确认错误的
        correct = set(entry.correct_options) - wrong
        entry.wrong_options = sorted(wrong)
        entry.correct_options = sorted(correct)
        entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def get_correct_options(self, course_id: int, exam_id: str, question_key: str) -> list[int]:
        """获取已知正确选项"""
        entry = self.get(course_id, exam_id, question_key)
        return entry.correct_options if entry else []

    def get_wrong_options(self, course_id: int, exam_id: str, question_key: str) -> list[int]:
        """获取已知错误选项"""
        entry = self.get(course_id, exam_id, question_key)
        return entry.wrong_options if entry else []

    def save_ai_analysis(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        ai_analysis: str,
    ) -> None:
        """保存 AI 解析内容到缓存"""
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(questionType=0, lastUpdated=_now_str())
        entry.ai_analysis = ai_analysis
        entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def save_options(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        question_type: int,
        options: list[HomeworkCacheOption],
    ) -> None:
        """保存题目选项信息（首次做作业时调用）"""
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(
                questionType=question_type,
                options=options,
                lastUpdated=_now_str(),
            )
        else:
            entry.question_type = question_type
            if not entry.options:
                entry.options = options
            entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def find_key_by_options(
        self,
        course_id: int,
        exam_id: str,
        option_ids: list[int],
    ) -> str | None:
        """通过选项 ID 集合查找缓存中对应的 question key

        用于在 lookHomework 返回数字型 id 时，通过选项匹配找到对应的 eid key。
        因为 doHomework 和 lookHomework 返回的选项 ID 相同，可以借此关联 eid 和 id。

        Returns:
            匹配到的 question key，未找到返回 None
        """
        entries = self._load_exam(course_id, exam_id)
        option_set = set(option_ids)
        for question_key, entry in entries.items():
            if entry.options:
                entry_option_ids = {opt.id for opt in entry.options}
                if entry_option_ids == option_set:
                    return question_key
        return None

    def load_all_for_course(self, course_id: int) -> dict[str, HomeworkCacheEntry]:
        """加载课程下所有 exam 的缓存（合并）"""
        return self._load_all_exams(course_id)

    # --- 保留 dict 兼容接口（供 _serialize_entry 内部使用） ---

    def _entry_to_dict(self, entry: HomeworkCacheEntry) -> dict[str, Any]:
        """条目转 dict（兼容旧代码）"""
        return self._serialize_entry(entry)

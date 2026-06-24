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
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption, WrongOption


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
        """标记正确选项

        - 合并到 correct_options（扁平 list[int]，去重）
        - 移除与正确选项完全匹配的错误组合
        """
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(questionType=0, lastUpdated=_now_str())
        correct = set(entry.correct_options) | set(option_ids)
        entry.correct_options = sorted(correct)
        # 移除与正确答案完全匹配的错误组合（仅选择题，填空题不会调用 mark_correct）
        correct_set = set(option_ids)
        entry.wrong_options = [
            c
            for c in entry.wrong_options
            if not (isinstance(c, list) and c and isinstance(c[0], int) and set(c) == correct_set)
        ]
        entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def mark_wrong(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        answer: list[int] | list[str],
    ) -> None:
        """标记错误选择方式

        - 选择题: answer 为 list[int]（一次完整选择），追加到 wrong_options，不合并
        - 填空题: answer 为 list[str]（每空一个元素），追加到 wrong_options
        - 去重：已存在的相同组合不重复追加
        """
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(questionType=0, lastUpdated=_now_str())

        # 统一处理：按类型分组去重后追加
        if answer:
            if isinstance(answer[0], int):
                # 选择题：排序后比较
                new_combo = sorted(answer)
                existing_int: list[list[int]] = [
                    sorted(c) for c in entry.wrong_options if isinstance(c, list) and c and isinstance(c[0], int)
                ]
                if new_combo not in existing_int:
                    entry.wrong_options.append(new_combo)
            else:
                # 填空题：直接比较（保持顺序）
                existing_str: list[list[str]] = [
                    c for c in entry.wrong_options if isinstance(c, list) and c and isinstance(c[0], str)
                ]
                if list(answer) not in existing_str:
                    entry.wrong_options.append(list(answer))

        entry.last_updated = _now_str()
        self.put(course_id, exam_id, question_key, entry)

    def get_correct_options(self, course_id: int, exam_id: str, question_key: str) -> list[int]:
        """获取已知正确选项"""
        entry = self.get(course_id, exam_id, question_key)
        return entry.correct_options if entry else []

    def get_wrong_options(self, course_id: int, exam_id: str, question_key: str) -> list[WrongOption]:
        """获取已知错误选择方式列表"""
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
        content: str = "",
    ) -> None:
        """保存题目选项信息（首次做作业时调用）

        Args:
            content: 题目纯文本内容（用于无选项题目的 id→eid 桥接）
        """
        entry = self.get(course_id, exam_id, question_key)
        if entry is None:
            entry = HomeworkCacheEntry(
                questionType=question_type,
                content=content,
                options=options,
                lastUpdated=_now_str(),
            )
        else:
            entry.question_type = question_type
            if content:
                entry.content = content
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

        用于 eid ↔ id 桥接：doHomework 和 lookHomework 返回的选项 ID 相同。
        优先返回数字型 key（id），因为对错信息以 id 为首要 key 保存。

        Returns:
            匹配到的 question key，未找到返回 None
        """
        entries = self._load_exam(course_id, exam_id)
        option_set = set(option_ids)
        matched_numeric: str | None = None
        matched_other: str | None = None
        for question_key, entry in entries.items():
            if entry.options:
                entry_option_ids = {opt.id for opt in entry.options}
                if entry_option_ids == option_set:
                    if question_key.isdigit():
                        matched_numeric = question_key
                    else:
                        matched_other = question_key
        # 优先返回数字型 key（id 为首要 key）
        return matched_numeric or matched_other

    def find_key_by_content(
        self,
        course_id: int,
        exam_id: str,
        content: str,
    ) -> str | None:
        """通过题目纯文本内容查找缓存中对应的 question key

        用于无选项题目（如填空题）的 eid ↔ id 桥接。
        优先返回数字型 key（id 为首要 key）。

        Returns:
            匹配到的 question key，未找到返回 None
        """
        if not content:
            return None
        entries = self._load_exam(course_id, exam_id)
        matched_numeric: str | None = None
        matched_other: str | None = None
        for question_key, entry in entries.items():
            if entry.content and entry.content == content:
                if question_key.isdigit():
                    matched_numeric = question_key
                else:
                    matched_other = question_key
        return matched_numeric or matched_other

    def load_all_for_course(self, course_id: int) -> dict[str, HomeworkCacheEntry]:
        """加载课程下所有 exam 的缓存（合并）"""
        return self._load_all_exams(course_id)

    # --- 保留 dict 兼容接口（供 _serialize_entry 内部使用） ---

    def _entry_to_dict(self, entry: HomeworkCacheEntry) -> dict[str, Any]:
        """条目转 dict（兼容旧代码）"""
        return self._serialize_entry(entry)

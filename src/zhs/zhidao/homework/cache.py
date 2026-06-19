"""知到作业本地缓存管理

提供 HomeworkCache 类，管理作业答案的本地 JSON 缓存。
缓存 key 格式: courseId:examId:questionKey（questionKey 为 eid 或数字型 id）
缓存文件路径: .zhs/cache/zhidao_homework_cache/{courseId}/{examId}.json
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from zhs.utils.path import get_data_dir
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption


class HomeworkCache:
    """作业答案本地缓存"""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or get_data_dir() / "cache" / "zhidao_homework_cache"
        self._loaded: dict[str, dict[str, HomeworkCacheEntry]] = {}

    def get(self, course_id: int, exam_id: str, question_key: str) -> HomeworkCacheEntry | None:
        """获取缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        cache_key = f"{course_id}:{exam_id}:{question_key}"
        return entries.get(cache_key)

    def put(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        entry: HomeworkCacheEntry,
    ) -> None:
        """写入缓存条目"""
        entries = self._load_exam(course_id, exam_id)
        cache_key = f"{course_id}:{exam_id}:{question_key}"
        entries[cache_key] = entry
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

        Args:
            course_id: 课程 ID
            exam_id: 考试 ID
            option_ids: 选项 ID 列表

        Returns:
            匹配到的 question key（通常是 eid），未找到返回 None
        """
        entries = self._load_exam(course_id, exam_id)
        option_set = set(option_ids)
        for cache_key, entry in entries.items():
            # 提取 key 部分（去掉 courseId:examId: 前缀）
            parts = cache_key.split(":", 2)
            if len(parts) < 3:
                continue
            key = parts[2]
            # 检查选项是否匹配
            if entry.options:
                entry_option_ids = {opt.id for opt in entry.options}
                if entry_option_ids == option_set:
                    return key
        return None

    def _cache_path(self, course_id: int, exam_id: str) -> Path:
        """缓存文件路径: .zhs/cache/zhidao_homework_cache/{courseId}/{examId}.json"""
        return self._cache_dir / str(course_id) / f"{exam_id}.json"

    def _load_exam(self, course_id: int, exam_id: str) -> dict[str, HomeworkCacheEntry]:
        """加载某个 exam 的缓存（惰性加载）"""
        exam_key = f"{course_id}:{exam_id}"
        if exam_key in self._loaded:
            return self._loaded[exam_key]

        path = self._cache_path(course_id, exam_id)
        entries: dict[str, HomeworkCacheEntry] = {}

        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for key, value in data.items():
                    entries[key] = HomeworkCacheEntry.model_validate(value)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to load homework cache {path}: {e}")

        self._loaded[exam_key] = entries
        return entries

    def _save_exam(self, course_id: int, exam_id: str, entries: dict[str, HomeworkCacheEntry]) -> None:
        """保存某个 exam 的缓存"""
        path = self._cache_path(course_id, exam_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {key: entry.model_dump(by_alias=True) for key, entry in entries.items()}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Failed to save homework cache {path}: {e}")


def _now_str() -> str:
    """当前时间 ISO 格式字符串"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

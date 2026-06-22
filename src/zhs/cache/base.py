"""缓存基类 — 统一缓存路径与持久化逻辑

缓存路径: {cache_dir}/{course_type}/{course_id}/{exam_id}.json
缓存格式: {question_key: entry_dict, ...}

子类需:
1. 设置 course_type 类属性
2. 实现 _deserialize_entry / _serialize_entry
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from loguru import logger

from zhs.utils.path import get_data_dir


class BaseQuestionCache[T](ABC):
    """题目缓存基类

    子类通过设置 course_type 与实现序列化方法，复用路径管理与持久化逻辑。
    """

    course_type: str = ""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or get_data_dir() / "cache"
        self._loaded: dict[str, dict[str, T]] = {}

    def _cache_path(self, course_id: int | str, exam_id: int | str) -> Path:
        """缓存文件路径: {cache_dir}/{course_type}/{course_id}/{exam_id}.json"""
        return self._cache_dir / self.course_type / str(course_id) / f"{exam_id}.json"

    def _load_exam(self, course_id: int | str, exam_id: int | str) -> dict[str, T]:
        """加载某个 exam 的缓存（惰性加载）"""
        exam_key = f"{course_id}:{exam_id}"
        if exam_key in self._loaded:
            return self._loaded[exam_key]

        path = self._cache_path(course_id, exam_id)
        entries: dict[str, T] = {}

        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        entries[key] = self._deserialize_entry(value)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to load cache {path}: {e}")

        self._loaded[exam_key] = entries
        return entries

    def _save_exam(self, course_id: int | str, exam_id: int | str, entries: dict[str, T]) -> None:
        """保存某个 exam 的缓存"""
        path = self._cache_path(course_id, exam_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {key: self._serialize_entry(entry) for key, entry in entries.items()}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Failed to save cache {path}: {e}")

    def _load_all_exams(self, course_id: int | str) -> dict[str, T]:
        """加载课程下所有 exam 的缓存（合并）"""
        course_dir = self._cache_dir / self.course_type / str(course_id)
        if not course_dir.exists():
            return {}

        merged: dict[str, T] = {}
        for json_file in course_dir.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, dict):
                            merged[key] = self._deserialize_entry(value)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Failed to load cache {json_file}: {e}")
        return merged

    @abstractmethod
    def _deserialize_entry(self, data: dict[str, Any]) -> T:
        """反序列化条目"""
        ...

    @abstractmethod
    def _serialize_entry(self, entry: T) -> dict[str, Any]:
        """序列化条目"""
        ...

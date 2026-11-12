"""知到共享课学习计划：首日刷大部分，剩余平均分到之后每天

学习习惯分看的是“每天都在学”，单日学得太短不会被记为学过（用户实测：一天累计几分钟没记上），
所以之后每天至少 MIN_DAILY_MINUTES 分钟。计划按课程独立计算，状态保存在数据目录下：

    first_day   第一次运行的日期（这天刷大部分）
    days        {"YYYY-MM-DD": 当天已学秒数}，跨多次运行累计

预算的单位是真实经过的秒数（与 ctx.fucked_time 一致）。
"""

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from loguru import logger

# 之后每天至少学多少分钟（单日太短不被记为学过）
MIN_DAILY_MINUTES = 30
# 之后每天的目标分钟数（剩余平均分摊，不低于 MIN_DAILY_MINUTES）
DEFAULT_DAILY_MINUTES = 40


@dataclass(frozen=True)
class DailyPlan:
    """今天的学习预算"""

    budget_seconds: int  # 今天还能学的秒数；0 表示今天已完成
    is_first_day: bool
    remaining_days: int  # 含今天在内到截止日还剩几天
    daily_seconds: int  # 之后每天的配额

    def describe(self, remaining_minutes: int = 0) -> str:
        """返回计划描述

        Args:
            remaining_minutes: 课程剩余分钟数（用于建议每天学习时长）
        """
        if self.budget_seconds <= 0:
            return f"今天的学习时长已完成（之后每天 {self.daily_seconds // 60} 分钟）"
        head = "首日，刷大部分" if self.is_first_day else "按计划"
        daily = self.daily_seconds // 60
        msg = f"{head}：今天学 {self.budget_seconds // 60} 分钟，之后每天 {daily} 分钟，剩 {self.remaining_days} 天"
        if remaining_minutes > 0 and self.remaining_days > 0:
            suggest = (remaining_minutes + self.remaining_days - 1) // self.remaining_days
            if suggest != daily:
                msg += f"（建议每天 {suggest} 分钟可按时完成）"
        return msg


def plan_today(
    *,
    remaining_seconds: int,
    today: date,
    first_day: date,
    end_day: date | None,
    studied_today: int,
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
) -> DailyPlan:
    """计算今天的学习预算

    Args:
        remaining_seconds: 课程还需观看的秒数（所有未完成视频之和）
        today: 今天
        first_day: 计划开始的日期（首日）
        end_day: 课程学习截止日；None 时不考虑截止
        studied_today: 今天已经学过的秒数（之前几次运行累计）
        daily_minutes: 之后每天的目标分钟数，不低于 MIN_DAILY_MINUTES
    """
    daily = max(daily_minutes, MIN_DAILY_MINUTES) * 60
    days_left = (end_day - today).days + 1 if end_day else None  # 含今天
    is_first = today <= first_day

    if remaining_seconds <= 0:
        return DailyPlan(0, is_first, max(days_left or 0, 0), daily)

    if days_left is not None and days_left <= 1:
        # 最后一天：剩多少学多少，截止后学习不记进度
        budget = remaining_seconds
    elif is_first:
        # 首日：留够之后每天 daily 秒的量，其余今天学完
        later_days = (days_left - 1) if days_left is not None else 0
        budget = max(remaining_seconds - later_days * daily, 0)
        # 首日至少也按一天的配额学（保证当天被记为学过）
        budget = max(budget, min(daily, remaining_seconds))
    else:
        # 之后每天：剩余平均分摊，不低于 daily
        per_day = math.ceil(remaining_seconds / days_left) if days_left else daily
        budget = min(max(per_day, daily), remaining_seconds)

    return DailyPlan(max(budget - studied_today, 0), is_first, max(days_left or 0, 0), daily)


class StudyLedger:
    """按课程记录每天已学秒数（跨多次运行累计）"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _course(self, key: str) -> dict[str, Any]:
        course = self._data.get(key)
        if not isinstance(course, dict):
            course = {}
            self._data[key] = course
        if not isinstance(course.get("days"), dict):
            course["days"] = {}
        return course

    def first_day(self, key: str, today: date) -> date:
        """课程计划的首日；第一次调用时记为今天"""
        course = self._course(key)
        if "first_day" not in course:
            course["first_day"] = today.isoformat()
            self.save()
        try:
            return date.fromisoformat(course["first_day"])
        except (TypeError, ValueError):
            return today

    def studied(self, key: str, day: date) -> int:
        return int(self._course(key)["days"].get(day.isoformat(), 0))

    def add(self, key: str, day: date, seconds: int) -> None:
        if seconds <= 0:
            return
        days = self._course(key)["days"]
        days[day.isoformat()] = int(days.get(day.isoformat(), 0)) + int(seconds)
        self.save()

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"学习记录保存失败: {exc}")


def end_date_from_ms(end_ms: int | None) -> date | None:
    """毫秒时间戳 → 本地日期"""
    if not end_ms or end_ms <= 0:
        return None
    return datetime.fromtimestamp(end_ms / 1000).date()

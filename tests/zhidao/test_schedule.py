"""知到学习计划：首日刷大部分，之后每天平均分摊、每天至少 30 分钟"""

from datetime import date
from pathlib import Path

import pytest

from zhs.zhidao.schedule import MIN_DAILY_MINUTES, StudyLedger, end_date_from_ms, plan_today

TODAY = date(2026, 11, 12)
END = date(2026, 11, 26)  # 军事理论学习截止（courseEndTime 2026-11-26 23:59:59）


class TestPlanToday:
    def test_first_day_does_most_and_leaves_daily_quota(self) -> None:
        """首日：留够之后 14 天 × 40 分钟，其余今天学完"""
        remaining = 20 * 3600  # 20 小时
        plan = plan_today(remaining_seconds=remaining, today=TODAY, first_day=TODAY, end_day=END, studied_today=0)
        later = 14 * 40 * 60
        assert plan.is_first_day
        assert plan.remaining_days == 15
        assert plan.budget_seconds == remaining - later

    def test_first_day_at_least_one_daily_quota(self) -> None:
        """剩余很少时首日也至少学一天的配额（保证当天被记为学过）"""
        plan = plan_today(remaining_seconds=3 * 3600, today=TODAY, first_day=TODAY, end_day=END, studied_today=0)
        assert plan.budget_seconds == 40 * 60

    def test_later_day_uses_daily_minutes(self) -> None:
        plan = plan_today(
            remaining_seconds=5 * 3600, today=date(2026, 11, 13), first_day=TODAY, end_day=END, studied_today=0
        )
        assert not plan.is_first_day
        assert plan.budget_seconds == 40 * 60

    def test_later_day_spreads_when_behind(self) -> None:
        """落后时把剩余平均分到剩下的天数，超过默认配额"""
        plan = plan_today(
            remaining_seconds=10 * 3600, today=date(2026, 11, 22), first_day=TODAY, end_day=END, studied_today=0
        )
        assert plan.remaining_days == 5
        assert plan.budget_seconds == 2 * 3600

    def test_never_more_than_remaining(self) -> None:
        plan = plan_today(
            remaining_seconds=600, today=date(2026, 11, 13), first_day=TODAY, end_day=END, studied_today=0
        )
        assert plan.budget_seconds == 600

    def test_last_day_finishes_everything(self) -> None:
        plan = plan_today(remaining_seconds=5 * 3600, today=END, first_day=TODAY, end_day=END, studied_today=0)
        assert plan.budget_seconds == 5 * 3600

    def test_studied_today_counts_across_runs(self) -> None:
        """同一天第二次运行：扣掉已学的"""
        plan = plan_today(
            remaining_seconds=5 * 3600, today=date(2026, 11, 13), first_day=TODAY, end_day=END, studied_today=25 * 60
        )
        assert plan.budget_seconds == 15 * 60

    def test_done_for_today(self) -> None:
        plan = plan_today(
            remaining_seconds=5 * 3600, today=date(2026, 11, 13), first_day=TODAY, end_day=END, studied_today=45 * 60
        )
        assert plan.budget_seconds == 0
        assert "已完成" in plan.describe()

    def test_daily_minutes_floor(self) -> None:
        """每天配额不低于 30 分钟（实测单日太短不被记为学过）"""
        plan = plan_today(
            remaining_seconds=5 * 3600,
            today=date(2026, 11, 13),
            first_day=TODAY,
            end_day=END,
            studied_today=0,
            daily_minutes=10,
        )
        assert plan.daily_seconds == MIN_DAILY_MINUTES * 60
        assert plan.budget_seconds == MIN_DAILY_MINUTES * 60

    def test_nothing_remaining(self) -> None:
        plan = plan_today(remaining_seconds=0, today=TODAY, first_day=TODAY, end_day=END, studied_today=0)
        assert plan.budget_seconds == 0

    def test_no_end_date_still_plans(self) -> None:
        plan = plan_today(
            remaining_seconds=5 * 3600, today=date(2026, 11, 13), first_day=TODAY, end_day=None, studied_today=0
        )
        assert plan.budget_seconds == 40 * 60

    def test_unknown_duration_is_not_treated_as_finished(self) -> None:
        """图谱课时长未查出时，剩余 0 不能当成已经学完"""
        plan = plan_today(
            remaining_seconds=0,
            today=TODAY,
            first_day=TODAY,
            end_day=END,
            studied_today=0,
            progress_unknown=True,
        )
        assert plan.budget_seconds == 40 * 60
        assert plan.duration_unknown
        assert "今天先学 40 分钟" in plan.describe()

    def test_unknown_duration_respects_studied_today(self) -> None:
        plan = plan_today(
            remaining_seconds=0,
            today=TODAY,
            first_day=TODAY,
            end_day=END,
            studied_today=40 * 60,
            progress_unknown=True,
        )
        assert plan.budget_seconds == 0


class TestStudyLedger:
    def test_first_day_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "plan.json"
        assert StudyLedger(path).first_day("c1", TODAY) == TODAY
        # 第二天重新打开：首日不变
        assert StudyLedger(path).first_day("c1", date(2026, 11, 13)) == TODAY

    def test_add_accumulates_per_day(self, tmp_path: Path) -> None:
        path = tmp_path / "plan.json"
        StudyLedger(path).add("c1", TODAY, 600)
        StudyLedger(path).add("c1", TODAY, 300)
        ledger = StudyLedger(path)
        assert ledger.studied("c1", TODAY) == 900
        assert ledger.studied("c1", date(2026, 11, 13)) == 0
        assert ledger.studied("c2", TODAY) == 0

    def test_corrupt_file_starts_fresh(self, tmp_path: Path) -> None:
        path = tmp_path / "plan.json"
        path.write_text("not json", encoding="utf-8")
        assert StudyLedger(path).studied("c1", TODAY) == 0


@pytest.mark.parametrize(("ms", "expected"), [(None, None), (0, None)])
def test_end_date_from_ms_empty(ms: int | None, expected: date | None) -> None:
    assert end_date_from_ms(ms) == expected

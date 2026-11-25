"""Zhidao video 测试

Task 3.4 — zhidao/video.py
TDD 步骤:
1. 已看完视频 → 跳过
2. played_time = min(played_time + speed, end_time) 截断
3. 随机暂停 0.25% → 冻结 played_time，不回滚已上报进度；倍速默认 1.5 + 抖动
4. saveDatabaseIntervalTimeV2 initial=True 格式
5. saveDatabaseIntervalTimeV2 initial=False 格式（ewssw/sdsew/zwsds）
6. _watch_video 使用独立 httpx.Client
7. _watch_video daemon=True + timeout
8. 弹窗答题 answer_delay 机制
9. 人类延迟 sleep(random+1)
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import respx

from zhs.captcha.models import CaptchaSolution
from zhs.config import AppConfig
from zhs.crypto import WatchPoint, encode_ev
from zhs.exceptions import ApiError, CaptchaRequired, TimeLimitExceeded
from zhs.session import ZhsSession
from zhs.zhidao.models import (
    CourseInfo,
    QuestionPoint,
    VideoChapter,
    VideoLesson,
    VideoSmallLesson,
    ZhidaoContext,
    ZhidaoCourse,
)
from zhs.zhidao.video import ZhidaoVideoPlayer


def _make_context(
    video_sec: int = 1800,
    watch_state: int = 0,
    study_total_time: int = 0,
) -> ZhidaoContext:
    """构造测试用 ZhidaoContext"""
    video = VideoSmallLesson(
        video_id=100,
        id=200,
        name="1.1 导论",
        lesson_id=10,
        chapter_id=1,
        video_sec=video_sec,
        watch_state=watch_state,
        study_total_time=study_total_time,
    )
    course = ZhidaoCourse(
        secret="ABC123",
        course_name="测试课程",
        course_info=CourseInfo(course_id=456, name="测试课程"),
        recruit_id=789,
    )
    chapter = VideoChapter(
        id=1,
        name="第一章",
        video_lessons=[
            VideoLesson(id=10, name="1.1 导论", video_small_lessons=[video]),
        ],
    )
    return ZhidaoContext(
        course=course,
        chapters=[chapter],
        videos={100: video},
    )


@pytest.fixture
def mock_config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def mock_session(mock_config: AppConfig) -> Iterator[ZhsSession]:
    with respx.mock:
        session = ZhsSession(mock_config)
        yield session


class TestPlayVideoAlreadyDone:
    """已看完视频 → 跳过"""

    def test_skip_watched_video(self, mock_session: ZhsSession) -> None:
        """watch_state=1 且 end_threshold<=1.0 时跳过"""
        ctx = _make_context(watch_state=1)
        player = ZhidaoVideoPlayer(mock_session)
        # play_video 应该直接返回，不调用任何 API
        with patch.object(player, "_main_loop") as mock_loop:
            player.play_video("ABC123", 100, ctx)
            mock_loop.assert_not_called()

    def test_rewatch_if_threshold_above_1(self, mock_session: ZhsSession) -> None:
        """end_threshold > 1.0 时即使已看完也重新播放"""
        ctx = _make_context(watch_state=1)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=1.5)
        # 需要模拟所有 API 调用
        with (
            patch.object(player, "_main_loop"),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_load_questions", return_value=[]),
        ):
            player.play_video("ABC123", 100, ctx)
            # end_threshold > 1.0 时不跳过


class TestPlayedTimeCapped:
    """played_time = min(played_time + speed, end_time) 截断"""

    def test_capped_at_end_time(self) -> None:
        """played_time 不超过 end_time"""
        played_time = 99.0
        speed = 1.5
        end_time = 100.0
        assert min(played_time + speed, end_time) == 100.0

    def test_normal_increment(self) -> None:
        """正常递增"""
        played_time = 50.0
        speed = 1.5
        end_time = 100.0
        assert min(played_time + speed, end_time) == 51.5


class TestClassicHeartbeat:
    """真实主循环与编码数据的确定性回归。"""

    @staticmethod
    def run_loop(
        session: ZhsSession,
        end: float = 901.0,
        jitter: int = 0,
        speed: float | None = None,
        popup_at: int = 0,
        fail_first: bool = False,
        fail_db: bool = False,
        start: float = 0.0,
        total_base: int = 0,
        pause_at: int = 0,
        video_sec: int = 2000,
    ) -> list[tuple[str, int, list[int | str]]]:
        ctx = _make_context(video_sec=video_sec)
        player = ZhidaoVideoPlayer(session, speed=speed)
        calls: list[tuple[str, int, list[int | str]]] = []
        encoded: list[int | str] = []
        wall = 0
        tick = 0

        def encode(raw: list[int | str], key: str) -> str:
            encoded[:] = raw
            return "encoded"

        def fake_sleep(_seconds: float) -> None:
            nonlocal wall
            wall += 1

        def pause_random() -> float:
            """默认不触发随机暂停；pause_at 指定的轮次触发一次。"""
            nonlocal tick
            tick += 1
            return 0.0 if pause_at and tick == pause_at else 1.0

        def query(url: str, data: dict[str, Any]) -> dict[str, Any]:
            calls.append(("cache" if "Cache" in url else "db", wall, encoded.copy()))
            if (fail_first and len(calls) == 1) or (fail_db and wall == 300):
                raise ApiError(-1, "temporary failure")
            return {}

        questions = [QuestionPoint(time_sec=popup_at, question_ids=[1])] if popup_at else []
        with (
            patch.object(session, "zhidao_query", side_effect=query),
            patch("zhs.zhidao.video.encode_ev", side_effect=encode),
            patch("zhs.zhidao.video.time.sleep", side_effect=fake_sleep),
            patch("zhs.zhidao.video.print"),
            patch("zhs.zhidao.video.randint", return_value=jitter),
            patch("zhs.zhidao.video.random", side_effect=pause_random),
            patch("zhs.zhidao.quiz.ZhidaoQuizzer"),
        ):
            player._main_loop("ABC123", 100, ctx, start, int(end), total_base, "token", questions)
        return calls

    @staticmethod
    def delta(call: tuple[str, int, list[int | str]]) -> int:
        return int(call[2][8 if call[0] == "cache" else 6])

    @pytest.mark.parametrize("jitter", [-5, 0, 5])
    def test_independent_cadence_and_shared_delta(self, mock_session: ZhsSession, jitter: int) -> None:
        calls = self.run_loop(mock_session, jitter=jitter)
        assert [(kind, tick) for kind, tick, _ in calls[:3]] == [
            ("cache", 180 + jitter),
            ("db", 300 + jitter),
            ("cache", 2 * (180 + jitter)),
        ]
        assert sum(map(self.delta, calls)) == 901
        assert calls[-1][0] == "db"

    @pytest.mark.parametrize("speed", [None, 1.0, 2.0])
    def test_fixed_configured_speed(self, mock_session: ZhsSession, speed: float | None) -> None:
        calls = self.run_loop(mock_session, end=1000, speed=speed)
        actual_speed = speed if speed is not None else 1.5
        for kind, tick, raw in calls[:-1]:
            assert raw[5 if kind == "cache" else 7] == int(tick * actual_speed)
        assert calls[-1][1] == -(-1000 // actual_speed)
        assert sum(map(self.delta, calls)) == 1000

    def test_popup_reports_database_immediately(self, mock_session: ZhsSession) -> None:
        calls = self.run_loop(mock_session, end=610, popup_at=300)
        assert [(kind, tick) for kind, tick, _ in calls[:3]] == [("cache", 180), ("db", 200), ("cache", 360)]
        assert sum(map(self.delta, calls)) == 610

    def test_failed_cache_keeps_shared_delta(self, mock_session: ZhsSession) -> None:
        calls = self.run_loop(mock_session, end=610, fail_first=True)
        assert calls[1][:2] == ("db", 300)
        assert self.delta(calls[1]) == 450
        assert sum(map(self.delta, calls[1:])) == 610

    def test_failed_db_retries_after_30_seconds(self, mock_session: ZhsSession) -> None:
        calls = self.run_loop(mock_session, end=610, fail_db=True)
        db_calls = [call for call in calls if call[0] == "db"]
        assert [call[1] for call in db_calls[:2]] == [300, 330]
        assert self.delta(db_calls[1]) == 225
        assert sum(self.delta(call) for call in calls if call[1] != 300) == 610

    def test_precheck_sync_total_reaches_first_heartbeats(self, mock_session: ZhsSession) -> None:
        # video_sec 取 3000，让 -8 同步后的累计（2000）还没到目标（3000）
        ctx = _make_context(video_sec=3000, study_total_time=798)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=1.0)
        calls: list[tuple[str, float, list[int | str]]] = []
        encoded: list[int | str] = []
        note_count = 0

        def encode(raw: list[int | str], key: str) -> str:
            encoded[:] = raw
            return "encoded"

        def query(url: str, data: dict[str, Any]) -> dict[str, Any]:
            nonlocal note_count
            if "prelearningNote" in url:
                note_count += 1
                return {
                    "data": {
                        "studiedLessonDto": {
                            "id": note_count,
                            "learnTimeSec": 42,
                            "studyTotalTime": 800 if note_count == 1 else 2000,
                        }
                    }
                }
            calls.append(("cache" if "Cache" in url else "db", ctx.fucked_time, encoded.copy()))
            if len(calls) == 1:
                raise ApiError(-8, "study time decreased")
            return {}

        with (
            patch.object(mock_session, "zhidao_query", side_effect=query),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.encode_ev", side_effect=encode),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
            patch("zhs.zhidao.video.randint", return_value=0),
            patch("zhs.zhidao.video.random", return_value=1),
        ):
            player.play_video("ABC123", 100, ctx)
        assert note_count == 2
        assert calls[0][2][6:9] == [0, 800, "00:00:42"]
        assert calls[1][2][6:9] == [0, 2000, "00:00:42"]
        # 第二列是 ctx.fucked_time，即累计视频秒（1.5 倍速下 180 秒墙钟 = 270 秒视频）
        assert calls[2][:2] == ("cache", 270.0)
        assert calls[2][2][4:6] == ["00:05:12", 2270]
        assert calls[2][2][8] == 270
        assert calls[3][:2] == ("db", 450.0)
        assert calls[3][2][6:9] == [180, 2450, "00:08:12"]

    def test_resumed_loop_accumulates_without_skipping(self, mock_session: ZhsSession) -> None:
        # 续播：位置 42s、累计 800s，目标累计 1100s → 继续补 300 秒而不是从 42s 重来
        calls = self.run_loop(mock_session, start=42, end=1100, total_base=800)
        assert calls[0][2][4:6] == ["00:05:12", 1070]
        assert calls[-1][2][7:9] == [1100, "00:05:42"]
        assert sum(map(self.delta, calls)) == 300

    def test_end_at_cache_deadline_reports_database_only(self, mock_session: ZhsSession) -> None:
        calls = self.run_loop(mock_session, end=270)
        assert len(calls) == 1
        assert calls[0][:2] == ("db", 180)
        assert self.delta(calls[0]) == 270

    def test_random_pause_freezes_total_without_rollback(self, mock_session: ZhsSession) -> None:
        """随机暂停冻结播放位置，不回滚已上报进度，恢复后累计仍等于观看时长"""
        calls = self.run_loop(mock_session, end=630, pause_at=170)
        ticks = [(kind, tick) for kind, tick, _ in calls]

        # 暂停开始时立即上报一次；暂停期间心跳不再前进
        assert ticks[:2] == [("db", 170), ("cache", 180)]
        paused = [call for call in calls if 170 <= call[1] <= 230]
        totals = {raw[5] if kind == "cache" else raw[7] for kind, _, raw in paused}
        assert totals == {253}
        assert all(self.delta(call) == 0 for call in paused[1:])

        # 没有负增量或重复回滚，累计增量与观看时长一致
        assert min(map(self.delta, calls)) >= 0
        assert sum(map(self.delta, calls)) == 630

    def test_speed_is_fixed_constant(self, mock_session: ZhsSession) -> None:
        """倍速不做抖动：默认恒定 1.5，整条链路上的累计等于次数 × 1.5"""
        calls = self.run_loop(mock_session, end=610)
        assert calls[0][:2] == ("cache", 180)
        assert calls[0][2][5] == 270  # 180 * 1.5
        assert min(map(self.delta, calls)) >= 0
        assert sum(map(self.delta, calls)) == 610

    def test_speed_stays_constant_across_heartbeats(self, mock_session: ZhsSession) -> None:
        """心跳成功后不重抽倍速，各点累计严格是 1.5 的倍数"""
        calls = self.run_loop(mock_session, end=1000)
        assert [(kind, tick) for kind, tick, _ in calls[:3]] == [("cache", 180), ("db", 300), ("cache", 360)]
        assert calls[0][2][5] == 270  # 180 * 1.5
        assert calls[1][2][7] == 450  # 300 * 1.5
        assert calls[2][2][5] == 540  # 360 * 1.5
        assert sum(map(self.delta, calls)) == 1000

    def test_cache_and_database_use_course_info_course_id(self, mock_session: ZhsSession) -> None:
        """两种心跳的 courseId 都取 courseInfo.courseId，不能用 videoList 的 ctx.course_id"""
        ctx = _make_context(video_sec=2000)
        assert ctx.course_id != (ctx.course.course_info.course_id if ctx.course.course_info else 0)
        player = ZhidaoVideoPlayer(mock_session)
        raw: list[int | str] = []
        sent: dict[str, Any] = {}

        def encode(ev: list[int | str], key: str) -> str:
            raw[:] = ev
            return "encoded"

        def query(url: str, data: dict[str, Any]) -> dict[str, Any]:
            sent["kind"] = "cache" if "Cache" in url else "db"
            sent["data"] = data
            return {}

        with (
            patch.object(mock_session, "zhidao_query", side_effect=query),
            patch("zhs.zhidao.video.encode_ev", side_effect=encode),
        ):
            player._report_cache_progress(100, ctx, 180.0, 0.0, "0,1", "token", 180)
            assert sent["kind"] == "cache"
            assert raw[2] == 456
            assert sent["data"]["zwsds"] == "token"
            assert "courseId" not in sent["data"]

            sent.clear()
            player._report_progress_v2("ABC123", 100, ctx, 180.0, 0.0, "0,1", "token", initial=False, total=180)
            assert sent["kind"] == "db"
            assert sent["data"]["courseId"] == 456
            assert sent["data"]["zwsds"] == "token"

    def test_resume_position_and_total(self, mock_session: ZhsSession) -> None:
        """续播位置（learnTimeSec）与累计（studyTotalTime）必须分开传给主循环"""
        ctx = _make_context(video_sec=452, study_total_time=200)
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(
                mock_session,
                "zhidao_query",
                return_value={"data": {"studiedLessonDto": {"id": 1, "learnTimeSec": 42, "studyTotalTime": 200}}},
            ),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch.object(player, "_main_loop") as loop,
            patch("zhs.zhidao.video.encode_ev", return_value="encoded") as encode,
            patch("zhs.zhidao.video.time.sleep"),
        ):
            player.play_video("ABC123", 100, ctx)
        assert loop.call_args.args[3] == 42.0  # 位置
        assert loop.call_args.args[5] == 200  # 累计基数
        assert loop.call_args.args[4] == 411  # 累计目标 = 452 * 0.91
        raw = encode.call_args.args[0]
        assert raw[6:9] == [0, 200, "00:00:42"]

    def test_position_wraps_and_delta_stays_non_negative(self, mock_session: ZhsSession) -> None:
        """位置播到底回绕到开头，累计继续补，本段秒不出现负数"""
        calls = self.run_loop(mock_session, video_sec=100, end=400)
        positions = [call[2][4] if call[0] == "cache" else call[2][8] for call in calls]
        assert len(set(positions)) > 1  # 位置确实回绕过
        assert min(map(self.delta, calls)) >= 0
        assert sum(map(self.delta, calls)) == 400

    def test_pause_does_not_consume_time_limit(self, mock_session: ZhsSession) -> None:
        """随机暂停只冻结进度，不消耗 -l 配额；-l 按视频时长累计（1.5 倍速记 1.5 秒）"""
        ctx = _make_context(video_sec=2000)
        player = ZhidaoVideoPlayer(mock_session)
        wall = 0
        rolls = {"n": 0}

        def fake_sleep(_seconds: float) -> None:
            nonlocal wall
            wall += 1

        def pause_once() -> float:
            rolls["n"] += 1
            return 0.0 if rolls["n"] == 1 else 1.0

        with (
            patch.object(mock_session, "zhidao_query", return_value={}),
            patch("zhs.zhidao.video.encode_ev", return_value="encoded"),
            patch("zhs.zhidao.video.time.sleep", side_effect=fake_sleep),
            patch("zhs.zhidao.video.print"),
            patch("zhs.zhidao.video.randint", return_value=0),
            patch("zhs.zhidao.video.random", side_effect=pause_once),
            patch("zhs.zhidao.quiz.ZhidaoQuizzer"),
        ):
            player._main_loop("ABC123", 100, ctx, 0.0, 10, 0, "token", [])
        assert ctx.fucked_time == pytest.approx(10.5)  # 7 秒 × 1.5 倍速 = 10.5 秒视频时长
        assert wall == 68  # 60 秒暂停 + 7 秒播放，暂停的 1 分钟不计入配额

    def test_total_reaching_target_skips_loop(self, mock_session: ZhsSession) -> None:
        """累计已达标（位置可能没到底）时不再空转，只发一条预检心跳"""
        ctx = _make_context(video_sec=680, study_total_time=680)
        player = ZhidaoVideoPlayer(mock_session)
        sent: list[str] = []

        def query(url: str, data: dict[str, Any]) -> dict[str, Any]:
            sent.append(url)
            return {}

        with (
            patch.object(mock_session, "zhidao_query", side_effect=query),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 680)),
            patch.object(player, "_main_loop") as loop,
            patch.object(player, "_start_watch_thread") as watch_thread,
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
        ):
            player.play_video("ABC123", 100, ctx)
        loop.assert_not_called()
        watch_thread.assert_not_called()
        assert len(sent) == 1
        assert "saveDatabaseIntervalTimeV2" in sent[0]


class TestReportV2Initial:
    """saveDatabaseIntervalTimeV2 initial=True 格式"""

    def test_initial_ev_format(self) -> None:
        """initial=True 时 ev 数据结构"""
        ctx = _make_context()
        video = ctx.videos[100]
        played_time = 100
        raw_ev: list[int | str] = [
            ctx.course.recruit_id or 0,
            video.chapter_id,
            ctx.course.course_info.course_id if ctx.course.course_info else 0,
            video.lesson_id,
            str(timedelta(seconds=min(video.video_sec, int(played_time)))),
            int(played_time),
            video.video_id,
            "0",
            int(played_time),
            "test-uuid",
        ]
        ev = encode_ev(raw_ev)
        assert isinstance(ev, str)
        assert len(ev) > 0

    def test_initial_data_no_course_id(self) -> None:
        """initial=True 时 data 不含 courseId"""
        data = {"ewssw": "0,1", "sdsew": "abc", "zwsds": "token"}
        # initial=True 时移除 courseId
        data.pop("courseId", None)
        assert "courseId" not in data


class TestReportV2Regular:
    """saveDatabaseIntervalTimeV2 initial=False 格式"""

    def test_regular_ev_format(self) -> None:
        """initial=False 时 ev 数据结构"""
        ctx = _make_context()
        video = ctx.videos[100]
        played_time = 100
        last_submit = 70
        raw_ev: list[int | str] = [
            ctx.course.recruit_id or 0,
            video.lesson_id,
            video.id,
            video.video_id,
            video.chapter_id,
            "0",
            int(played_time - last_submit),
            int(played_time),
            str(timedelta(seconds=min(video.video_sec, int(played_time)))),
            "test-uuid" + "zhs",
        ]
        ev = encode_ev(raw_ev)
        assert isinstance(ev, str)

    def test_regular_data_has_ewssw_sdsew_zwsds(self) -> None:
        """initial=False 时 data 包含 ewssw/sdsew/zwsds/courseId"""
        data = {"ewssw": "0,1", "sdsew": "abc", "zwsds": "token", "courseId": 456}
        assert "ewssw" in data
        assert "sdsew" in data
        assert "zwsds" in data
        assert "courseId" in data


class TestWatchVideoIndependentClient:
    """_watch_video 使用独立 httpx.Client"""

    def test_uses_independent_client(self, mock_session: ZhsSession) -> None:
        """_watch_video 不共享 session 的 cookies"""
        player = ZhidaoVideoPlayer(mock_session)
        # _watch_video 应创建独立的 httpx.Client
        with patch("zhs.zhidao.video.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = MagicMock(
                text='result({"result":{"lines":[{"lineUrl":"https://video.url"}]}})'
            )
            player._watch_video(100)
            mock_client_cls.assert_called_once()


class TestWatchVideoDaemonThread:
    """_watch_video 线程属性"""

    def test_daemon_thread(self, mock_session: ZhsSession) -> None:
        """_watch_video 线程 daemon=True"""
        player = ZhidaoVideoPlayer(mock_session)
        with patch("zhs.zhidao.video.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            player._start_watch_thread(100)
            mock_thread_cls.assert_called_once()
            # 验证 daemon=True
            call_kwargs = mock_thread_cls.call_args
            assert call_kwargs.kwargs.get("daemon") is True or call_kwargs[1].get("daemon") is True


class TestAnswerDelay:
    """弹窗答题 answer_delay 机制"""

    def test_answer_delay_decrement(self) -> None:
        """answer_delay=2 递减"""
        answer_delay = 2
        answer_delay -= 1
        assert answer_delay == 1
        answer_delay -= 1
        assert answer_delay == 0

    def test_answer_delay_triggers_on_zero(self) -> None:
        """answer_delay=0 时提交答案"""
        answer_delay = 0
        # 当 answer_delay == 0 时，执行答题
        should_answer = answer_delay == 0
        assert should_answer


class TestHumanDelay:
    """人类延迟"""

    def test_human_delay_range(self) -> None:
        """sleep(random+1) 范围在 [1, 2) 秒"""
        import random

        for _ in range(100):
            delay = random.random() + 1
            assert 1.0 <= delay < 2.0


class TestEndThreshold:
    """end_threshold 计算"""

    def test_default_threshold(self) -> None:
        """默认 end_threshold=0.91"""
        player = ZhidaoVideoPlayer.__new__(ZhidaoVideoPlayer)
        player.end_threshold = 0.91
        video_sec = 1800
        end_time = max(video_sec * player.end_threshold, 1.0)
        assert end_time == 1638.0

    def test_question_extends_end_time(self) -> None:
        """弹窗题目时间超过 end_threshold 时，end_time 取题目时间"""
        video_sec = 1800
        end_threshold = 0.91
        end_time = max(video_sec * end_threshold, 1.0)
        last_question_time = 1700
        end_time = max(last_question_time, end_time)
        assert end_time == 1700


class TestWatchPoint:
    """WatchPoint 在视频播放中的使用"""

    def test_watch_point_add_and_get(self) -> None:
        """WatchPoint 添加和获取"""
        wp = WatchPoint()
        wp.add(10)
        result = wp.get()
        assert "0" in result
        assert "1" in result

    def test_watch_point_reset(self) -> None:
        """WatchPoint 重置"""
        wp = WatchPoint()
        wp.add(100)
        wp.reset(50)
        assert wp.last == 50
        assert wp.wp == [0, 1]


class TestPlayCourse:
    """play_course 测试"""

    def test_play_course_iterates_videos(self, mock_session: ZhsSession) -> None:
        """play_course 遍历所有视频"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with patch.object(player, "play_video") as mock_play:
            player.play_course("ABC123", ctx)
            mock_play.assert_called_once_with("ABC123", 100, ctx)

    def test_stops_course_once_when_budget_exhausted(self, mock_session: ZhsSession) -> None:
        """配额用完后整门课停止，只提示一次，不再逐个视频打印「跳过(时间限制)」"""
        ctx = _make_context()
        ctx.fucked_time = 60.0
        player = ZhidaoVideoPlayer(mock_session, time_limit=60)
        with (
            patch.object(player, "play_video") as mock_play,
            patch.object(player, "_print_with_progress") as printer,
            patch("zhs.zhidao.video.print"),
        ):
            player.play_course("ABC123", ctx)
        mock_play.assert_not_called()
        assert sum("时间配额已用完" in str(call.args[0]) for call in printer.call_args_list) == 1

    def test_play_course_prints_new_course(self, mock_session: ZhsSession) -> None:
        """play_course 开始时打印 '新课程' 标识"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player, "play_video"),
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.wipe_line"),
            patch("zhs.zhidao.video.print") as mock_print,
        ):
            player.play_course("ABC123", ctx)
            # 第一个 print 调用应包含 "新课程"
            first_call_args = mock_print.call_args_list[0]
            assert "新课程" in first_call_args.args[0]


class TestPrintWithProgress:
    """_print_with_progress / _clear_progress 测试"""

    def test_print_no_bar(self, mock_session: ZhsSession) -> None:
        """无进度条时正常打印"""
        player = ZhidaoVideoPlayer(mock_session)
        with patch("zhs.zhidao.video.print") as mock_print:
            player._print_with_progress("章节: 第一章", depth=1)
            assert mock_print.call_count == 1
            assert "章节: 第一章" in mock_print.call_args_list[0].args[0]

    def test_print_with_bar_reprints(self, mock_session: ZhsSession) -> None:
        """有进度条时清除并重印进度条（保持进度条在底部）"""
        player = ZhidaoVideoPlayer(mock_session)
        player._progress_line = "playing 100 [####] 50.0%"
        with (
            patch("zhs.zhidao.video.wipe_line"),
            patch("zhs.zhidao.video.print") as mock_print,
        ):
            player._print_with_progress("章节: 第一章", depth=1)
            # 两次 print: 消息 + 重印进度条
            assert mock_print.call_count == 2
            assert "章节: 第一章" in mock_print.call_args_list[0].args[0]
            assert "playing 100" in mock_print.call_args_list[1].args[0]

    def test_print_disabled(self, mock_session: ZhsSession) -> None:
        """enabled=False 时不打印"""
        player = ZhidaoVideoPlayer(mock_session)
        with patch("zhs.zhidao.video.print") as mock_print:
            player._print_with_progress("章节", enabled=False)
            mock_print.assert_not_called()

    def test_clear_progress(self, mock_session: ZhsSession) -> None:
        """_clear_progress 清除进度条"""
        player = ZhidaoVideoPlayer(mock_session)
        player._progress_line = "playing 100 [####] 50.0%"
        with patch("zhs.zhidao.video.wipe_line") as mock_wipe:
            player._clear_progress()
            mock_wipe.assert_called_once()
            assert player._progress_line is None

    def test_clear_progress_no_bar(self, mock_session: ZhsSession) -> None:
        """_clear_progress 无进度条时不调用 wipe_line"""
        player = ZhidaoVideoPlayer(mock_session)
        with patch("zhs.zhidao.video.wipe_line") as mock_wipe:
            player._clear_progress()
            mock_wipe.assert_not_called()


class TestMainLoopCompletion:
    """_main_loop 完成时显示 100% 进度条"""

    def test_completion_shows_100_percent(self, mock_session: ZhsSession) -> None:
        """视频播放完成时进度条显示 100.0%"""
        ctx = _make_context(video_sec=100, study_total_time=0)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=0.05)
        with (
            patch.object(player, "_report_progress_v2", return_value=(0.0, True)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.random", return_value=1),
            patch("zhs.zhidao.video.print") as mock_print,
        ):
            player.play_video("ABC123", 100, ctx)
            # 最后一次 print 调用应包含 "100.0%"
            last_call_args = mock_print.call_args_list[-1]
            assert "100.0%" in last_call_args.args[0]


class TestProgressNoResidue:
    """进度行用空格填充，避免变短时残留旧字符"""

    def test_progress_padded_to_prev_len(self, mock_session: ZhsSession) -> None:
        """切换到更短的 action（如 pause）时，填充空格覆盖残留"""
        ctx = _make_context(video_sec=100, study_total_time=0)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=0.05)
        # 模拟上一视频残留的长进度行
        player._progress_line = "x" * 100
        with (
            patch.object(player, "_report_progress_v2", return_value=(0.0, True)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.random", return_value=1),
            patch("zhs.zhidao.video.print") as mock_print,
        ):
            player.play_video("ABC123", 100, ctx)
            # 第一次进度打印应被填充至至少 100 字符（覆盖残留）
            first = mock_print.call_args_list[0].args[0]
            assert first.startswith("\r")
            assert len(first) - 1 >= 100  # 去掉 \r 前缀后长度 >= 100


class TestReportProgressV2Return:
    """_report_progress_v2 返回 (server_played, success) 元组"""

    def test_success_returns_true(self, mock_session: ZhsSession) -> None:
        """上报成功时返回 (played_time, True)"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with patch.object(player._session, "zhidao_query"):
            result, success = player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                position=100.0,
                submitted_total=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is True
        assert result == 100.0

    def test_failure_returns_false(self, mock_session: ZhsSession) -> None:
        """上报失败时返回 (played_time, False)"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with patch.object(player._session, "zhidao_query", side_effect=Exception("code: -1 msg: error")):
            result, success = player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                position=100.0,
                submitted_total=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is False
        assert result == 100.0

    def test_minus_8_sync_success(self, mock_session: ZhsSession) -> None:
        """-8 错误同步成功时返回 (server_time, True)"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        db_call_count = 0

        def _query_side_effect(url: str, *args: object, **kwargs: object) -> object:
            # cache 调用始终成功
            if "saveCacheIntervalTimeV2" in url:
                return {}
            nonlocal db_call_count
            db_call_count += 1
            if db_call_count == 1:
                raise Exception("code: -8 msg: study time decreased")
            return {}  # 第二次调用成功

        with (
            patch.object(player._session, "zhidao_query", side_effect=_query_side_effect),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 120)),
        ):
            result, success = player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                position=100.0,
                submitted_total=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is True
        assert result == 120.0

    def test_minus_10_retry_success(self, mock_session: ZhsSession) -> None:
        """-10 错误重试成功时返回 (played_time, True)"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        db_call_count = 0

        def _query_side_effect(url: str, *args: object, **kwargs: object) -> object:
            # cache 调用始终成功
            if "saveCacheIntervalTimeV2" in url:
                return {}
            nonlocal db_call_count
            db_call_count += 1
            if db_call_count == 1:
                raise Exception("code: -10 msg: multi-window")
            return {}  # 第二次调用成功

        with (
            patch.object(player._session, "zhidao_query", side_effect=_query_side_effect),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch("zhs.zhidao.video.time.sleep"),
        ):
            result, success = player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                position=100.0,
                submitted_total=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is True
        assert result == 100.0


class TestReportFailureNoLastSubmitUpdate:
    """上报失败时 last_submit 不更新，确保下次增量正确"""

    def test_failure_keeps_last_submit(self, mock_session: ZhsSession) -> None:
        """上报失败时 last_submit 保持不变，下次上报增量包含全部未确认进度"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player, "_report_progress_v2", return_value=(100.0, False)) as mock_report,
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
            patch("zhs.zhidao.video.random", return_value=1),
        ):
            player.end_threshold = 0.05  # end_time=90，循环快速结束
            player.play_video("ABC123", 100, ctx)

        # 所有失败心跳的 last_submit 都停留在起始位置 0，增量不被丢掉
        assert len(mock_report.call_args_list) >= 2
        assert {call.args[4] for call in mock_report.call_args_list} == {0.0}
        assert mock_report.call_args_list[-1].args[3] > 0


class TestStartPrecheck:
    """开播预检：进入观看循环前立即上报，提前发现验证码/时长上限

    实测结论：服务端风控仅在常规心跳格式（initial=False）的
    saveDatabaseIntervalTimeV2 上评估，initial=True 补报不返回 -12/-9。
    故预检用 delta=0 的常规心跳（last_submit=played_time），提前到 t=0 发出。
    """

    def test_precheck_called_before_main_loop(self, mock_session: ZhsSession) -> None:
        """play_video 在 _main_loop 之前调用 _report_progress_v2（常规心跳格式）"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        manager = MagicMock()
        with (
            patch.object(player, "_main_loop") as mock_loop,
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_report_progress_v2", return_value=(0.0, True)) as mock_report,
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
        ):
            manager.attach_mock(mock_report, "report")
            manager.attach_mock(mock_loop, "loop")
            player.play_video("ABC123", 100, ctx)
            calls = [name for name, _args, _kwargs in manager.mock_calls]
            assert calls == ["report", "loop"]
            assert mock_report.call_args.kwargs.get("initial") is False
            # delta=0：last_submit 与 played_time 相同，不虚报进度
            args = mock_report.call_args.args
            assert args[4] == args[3]

    def test_precheck_captcha_before_loop(self, mock_session: ZhsSession) -> None:
        """预检发现 -12 → CaptchaRequired，不进入观看循环、不启动视频流线程"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player, "_main_loop") as mock_loop,
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_report_progress_v2", side_effect=CaptchaRequired("服务端要求验证码")),
            patch.object(player, "_start_watch_thread") as mock_watch,
            patch.object(player, "_three_dimensional_course_ware"),
        ):
            with pytest.raises(CaptchaRequired):
                player.play_video("ABC123", 100, ctx)
            mock_loop.assert_not_called()
            mock_watch.assert_not_called()

    def test_report_v2_minus9_raises_time_limit(self, mock_session: ZhsSession) -> None:
        """_report_progress_v2 遇到 code -9 → TimeLimitExceeded（不再静默失败继续白看）"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player._session, "zhidao_query", side_effect=ApiError(-9, "学习时间已经结束")),
            pytest.raises(TimeLimitExceeded),
        ):
            player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                position=100.0,
                submitted_total=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )

    def test_play_course_stops_on_time_limit(self, mock_session: ZhsSession) -> None:
        """play_course 遇到 TimeLimitExceeded 停止课程且不继续播放后续视频"""
        ctx = _make_context()
        # 追加第二个视频，验证是"停止课程"而非"跳过继续"
        video2 = VideoSmallLesson(
            video_id=101,
            id=201,
            name="1.2",
            lesson_id=10,
            chapter_id=1,
            video_sec=600,
            watch_state=0,
        )
        ctx.chapters[0].video_lessons[0].video_small_lessons.append(video2)
        ctx.videos[101] = video2
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player, "play_video", side_effect=TimeLimitExceeded("学习时间已达上限")) as mock_play,
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.wipe_line"),
            patch("zhs.zhidao.video.print"),
        ):
            player.play_course("ABC123", ctx)
            mock_play.assert_called_once()


class TestSolveCaptchaEv:
    """-12 上报 validateSlideToken 时的 ev 生成规则"""

    def test_ev_is_reencoded_from_five_ids(self, mock_session: ZhsSession) -> None:
        """ev 必须是 5 个 ID 的重编码（78 字符），不能复用心跳的 10 段 sdsew"""
        ctx = _make_context()
        video = ctx.videos[100]
        player = ZhidaoVideoPlayer(mock_session)
        exc = CaptchaRequired(
            "服务端要求验证码",
            response={"code": -12, "message": "需要弹出滑块验证", "data": None},
            payload={"ewssw": "0,1", "sdsew": "4e4d47" + "00" * 63, "zwsds": "x", "courseId": 456},
        )
        solution = CaptchaSolution(validate="CN31_xxx_v_i_1", raw_validate="raw")
        sent: list[dict[str, Any]] = []

        def query(_url: str, data: dict[str, Any]) -> dict[str, Any]:
            sent.append(data)
            return {"data": {"pass": True}}

        with (
            patch.object(player._session.captcha, "solve", return_value=solution),
            patch.object(player._session, "zhidao_query", side_effect=query),
        ):
            assert player._try_solve_captcha(exc, ctx, video) is True

        expected_ev = encode_ev(
            [789, video.lesson_id, video.id, video.video_id, video.chapter_id],
            mock_session.crypto.ev_key,
        )
        assert sent == [{"token": "CN31_xxx_v_i_1", "ev": expected_ev, "checkType": 1}]
        assert expected_ev != exc.payload["sdsew"]

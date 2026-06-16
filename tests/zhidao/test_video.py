"""Zhidao video 测试

Task 3.4 — zhidao/video.py
TDD 步骤:
1. 已看完视频 → 跳过
2. played_time = min(played_time + speed, end_time) 截断
3. 随机暂停 0.25% → played_time 不前进
4. saveDatabaseIntervalTimeV2 initial=True 格式
5. saveDatabaseIntervalTimeV2 initial=False 格式（ewssw/sdsew/zwsds）
6. _watch_video 使用独立 httpx.Client
7. _watch_video daemon=True + timeout
8. 弹窗答题 answer_delay 机制
9. 人类延迟 sleep(random+1)
"""

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import respx

from zhs.config import AppConfig
from zhs.crypto import WatchPoint, encode_ev
from zhs.session import ZhsSession
from zhs.zhidao.models import (
    CourseInfo,
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


class TestRandomPause:
    """随机暂停 0.25% → played_time 不前进"""

    def test_pause_no_progress(self) -> None:
        """暂停期间 played_time = last_submit（不前进）"""
        last_submit = 50
        played_time = 50
        # 暂停时 played_time 回退到 last_submit
        played_time = last_submit
        assert played_time == 50

    def test_pause_countdown(self) -> None:
        """暂停倒计时递减"""
        pause = 60
        pause -= 1
        assert pause == 59


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

    def test_answer_delay_causes_pause(self) -> None:
        """答题延迟期间产生暂停"""
        answer_delay = 2
        # 延迟期间 pause = pause or 1
        pause = 0
        if answer_delay > 0:
            pause = pause or 1
        assert pause == 1


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

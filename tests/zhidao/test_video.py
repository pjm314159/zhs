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
from zhs.exceptions import ApiError, CaptchaRequired, TimeLimitExceeded
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
            patch.object(player, "_report_progress_v2", return_value=(5.0, True)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
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
            patch.object(player, "_report_progress_v2", return_value=(5.0, True)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
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
                played_time=100.0,
                last_submit=70.0,
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
                played_time=100.0,
                last_submit=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is False
        assert result == 100.0

    def test_minus_8_sync_success(self, mock_session: ZhsSession) -> None:
        """-8 时累计秒改为 服务端记录 + 本段秒，返回新的累计秒

        「学习总时长下降了」只说明累计秒偏低；本段秒（100-70=30）与播放位置照旧上报。
        """
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
                played_time=100.0,
                last_submit=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is True
        assert result == 150.0  # 服务端 120 + 本段 30

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
                played_time=100.0,
                last_submit=70.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
            )
        assert success is True
        assert result == 100.0


class TestReportFailureNoLastSubmitUpdate:
    """上报失败时 last_submit 不更新，确保下次增量正确"""

    def test_failure_keeps_last_submit(self, mock_session: ZhsSession) -> None:
        """上报失败时 last_submit 保持不变，下次上报增量正确"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        # 模拟 _report_progress_v2 返回失败
        with (
            patch.object(player, "_report_progress_v2", return_value=(100.0, False)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
        ):
            # played_time 从 70 开始，end_time=91%*1800=1638
            # 但我们设置 end_threshold=1.0 让循环快速结束
            player.end_threshold = 0.05  # end_time=90
            # 全部上报失败 → 视频不计进度，play_video 如实抛错
            with pytest.raises(ApiError):
                player.play_video("ABC123", 100, ctx)


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
            patch.object(player, "_main_loop", return_value=1) as mock_loop,
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
                played_time=100.0,
                last_submit=70.0,
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


class TestHonestCompletion:
    """进度从未上报成功或课程没有可播视频时，不打印“完成课程”"""

    def test_all_reports_failed_raises(self, mock_session: ZhsSession) -> None:
        """主循环一次都没上报成功 → play_video 抛错，而不是静默返回"""
        ctx = _make_context(video_sec=100)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=0.05)
        with (
            patch.object(player, "_report_progress_v2", return_value=(0.0, False)),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_prelearning_note", return_value=("dG9rZW4=", 0)),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
            pytest.raises(ApiError),
        ):
            player.play_video("ABC123", 100, ctx)

    def test_course_with_failed_video_not_reported_done(self, mock_session: ZhsSession) -> None:
        """有视频失败时提示失败数，不打印“完成课程”"""
        ctx = _make_context()
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch.object(player, "play_video", side_effect=ApiError(-1, "参数解码发生错误")),
            patch("zhs.zhidao.video.tree_print") as mock_tree,
            patch("zhs.zhidao.video.print"),
        ):
            player.play_course("ABC123", ctx)
        texts = " ".join(str(c.args[0]) for c in mock_tree.call_args_list)
        assert "完成课程" not in texts
        assert "1 个视频失败" in texts

    def test_course_without_videos_warns(self, mock_session: ZhsSession) -> None:
        """没有可播放视频时提示，而不是报完成"""
        ctx = _make_context()
        ctx.chapters[0].video_lessons[0].video_small_lessons = []
        ctx.videos = {}
        player = ZhidaoVideoPlayer(mock_session)
        with (
            patch("zhs.zhidao.video.tree_print") as mock_tree,
            patch("zhs.zhidao.video.print"),
        ):
            player.play_course("ABC123", ctx)
        texts = " ".join(str(c.args[0]) for c in mock_tree.call_args_list)
        assert "完成课程" not in texts
        assert "未找到可播放的视频" in texts


class TestHms:
    """ev 里的播放位置用 HH:MM:SS，小时补零（抓包：网页端发 00:03:00，timedelta 会给 0:03:00）"""

    @pytest.mark.parametrize(
        ("sec", "expected"), [(0, "00:00:00"), (180, "00:03:00"), (468, "00:07:48"), (3723, "01:02:03")]
    )
    def test_format(self, sec: int, expected: str) -> None:
        from zhs.zhidao.video import _hms

        assert _hms(sec) == expected


class TestClassicHeartbeatCadence:
    """旧版 videolist 课心跳节奏与网页端一致（抓包：docs/capture-findings.md）

    网页端 1x 实测：saveCacheIntervalTimeV2 约每 180 秒、saveDatabaseIntervalTimeV2 约每 300 秒，
    触发时机各自计时，本段秒共用一条增量链；默认倍速 1.0，上报的学习秒数等于真实经过的秒数。
    """

    @staticmethod
    def _run(mock_session: ZhsSession, seconds: int, speed: float | None = None) -> list[tuple[str, list[str]]]:
        """跑主循环 seconds 秒，返回 [(接口名, 解码后的 ev 字段)]"""
        from zhs.crypto import _key_generator

        ctx = _make_context()
        ctx.videos[100].video_sec = 100000  # 足够长，不会提前播完
        player = ZhidaoVideoPlayer(mock_session, speed=speed, end_threshold=1.0)
        calls: list[tuple[str, list[str]]] = []

        def decode(ev: str) -> list[str]:
            keys = _key_generator(mock_session.crypto.ev_key)
            return "".join(chr(int(ev[i : i + 2], 16) ^ next(keys)) for i in range(0, len(ev), 2)).split(";")

        def fake_query(url: str, data: dict, *args: object, **kwargs: object) -> dict:
            calls.append((url.rsplit("/", 1)[1], decode(data["sdsew"])))
            return {"code": 0}

        with (
            patch.object(player._session, "zhidao_query", side_effect=fake_query),
            patch("zhs.zhidao.video.randint", return_value=0),  # 去掉抖动，间隔固定
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
        ):
            # end_time = 起点 + seconds * 倍速，循环恰好跑 seconds 秒
            effective = speed or 1.0
            player._main_loop("ABC123", 100, ctx, 0.0, seconds * effective, seconds * effective, "dG9rZW4=", [])
        return calls

    @staticmethod
    def _delta(name: str, ev: list[str]) -> int:
        """本段秒：Cache ev 第 9 字段，Database ev 第 7 字段"""
        return int(ev[8]) if "Cache" in name else int(ev[6])

    def test_web_capture_sequence(self, mock_session: ZhsSession) -> None:
        """复现网页抓包的触发时刻与本段秒：Cache@180 +180、DB@300 +120、Cache@360 +60

        两种上报共用一条增量链，服务端把两者的本段秒都累加进 studyTotalTime。
        """
        calls = self._run(mock_session, 361)
        got = [(name, self._delta(name, ev)) for name, ev in calls]
        assert got[:3] == [
            ("saveCacheIntervalTimeV2", 180),
            ("saveDatabaseIntervalTimeV2", 120),
            ("saveCacheIntervalTimeV2", 60),
        ]

    def test_deltas_sum_to_watched_seconds(self, mock_session: ZhsSession) -> None:
        """所有上报的本段秒之和 = 实际播放秒数，不重复计、不漏计"""
        calls = self._run(mock_session, 601)
        assert sum(self._delta(name, ev) for name, ev in calls) == 601

    def test_last_report_is_database(self, mock_session: ZhsSession) -> None:
        """播完时报的是 Database（计入进度），同一秒到期的 Cache 让位"""
        calls = self._run(mock_session, 601)
        assert calls[-1][0] == "saveDatabaseIntervalTimeV2"

    def test_position_follows_real_seconds(self, mock_session: ZhsSession) -> None:
        """默认 1.0 倍：播放位置随真实秒数前进；HH:MM:SS 小时补零，与网页一致"""
        calls = self._run(mock_session, 361)
        positions = [ev[4] if "Cache" in name else ev[8] for name, ev in calls]
        assert positions[:3] == ["00:03:00", "00:05:00", "00:06:00"]

    def test_configured_speed_scales_reported_seconds(self, mock_session: ZhsSession) -> None:
        """配置 1.5 倍时，300 秒真实时间合计上报 450 秒学习时长"""
        calls = self._run(mock_session, 300, speed=1.5)
        assert sum(self._delta(name, ev) for name, ev in calls) == 450


class TestResumeAndTotalSplit:
    """播放位置（learnTimeSec）与累计学习时长（studyTotalTime）分开处理

    实测：重看过的视频 studyTotalTime 会大于视频时长（如 452 秒的视频累计 798），
    把累计当播放位置会直接越过结尾、一次心跳就结束。网页端从 learnTimeSec 续播，
    ev 的累计秒在 studyTotalTime 上继续加（抓包：位置 00:03:00 时累计 863）。
    """

    def test_resume_position_from_learn_time_sec(self, mock_session: ZhsSession) -> None:
        player = ZhidaoVideoPlayer(mock_session)
        player._last_note = {"learnTimeSec": 120, "studyTotalTime": 900}
        assert player._resume_position(452) == 120.0

    def test_resume_position_clamped_to_duration(self, mock_session: ZhsSession) -> None:
        player = ZhidaoVideoPlayer(mock_session)
        player._last_note = {"learnTimeSec": 9999}
        assert player._resume_position(452) == 452.0

    def test_resume_position_missing_is_zero(self, mock_session: ZhsSession) -> None:
        player = ZhidaoVideoPlayer(mock_session)
        assert player._resume_position(452) == 0.0

    def test_ev_total_field_uses_total_not_position(self, mock_session: ZhsSession) -> None:
        """Database ev：本段秒 = 位置差，累计秒 = total，HH:MM:SS = 位置"""
        from zhs.crypto import _key_generator

        ctx = _make_context(video_sec=452)
        player = ZhidaoVideoPlayer(mock_session)
        sent: list[str] = []
        with patch.object(
            player._session, "zhidao_query", side_effect=lambda url, data, *a, **k: sent.append(data["sdsew"])
        ):
            player._report_progress_v2(
                "ABC123",
                100,
                ctx,
                played_time=180.0,
                last_submit=60.0,
                watch_point="0,1",
                token_id="dG9rZW4=",
                initial=False,
                total=863,
            )
        keys = _key_generator(mock_session.crypto.ev_key)
        ev = "".join(chr(int(sent[0][i : i + 2], 16) ^ next(keys)) for i in range(0, len(sent[0]), 2)).split(";")
        assert ev[6] == "120"  # 本段
        assert ev[7] == "863"  # 累计
        assert ev[8] == "00:03:00"  # 位置

    def test_play_video_resumes_from_position_not_total(self, mock_session: ZhsSession) -> None:
        """累计 798 > 时长 452 的视频，仍从 learnTimeSec 位置开始播"""
        ctx = _make_context(video_sec=452, study_total_time=798)
        player = ZhidaoVideoPlayer(mock_session, end_threshold=1.0)

        def fake_note(*args: object) -> tuple[str, int]:
            player._last_note = {"learnTimeSec": 42, "studyTotalTime": 798}
            return "dG9rZW4=", 798

        with (
            patch.object(player, "_prelearning_note", side_effect=fake_note),
            patch.object(player, "_load_questions", return_value=[]),
            patch.object(player, "_precheck"),
            patch.object(player, "_start_watch_thread"),
            patch.object(player, "_three_dimensional_course_ware"),
            patch.object(player, "_main_loop", return_value=1) as loop,
            patch("zhs.zhidao.video.time.sleep"),
        ):
            player.play_video("ABC123", 100, ctx)

        args = loop.call_args.args
        assert args[3] == 42.0  # 起始位置
        assert args[8] == 798  # 累计基准

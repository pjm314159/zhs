"""polymas 视频播放器测试

随机函数/sleep 全部 patch，保证确定性与速度。
report 报文字段按 probe step_report（PR #168），F9 未实测。
"""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zhs.config import PolymasConfig
from zhs.exceptions import ApiError, TimeLimitExceeded
from zhs.polymas.models import PolymasCourse, PolymasVideoNode
from zhs.polymas.video import PolymasVideoPlayer


def _course() -> PolymasCourse:
    return PolymasCourse.model_validate(
        {
            "courseId": "3001",
            "courseName": "智慧课",
            "courseType": "hikeAiCourse",
            "terms": [20271],
            "classId": "203843",
        }
    )


def _video(
    resource_id: str = "r1",
    title: str = "视频1",
    duration: float = 10.0,
) -> PolymasVideoNode:
    return PolymasVideoNode(resource_id=resource_id, title=title, chapter="第一章", duration=duration)


def _detail_body(
    duration: float = 10.0,
    end_watch: float = 0,
    finished: bool = False,
    percentage: float = 0.0,
) -> dict[str, Any]:
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "duration": duration,
            "endWatchTime": end_watch,
            "isFinished": finished,
            "completePercentage": percentage,
        },
    }


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.urls.polymas_api = "https://cloudapi.polymas.com"
    return session


@pytest.fixture
def mock_mgr() -> MagicMock:
    mgr = MagicMock()
    mgr.library_folder_id.return_value = "lib1"
    return mgr


def _player(session: MagicMock, **kwargs: Any) -> PolymasVideoPlayer:
    return PolymasVideoPlayer(session, PolymasConfig(), **kwargs)


class TestPlayVideo:
    @patch("zhs.polymas.video.time.sleep")
    @patch("zhs.polymas.video.random", return_value=1)
    @patch("zhs.polymas.video.uniform", return_value=0)
    @patch("zhs.polymas.video.randint", return_value=30)
    def test_reports_progress_to_end(
        self,
        _randint: MagicMock,
        _uniform: MagicMock,
        _random: MagicMock,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """未完成视频播放到阈值：最后上报区间 [0, int(duration*threshold)]"""
        mock_session.polymas_query.return_value = _detail_body(duration=10.0)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        calls = mock_session.polymas_query.call_args_list
        assert len(calls) == 2  # 1 detail + 1 report
        assert "resource/detail" in calls[0].args[0]
        assert "record/report" in calls[1].args[0]
        body = calls[1].args[1]
        assert body["startWatchTime"] == 0
        assert body["endWatchTime"] == int(10.0 * 0.91)
        assert body["studyTotalTime"] == body["endWatchTime"] - body["startWatchTime"]

    @patch("zhs.polymas.video.time.sleep")
    @patch("zhs.polymas.video.random", return_value=1)
    @patch("zhs.polymas.video.uniform", return_value=0)
    @patch("zhs.polymas.video.randint", return_value=30)
    def test_report_body_shape(
        self,
        _randint: MagicMock,
        _uniform: MagicMock,
        _random: MagicMock,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """report body 携带 courseId/resourceId/term(int)/clientType/日期串"""
        mock_session.polymas_query.return_value = _detail_body(duration=10.0)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        body = mock_session.polymas_query.call_args_list[1].args[1]
        assert body["courseId"] == "3001"
        assert body["resourceId"] == "r1"
        assert body["term"] == 20271
        assert body["clientType"] == "Windows"
        # startDate/endDate 可按 %Y-%m-%d %H:%M:%S 解析
        datetime.strptime(body["startDate"], "%Y-%m-%d %H:%M:%S")
        datetime.strptime(body["endDate"], "%Y-%m-%d %H:%M:%S")

    @patch("zhs.polymas.video.time.sleep")
    @patch("zhs.polymas.video.random", return_value=1)
    @patch("zhs.polymas.video.uniform", return_value=0)
    @patch("zhs.polymas.video.randint", return_value=30)
    def test_resumes_from_server_time(
        self,
        _randint: MagicMock,
        _uniform: MagicMock,
        _random: MagicMock,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """服务端已有进度（endWatchTime=5）→ 从 5 续播，上报区间从 5 起"""
        mock_session.polymas_query.return_value = _detail_body(duration=10.0, end_watch=5)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        body = mock_session.polymas_query.call_args_list[1].args[1]
        assert body["startWatchTime"] == 5
        assert body["endWatchTime"] == int(10.0 * 0.91)

    @patch("zhs.polymas.video.time.sleep")
    def test_skips_finished(
        self,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """isFinished=True → 只查详情，不上报"""
        mock_session.polymas_query.return_value = _detail_body(finished=True)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        assert mock_session.polymas_query.call_count == 1

    @patch("zhs.polymas.video.time.sleep")
    def test_skips_by_percentage(
        self,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """completePercentage 达阈值 → 跳过（0-100 语义，TODO: F10 校正）"""
        mock_session.polymas_query.return_value = _detail_body(percentage=95.0)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        assert mock_session.polymas_query.call_count == 1

    @patch("zhs.polymas.video.time.sleep")
    @patch("zhs.polymas.video.random", return_value=1)
    @patch("zhs.polymas.video.uniform", return_value=0)
    @patch("zhs.polymas.video.randint", return_value=30)
    def test_report_failure_does_not_crash(
        self,
        _randint: MagicMock,
        _uniform: MagicMock,
        _random: MagicMock,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """上报失败只记日志，不中断播放"""
        mock_session.polymas_query.side_effect = [_detail_body(duration=10.0), ApiError(code=500, message="x")]
        _player(mock_session).play_video(_course(), _video(), mock_mgr)  # 不抛异常

    @patch("zhs.polymas.video.time.sleep")
    @patch("zhs.polymas.video.random", return_value=1)
    @patch("zhs.polymas.video.uniform", return_value=0)
    @patch("zhs.polymas.video.randint", return_value=30)
    def test_time_limit_raises(
        self,
        _randint: MagicMock,
        _uniform: MagicMock,
        _random: MagicMock,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """累计观看时间达 time_limit → TimeLimitExceeded"""
        mock_session.polymas_query.return_value = _detail_body(duration=10000.0)
        with pytest.raises(TimeLimitExceeded):
            _player(mock_session, time_limit=5).play_video(_course(), _video(), mock_mgr)

    @patch("zhs.polymas.video.time.sleep")
    def test_detail_request_body(
        self,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """resource/detail POST body 携带 courseId/libraryFolderId/resourceId/term"""
        mock_session.polymas_query.return_value = _detail_body(finished=True)
        _player(mock_session).play_video(_course(), _video(), mock_mgr)
        call = mock_session.polymas_query.call_args_list[0]
        assert "resource/detail" in call.args[0]
        assert call.args[1] == {
            "courseId": "3001",
            "libraryFolderId": "lib1",
            "resourceId": "r1",
            "term": 20271,
        }
        mock_mgr.library_folder_id.assert_called_once()


class TestPlayCourse:
    @patch("zhs.polymas.video.time.sleep")
    def test_iterates_all_videos(self, _sleep: MagicMock, mock_session: MagicMock, mock_mgr: MagicMock) -> None:
        """play_course 遍历全部视频节点"""
        mock_mgr.get_video_nodes.return_value = [_video("r1"), _video("r2")]
        player = _player(mock_session)
        with patch.object(player, "play_video") as mock_pv:
            player.play_course(_course(), mock_mgr)
        assert mock_pv.call_count == 2

    @patch("zhs.polymas.video.time.sleep")
    def test_single_video_failure_isolated(
        self,
        _sleep: MagicMock,
        mock_session: MagicMock,
        mock_mgr: MagicMock,
    ) -> None:
        """单个视频失败不中断整个课程"""
        mock_mgr.get_video_nodes.return_value = [_video("r1"), _video("r2")]
        player = _player(mock_session)
        with patch.object(player, "play_video", side_effect=[RuntimeError("boom"), None]) as mock_pv:
            player.play_course(_course(), mock_mgr)
        assert mock_pv.call_count == 2

    @patch("zhs.polymas.video.time.sleep")
    def test_empty_video_list(self, _sleep: MagicMock, mock_session: MagicMock, mock_mgr: MagicMock) -> None:
        """无视频节点 → 正常结束不报错"""
        mock_mgr.get_video_nodes.return_value = []
        _player(mock_session).play_course(_course(), mock_mgr)

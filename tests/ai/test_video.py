"""ai/video.py TDD — AiVideoPlayer"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.ai.video import AiVideoPlayer


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock()
    session.crypto = MagicMock()
    session.crypto.key_bytes = MagicMock(return_value=b"hw2fdlwcj4cs1mx7")
    session.urls = MagicMock()
    session.urls.ai = "https://kg-ai-run.zhihuishu.com"
    session.urls.newbase = "https://newbase.zhihuishu.com"
    return session


@pytest.fixture
def player(mock_session: MagicMock) -> AiVideoPlayer:
    """创建 AiVideoPlayer 实例"""
    return AiVideoPlayer(mock_session, speed=1.5)


class TestAiVideoPlayerInit:
    """AiVideoPlayer 初始化"""

    def test_default_speed(self, mock_session: MagicMock) -> None:
        """默认速度 1.5"""
        p = AiVideoPlayer(mock_session)
        assert p._speed == 1.5

    def test_custom_speed(self, mock_session: MagicMock) -> None:
        """自定义速度"""
        p = AiVideoPlayer(mock_session, speed=2.0)
        assert p._speed == 2.0


class TestAiQuery:
    """AI 查询方法"""

    def test_ai_query_uses_ai_key(self, player: AiVideoPlayer) -> None:
        """_ai_query 使用 ai_key"""
        with patch.object(player._session, "zhidao_query", return_value={"code": 200, "data": {}}) as mock_query:
            player._ai_query("https://example.com/api", {"test": 1})
            call_kwargs = mock_query.call_args
            assert call_kwargs[1]["key"] == player._session.crypto.key_bytes("ai_key")
            assert call_kwargs[1]["ok_code"] == 200
            assert call_kwargs[1]["content_type"] == "json"


class TestPlayVideo:
    """视频播放"""

    @patch("zhs.ai.video.time.sleep")
    def test_play_video_reports_progress(self, mock_sleep: MagicMock, player: AiVideoPlayer) -> None:
        """play_video 上报视频进度"""
        with (
            patch.object(player, "_ai_query", return_value={"data": [{"time": 100}]}),
            patch.object(player, "_watch_video"),
            patch.object(player, "_report_video_progress", return_value=True) as mock_report,
        ):
            player.play_video(1, 2, 3, 4)
            # 应该多次上报进度
            assert mock_report.call_count > 0

    @patch("zhs.ai.video.time.sleep")
    def test_play_video_with_override_speed(self, mock_sleep: MagicMock, player: AiVideoPlayer) -> None:
        """play_video 支持覆盖速度"""
        with (
            patch.object(player, "_ai_query", return_value={"data": [{"time": 100}]}),
            patch.object(player, "_watch_video"),
            patch.object(player, "_report_video_progress", return_value=True),
        ):
            player.play_video(1, 2, 3, 4, speed=2.0)
            # 不抛异常即通过


class TestReportVideoProgress:
    """视频进度上报"""

    def test_report_success(self, player: AiVideoPlayer) -> None:
        """上报成功返回 True"""
        with patch.object(player, "_ai_query", return_value={"code": 200}):
            result = player._report_video_progress(1, 2, 3, 4, 50)
            assert result is True

    def test_report_failure(self, player: AiVideoPlayer) -> None:
        """上报失败返回 False"""
        with patch.object(player, "_ai_query", side_effect=Exception("Network error")):
            result = player._report_video_progress(1, 2, 3, 4, 50)
            assert result is False

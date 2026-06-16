"""Task 4.3 — hike/video.py TDD"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.exceptions import TimeLimitExceeded
from zhs.hike.models import ResourceNode
from zhs.hike.video import HikeVideoPlayer
from zhs.session import ZhsSession


@pytest.fixture
def mock_session() -> MagicMock:
    """创建 mock ZhsSession"""
    session = MagicMock(spec=ZhsSession)
    session.uuid = "test-uuid-123"
    session.urls = MagicMock()
    session.urls.hike = "https://hike.zhihuishu.com"
    session.crypto = MagicMock()
    session.crypto.hike_salt = "o6xpt3b#Qy$Z"
    return session


class TestTraverse:
    """_traverse 递归遍历资源树"""

    def test_video_type(self, mock_session: MagicMock) -> None:
        """data_type=3 → play_video"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate({"id": 100, "name": "视频", "dataType": 3, "totalTime": 600, "fileId": 999})
        with patch.object(player, "play_video") as mock_play:
            player._traverse("course1", node)
            mock_play.assert_called_once_with("course1", 999, 0)

    def test_none_with_file_id(self, mock_session: MagicMock) -> None:
        """data_type=None + file_id → play_file"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate({"id": 100, "name": "文件", "dataType": None, "totalTime": 0, "fileId": 888})
        with patch.object(player, "play_file") as mock_file:
            player._traverse("course1", node)
            mock_file.assert_called_once_with("course1", 888)

    def test_none_without_file_id(self, mock_session: MagicMock) -> None:
        """data_type=None + 无 file_id → 跳过"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate({"id": 100, "name": "测验", "dataType": None, "totalTime": 0})
        with patch.object(player, "play_video") as mock_play, patch.object(player, "play_file") as mock_file:
            player._traverse("course1", node)
            mock_play.assert_not_called()
            mock_file.assert_not_called()

    def test_unknown_type_with_file_id(self, mock_session: MagicMock) -> None:
        """非标准 data_type + file_id → play_file"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate(
            {"id": 100, "name": "文档", "dataType": 1, "totalTime": 0, "fileId": 777, "fileName": "doc.pdf"}
        )
        with patch.object(player, "play_file") as mock_file:
            player._traverse("course1", node)
            mock_file.assert_called_once_with("course1", 777)

    def test_unknown_type_without_file_id(self, mock_session: MagicMock) -> None:
        """非标准 data_type + 无 file_id → 跳过 + 日志"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate({"id": 100, "name": "讨论", "dataType": 5, "totalTime": 0})
        with patch.object(player, "play_video") as mock_play, patch.object(player, "play_file") as mock_file:
            player._traverse("course1", node)
            mock_play.assert_not_called()
            mock_file.assert_not_called()

    def test_already_watched_skip(self, mock_session: MagicMock) -> None:
        """已看完视频跳过（study_time >= total_time * threshold）"""
        player = HikeVideoPlayer(mock_session, end_threshold=0.91)
        node = ResourceNode.model_validate(
            {"id": 100, "name": "视频", "dataType": 3, "studyTime": 550, "totalTime": 600, "fileId": 999}
        )
        with patch.object(player, "play_video") as mock_play:
            player._traverse("course1", node)
            mock_play.assert_not_called()

    def test_recursive_child_list(self, mock_session: MagicMock) -> None:
        """有 child_list → 递归遍历子节点"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate(
            {
                "id": 1,
                "name": "章节",
                "childList": [
                    {"id": 2, "name": "视频", "dataType": 3, "totalTime": 600, "fileId": 100},
                    {"id": 3, "name": "文件", "dataType": 1, "totalTime": 0, "fileId": 200, "fileName": "a.pdf"},
                ],
            }
        )
        with patch.object(player, "play_video") as mock_play, patch.object(player, "play_file") as mock_file:
            player._traverse("course1", node)
            mock_play.assert_called_once_with("course1", 100, 0)
            mock_file.assert_called_once_with("course1", 200)

    def test_study_time_none_defaults_to_zero(self, mock_session: MagicMock) -> None:
        """studyTime 为 None 时默认 0"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate(
            {"id": 100, "name": "视频", "dataType": 3, "studyTime": None, "totalTime": 600, "fileId": 999}
        )
        with patch.object(player, "play_video") as mock_play:
            player._traverse("course1", node)
            mock_play.assert_called_once_with("course1", 999, 0)

    def test_exception_isolation(self, mock_session: MagicMock) -> None:
        """单个视频失败不中断遍历"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate(
            {
                "id": 1,
                "name": "章节",
                "childList": [
                    {"id": 2, "name": "视频1", "dataType": 3, "totalTime": 600, "fileId": 100},
                    {"id": 3, "name": "视频2", "dataType": 3, "totalTime": 600, "fileId": 101},
                ],
            }
        )
        with patch.object(player, "play_video", side_effect=[Exception("fail"), None]) as mock_play:
            player._traverse("course1", node)
            # 第二个视频仍然被调用
            assert mock_play.call_count == 2

    def test_time_limit_exceeded_stops(self, mock_session: MagicMock) -> None:
        """TimeLimitExceeded 停止遍历并向上传播"""
        player = HikeVideoPlayer(mock_session)
        node = ResourceNode.model_validate(
            {
                "id": 1,
                "name": "章节",
                "childList": [
                    {"id": 2, "name": "视频1", "dataType": 3, "totalTime": 600, "fileId": 100},
                    {"id": 3, "name": "视频2", "dataType": 3, "totalTime": 600, "fileId": 101},
                ],
            }
        )
        with patch.object(player, "play_video", side_effect=TimeLimitExceeded("limit")) as mock_play:
            with pytest.raises(TimeLimitExceeded):
                player._traverse("course1", node)
            # 第一个视频触发 TimeLimitExceeded，不再遍历第二个
            assert mock_play.call_count == 1


class TestPlayVideo:
    """play_video 播放视频"""

    def test_calls_stu_view_file(self, mock_session: MagicMock) -> None:
        """调用 stuViewFile 获取视频信息"""
        mock_session.hike_query.return_value = {
            "rt": {"fileId": 100, "dataId": 200, "totalTime": 120},
        }
        player = HikeVideoPlayer(mock_session, speed=10, end_threshold=1.0)
        with (
            patch.object(player, "_watch_video"),
            patch.object(player, "save_stu_study_record", side_effect=lambda *a, **kw: int(a[3] + 10)),
            patch("zhs.hike.video.time.sleep"),
            patch("zhs.hike.video.random", return_value=0),
        ):
            player.play_video("course1", 100, 0)
        # 验证 stuViewFile 被调用
        calls = mock_session.hike_query.call_args_list
        assert any("stuViewFile" in str(c) for c in calls)

    def test_save_stu_study_record_overwrites_time(self, mock_session: MagicMock) -> None:
        """saveStuStudyRecord 返回值覆盖 played_time"""
        mock_session.hike_query.return_value = {
            "rt": {"fileId": 100, "dataId": 200, "totalTime": 120},
        }
        player = HikeVideoPlayer(mock_session, speed=10, end_threshold=1.0)
        with (
            patch.object(player, "_watch_video"),
            patch.object(player, "save_stu_study_record", side_effect=lambda *a, **kw: int(a[3] + 10)) as mock_save,
            patch("zhs.hike.video.time.sleep"),
            patch("zhs.hike.video.random", return_value=0),
        ):
            player.play_video("course1", 100, 0)
        # save_stu_study_record 应该被调用，返回值覆盖时间
        assert mock_save.called


class TestPlayFile:
    """play_file 标记文件已查看"""

    def test_calls_stu_view_file(self, mock_session: MagicMock) -> None:
        """调用 stuViewFile 标记文件"""
        mock_session.hike_query.return_value = {
            "rt": {"fileId": 100, "dataId": 200, "totalTime": 0},
        }
        player = HikeVideoPlayer(mock_session)
        with patch("zhs.hike.video.time.sleep"), patch("zhs.hike.video.random", return_value=0):
            player.play_file("course1", 100)
        calls = mock_session.hike_query.call_args_list
        assert any("stuViewFile" in str(c) for c in calls)

    def test_catches_key_error(self, mock_session: MagicMock) -> None:
        """play_file try/except 防护 KeyError"""
        mock_session.hike_query.return_value = {"rt": {}}
        player = HikeVideoPlayer(mock_session)
        with patch("zhs.hike.video.time.sleep"), patch("zhs.hike.video.random", return_value=0):
            # 不应抛出异常
            player.play_file("course1", 100)


class TestSaveStuStudyRecord:
    """save_stu_study_record 上报学习进度"""

    def test_api_call_with_signature(self, mock_session: MagicMock) -> None:
        """调用 API 时需要签名"""
        mock_session.hike_query.return_value = {"rt": 50}
        player = HikeVideoPlayer(mock_session)
        result = player.save_stu_study_record("course1", 100, 60, 30, 1000000)
        assert result == 50
        # 验证 sig=True
        call_kwargs = mock_session.hike_query.call_args[1]
        assert call_kwargs.get("sig") is True

    def test_returns_rt_value(self, mock_session: MagicMock) -> None:
        """返回 rt 值作为新的 played_time"""
        mock_session.hike_query.return_value = {"rt": 75}
        player = HikeVideoPlayer(mock_session)
        result = player.save_stu_study_record("course1", 100, 60, 30, 1000000)
        assert result == 75


class TestDefaultSpeed:
    """默认速度"""

    def test_default_speed(self, mock_session: MagicMock) -> None:
        """默认速度 1.25"""
        player = HikeVideoPlayer(mock_session)
        assert player.speed == 1.25

    def test_custom_speed(self, mock_session: MagicMock) -> None:
        """自定义速度"""
        player = HikeVideoPlayer(mock_session, speed=2.0)
        assert player.speed == 2.0

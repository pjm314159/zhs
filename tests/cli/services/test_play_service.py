"""cli/services/play_service.py 单元测试

覆盖 run_courses / run_ai / run_ai_by_str / run_zhidao / run_hike / run_all。
"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.services.play_service import (
    run_ai,
    run_ai_by_str,
    run_all,
    run_courses,
    run_hike,
    run_zhidao,
)


def _make_config() -> MagicMock:
    """创建 mock 配置"""
    config = MagicMock()
    config.video.zhidao_speed = 1.5
    config.video.hike_speed = 1.25
    config.video.ai_speed = 1.5
    config.video.ai_learn_optional = False
    config.threshold = 0.91
    config.limit = 0
    return config


class TestRunCourses:
    """run_courses"""

    def test_zhidao_course_routed(self) -> None:
        """含字母的课程路由到 run_zhidao"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.play_service.run_zhidao") as mock_run:
            run_courses(session, config, ["ABC123"], None)
        mock_run.assert_called_once_with(session, config, "ABC123")

    def test_hike_course_routed(self) -> None:
        """纯数字课程路由到 run_hike"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.play_service.run_hike") as mock_run:
            run_courses(session, config, ["12345"], None)
        mock_run.assert_called_once_with(session, config, "12345")

    def test_ai_course_routed(self) -> None:
        """--type ai 路由到 run_ai_by_str"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.play_service.run_ai_by_str") as mock_run:
            run_courses(session, config, ["100:200"], "ai")
        mock_run.assert_called_once_with(session, config, "100:200")

    def test_multiple_courses_processed(self) -> None:
        """多个课程依次处理"""
        session = MagicMock()
        config = _make_config()
        with (
            patch("zhs.cli.services.play_service.run_zhidao") as mock_zhidao,
            patch("zhs.cli.services.play_service.run_hike") as mock_hike,
        ):
            run_courses(session, config, ["ABC123", "12345"], None)
        mock_zhidao.assert_called_once_with(session, config, "ABC123")
        mock_hike.assert_called_once_with(session, config, "12345")

    def test_course_exception_does_not_stop_loop(self, capsys: pytest.CaptureFixture[str]) -> None:
        """单个课程异常不中断后续课程"""
        session = MagicMock()
        config = _make_config()
        with (
            patch("zhs.cli.services.play_service.run_zhidao", side_effect=Exception("err")),
            patch("zhs.cli.services.play_service.run_hike") as mock_hike,
        ):
            run_courses(session, config, ["ABC123", "12345"], None)
        # 第二个课程仍应被处理
        mock_hike.assert_called_once()
        captured = capsys.readouterr()
        assert "处理失败" in captured.out

    def test_unknown_type_prints_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """未知类型打印警告并跳过"""
        session = MagicMock()
        config = _make_config()
        # 通过 mock detect_course_type 返回未知类型
        with patch("zhs.cli.services.play_service.detect_course_type", return_value="unknown"):
            run_courses(session, config, ["test"], None)
        captured = capsys.readouterr()
        assert "未知的课程类型" in captured.out


class TestRunAi:
    """run_ai"""

    @patch("zhs.ai.course.AiCourseManager")
    def test_calls_run_course_with_no_homework(self, mock_mgr_cls: MagicMock) -> None:
        """调用 run_course 且 no_homework=True"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        run_ai(session, config, 100, 200)

        mock_mgr.run_course.assert_called_once()
        call_kwargs = mock_mgr.run_course.call_args.kwargs
        assert call_kwargs["no_homework"] is True
        assert call_kwargs["speed"] == config.video.ai_speed
        assert call_kwargs["learn_optional"] == config.video.ai_learn_optional

    @patch("zhs.ai.course.AiCourseManager")
    def test_passes_video_config(self, mock_mgr_cls: MagicMock) -> None:
        """传递 video_config 参数"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        run_ai(session, config, 100, 200)

        call_kwargs = mock_mgr.run_course.call_args.kwargs
        assert call_kwargs["video_config"] == config.video


class TestRunAiByStr:
    """run_ai_by_str"""

    def test_valid_string_calls_run_ai(self) -> None:
        """合法字符串调用 run_ai"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.play_service.run_ai") as mock_run:
            run_ai_by_str(session, config, "100:200")
        mock_run.assert_called_once_with(session, config, 100, 200)

    def test_invalid_string_does_nothing(self) -> None:
        """非法字符串不调用 run_ai"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.play_service.run_ai") as mock_run:
            run_ai_by_str(session, config, "invalid")
        mock_run.assert_not_called()


class TestRunZhidao:
    """run_zhidao"""

    @patch("zhs.zhidao.video.ZhidaoVideoPlayer")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_calls_play_course(
        self,
        mock_mgr_cls: MagicMock,
        mock_player_cls: MagicMock,
    ) -> None:
        """调用 play_course"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_player = MagicMock()
        mock_player_cls.return_value = mock_player
        mock_ctx = MagicMock()
        mock_mgr.get_context.return_value = mock_ctx

        run_zhidao(session, config, "ABC123")

        mock_mgr.get_context.assert_called_once_with("ABC123")
        mock_player.play_course.assert_called_once_with("ABC123", mock_ctx)

    @patch("zhs.zhidao.video.ZhidaoVideoPlayer")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_player_uses_config_speed(
        self,
        mock_mgr_cls: MagicMock,
        mock_player_cls: MagicMock,
    ) -> None:
        """player 使用配置中的 speed"""
        session = MagicMock()
        config = _make_config()
        config.video.zhidao_speed = 2.0
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        run_zhidao(session, config, "ABC123")

        mock_player_cls.assert_called_once()
        call_kwargs = mock_player_cls.call_args.kwargs
        assert call_kwargs["speed"] == 2.0


class TestRunHike:
    """run_hike"""

    @patch("zhs.hike.video.HikeVideoPlayer")
    @patch("zhs.hike.course.HikeCourseManager")
    def test_calls_play_course(
        self,
        mock_mgr_cls: MagicMock,
        mock_player_cls: MagicMock,
    ) -> None:
        """调用 play_course"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_player = MagicMock()
        mock_player_cls.return_value = mock_player
        mock_root = MagicMock()
        mock_mgr.get_context.return_value = mock_root

        run_hike(session, config, "12345")

        mock_mgr.get_context.assert_called_once_with("12345")
        mock_player.play_course.assert_called_once_with("12345", mock_root)


class TestRunAll:
    """run_all"""

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_default_runs_all_three_types(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """默认（None）运行 zhidao + hike + ai"""
        session = MagicMock()
        config = _make_config()
        mock_zhidao = MagicMock()
        mock_zhidao_cls.return_value = mock_zhidao
        mock_zhidao.get_course_list.return_value = []
        mock_hike = MagicMock()
        mock_hike_cls.return_value = mock_hike
        mock_hike.get_course_list.return_value = []
        mock_ai = MagicMock()
        mock_ai_cls.return_value = mock_ai
        mock_ai.get_ai_course_list.return_value = []

        run_all(session, config, None)

        mock_zhidao.get_course_list.assert_called_once()
        mock_hike.get_course_list.assert_called_once()
        mock_ai.get_ai_course_list.assert_called_once()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_type_zhidao_only_runs_zhidao(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type zhidao 只运行 zhidao"""
        session = MagicMock()
        config = _make_config()
        mock_zhidao = MagicMock()
        mock_zhidao_cls.return_value = mock_zhidao
        mock_zhidao.get_course_list.return_value = []

        run_all(session, config, "zhidao")

        mock_zhidao.get_course_list.assert_called_once()
        mock_hike_cls.assert_not_called()
        mock_ai_cls.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_type_hike_only_runs_hike(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type hike 只运行 hike"""
        session = MagicMock()
        config = _make_config()
        mock_hike = MagicMock()
        mock_hike_cls.return_value = mock_hike
        mock_hike.get_course_list.return_value = []

        run_all(session, config, "hike")

        mock_hike.get_course_list.assert_called_once()
        mock_zhidao_cls.assert_not_called()
        mock_ai_cls.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_type_ai_only_runs_ai(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type ai 只运行 ai"""
        session = MagicMock()
        config = _make_config()
        mock_ai = MagicMock()
        mock_ai_cls.return_value = mock_ai
        mock_ai.get_ai_course_list.return_value = []

        run_all(session, config, "ai")

        mock_ai.get_ai_course_list.assert_called_once()
        mock_zhidao_cls.assert_not_called()
        mock_hike_cls.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_type_auto_runs_all(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type auto 运行全部"""
        session = MagicMock()
        config = _make_config()
        mock_zhidao = MagicMock()
        mock_zhidao_cls.return_value = mock_zhidao
        mock_zhidao.get_course_list.return_value = []
        mock_hike = MagicMock()
        mock_hike_cls.return_value = mock_hike
        mock_hike.get_course_list.return_value = []
        mock_ai = MagicMock()
        mock_ai_cls.return_value = mock_ai
        mock_ai.get_ai_course_list.return_value = []

        run_all(session, config, "auto")

        mock_zhidao.get_course_list.assert_called_once()
        mock_hike.get_course_list.assert_called_once()
        mock_ai.get_ai_course_list.assert_called_once()

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_zhidao_list_exception_handled(
        self,
        mock_zhidao_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """知到课程列表获取异常被捕获"""
        session = MagicMock()
        config = _make_config()
        mock_zhidao_cls.return_value.get_course_list.side_effect = Exception("err")

        run_all(session, config, "zhidao")
        captured = capsys.readouterr()
        assert "获取知到课程列表失败" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_zhidao_course_exception_continues(
        self,
        mock_zhidao_cls: MagicMock,
        mock_ai_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """单个知到课程异常不中断"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.secret = "ABC123"
        mock_course.course_name = "测试课程"
        mock_zhidao_cls.return_value.get_course_list.return_value = [mock_course]
        mock_zhidao_cls.return_value.get_context.side_effect = Exception("err")
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        run_all(session, config, None)
        captured = capsys.readouterr()
        assert "处理失败" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    def test_ai_course_missing_ids_skipped(
        self,
        mock_ai_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AI 课程缺少 courseId 或 classId 跳过"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.return_value = [
            {"courseName": "测试课程"}  # 缺少 courseId 和 classId
        ]

        run_all(session, config, "ai")
        captured = capsys.readouterr()
        assert "缺少 courseId 或 classId" in captured.out

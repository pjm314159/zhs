"""Task 7.1 — __main__.py CLI TDD"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from zhs.__main__ import app, detect_course_type

runner = CliRunner()


def _make_mock_config() -> MagicMock:
    """创建标准 mock 配置对象"""
    mock_config = MagicMock()
    mock_config.save_cookies = True
    mock_config.zhidao_speed = 1.5
    mock_config.hike_speed = 1.25
    mock_config.threshold = 0.91
    mock_config.limit = 0
    mock_config.log_level = "INFO"
    mock_config.tree_view = True
    mock_config.progressbar_view = True
    mock_config.qr_extra = {}
    mock_config.image_path = ""
    mock_config.proxies = {}
    return mock_config


class TestHelp:
    """CLI 帮助"""

    def test_help_no_error(self) -> None:
        """zhs --help 不报错"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "智慧树" in result.output or "zhs" in result.output

    def test_login_help_no_error(self) -> None:
        """zhs login --help 不报错"""
        result = runner.invoke(app, ["login", "--help"])
        assert result.exit_code == 0
        assert "登录" in result.output


class TestDetectCourseType:
    """课程类型检测辅助函数"""

    def test_letters_route_zhidao(self) -> None:
        """含字母 → zhidao"""
        assert detect_course_type("ABC123") == "zhidao"

    def test_pure_digits_route_hike(self) -> None:
        """纯数字 → hike"""
        assert detect_course_type("12345") == "hike"

    def test_type_override(self) -> None:
        """显式 type 覆盖"""
        assert detect_course_type("ABC123", "hike") == "hike"
        assert detect_course_type("12345", "zhidao") == "zhidao"
        assert detect_course_type("12345", "ai") == "ai"


class TestNoLogin:
    """未登录时提示"""

    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_no_cookies_prompts_login(self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock) -> None:
        """未登录时提示运行 zhs login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # cookies.json 不存在 → _try_restore_cookies 返回 False
        with patch("zhs.__main__._try_restore_cookies", return_value=False):
            result = runner.invoke(app, ["-c", "ABC123"])
        assert result.exit_code == 1
        assert "zhs login" in result.output


class TestLoginSubcommand:
    """login 子命令"""

    @patch("zhs.__main__._do_login")
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_login_calls_do_login(
        self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock, mock_do_login: MagicMock
    ) -> None:
        """zhs login 调用 _do_login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner.invoke(app, ["login"])
        mock_do_login.assert_called_once()


class TestCourseTypeDetection:
    """课程类型路由"""

    @patch("zhs.__main__._run_zhidao")
    @patch("zhs.__main__._try_restore_cookies", return_value=True)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_course_with_letters_routes_zhidao(
        self,
        mock_config_mgr: MagicMock,
        mock_session_cls: MagicMock,
        mock_restore: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """含字母课程 ID → 路由到知到"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner.invoke(app, ["-c", "ABC123"])
        mock_run_zhidao.assert_called_once()

    @patch("zhs.__main__._run_hike")
    @patch("zhs.__main__._try_restore_cookies", return_value=True)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_numeric_course_routes_hike(
        self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock, mock_restore: MagicMock, mock_run_hike: MagicMock
    ) -> None:
        """纯数字课程 ID → 路由到 Hike"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner.invoke(app, ["-c", "12345"])
        mock_run_hike.assert_called_once()


class TestTypeOverride:
    """--type 显式指定"""

    @patch("zhs.__main__._run_hike")
    @patch("zhs.__main__._try_restore_cookies", return_value=True)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_type_hike_override(
        self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock, mock_restore: MagicMock, mock_run_hike: MagicMock
    ) -> None:
        """--type hike 显式指定"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # ABC123 含字母但 --type hike 强制走 Hike
        runner.invoke(app, ["-c", "ABC123", "--type", "hike"])
        mock_run_hike.assert_called_once()


class TestCLIOverridesConfig:
    """CLI 参数覆盖配置值"""

    @patch("zhs.__main__._run_zhidao")
    @patch("zhs.__main__._try_restore_cookies", return_value=True)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_speed_override(
        self,
        mock_config_mgr: MagicMock,
        mock_session_cls: MagicMock,
        mock_restore: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """--speed 覆盖 config 中的 speed"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner.invoke(app, ["-c", "ABC123", "--speed", "2.0"])
        # --speed 同时覆盖 zhidao_speed 和 hike_speed
        assert mock_config.zhidao_speed == 2.0
        assert mock_config.hike_speed == 2.0

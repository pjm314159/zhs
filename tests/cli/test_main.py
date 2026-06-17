"""__main__.py CLI TDD — 命令式接口"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from zhs.__main__ import _detect_course_type, _validate_course_type, app

runner = CliRunner()


def _make_mock_config() -> MagicMock:
    """创建标准 mock 配置对象"""
    mock_config = MagicMock()
    mock_config.save_cookies = True
    mock_config.zhidao_speed = 1.5
    mock_config.hike_speed = 1.25
    mock_config.ai_speed = 1.5
    mock_config.threshold = 0.91
    mock_config.limit = 0
    mock_config.log_level = "INFO"
    mock_config.tree_view = True
    mock_config.progressbar_view = True
    mock_config.qr_extra = {}
    mock_config.image_path = ""
    mock_config.proxies = {}
    mock_config.homework_threshold = 100
    mock_config.max_submit = 3
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

    def test_play_help_no_error(self) -> None:
        """zhs play --help 不报错"""
        result = runner.invoke(app, ["play", "--help"])
        assert result.exit_code == 0
        assert "刷视频" in result.output or "play" in result.output

    def test_homework_help_no_error(self) -> None:
        """zhs homework --help 不报错"""
        result = runner.invoke(app, ["homework", "--help"])
        assert result.exit_code == 0
        assert "作业" in result.output or "homework" in result.output

    def test_fetch_help_no_error(self) -> None:
        """zhs fetch --help 不报错"""
        result = runner.invoke(app, ["fetch", "--help"])
        assert result.exit_code == 0
        assert "课程" in result.output or "fetch" in result.output

    def test_init_help_no_error(self) -> None:
        """zhs init --help 不报错"""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0


class TestDetectCourseType:
    """课程类型检测辅助函数"""

    def test_letters_route_zhidao(self) -> None:
        """含字母 → zhidao"""
        assert _detect_course_type("ABC123") == "zhidao"

    def test_pure_digits_route_hike(self) -> None:
        """纯数字 → hike"""
        assert _detect_course_type("12345") == "hike"

    def test_type_override(self) -> None:
        """显式 type 覆盖"""
        assert _detect_course_type("ABC123", "hike") == "hike"
        assert _detect_course_type("12345", "zhidao") == "zhidao"
        assert _detect_course_type("12345", "ai") == "ai"


class TestNoLogin:
    """未登录时提示"""

    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_play_no_cookies_prompts_login(self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock) -> None:
        """zhs play 未登录时提示运行 zhs login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        with patch("zhs.__main__._try_restore_cookies", return_value=False):
            result = runner.invoke(app, ["play"])
        assert result.exit_code == 1
        assert "zhs login" in result.output

    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_homework_no_cookies_prompts_login(self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock) -> None:
        """zhs homework 未登录时提示运行 zhs login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        with patch("zhs.__main__._try_restore_cookies", return_value=False):
            result = runner.invoke(app, ["homework"])
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


class TestPlayCommand:
    """play 命令路由"""

    @patch("zhs.__main__._run_zhidao")
    @patch("zhs.__main__._load_config_and_session")
    def test_course_with_letters_routes_zhidao(
        self,
        mock_load: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """含字母课程 ID → 路由到知到"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "-c", "ABC123"])
        mock_run_zhidao.assert_called_once()

    @patch("zhs.__main__._run_hike")
    @patch("zhs.__main__._load_config_and_session")
    def test_numeric_course_routes_hike(
        self,
        mock_load: MagicMock,
        mock_run_hike: MagicMock,
    ) -> None:
        """纯数字课程 ID → 路由到 Hike"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "-c", "12345"])
        mock_run_hike.assert_called_once()

    @patch("zhs.__main__._run_ai_by_str")
    @patch("zhs.__main__._load_config_and_session")
    def test_ai_type_routes_ai(
        self,
        mock_load: MagicMock,
        mock_run_ai_by_str: MagicMock,
    ) -> None:
        """--type ai 路由到 AI"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "-c", "100:200", "--type", "ai"])
        mock_run_ai_by_str.assert_called_once()

    @patch("zhs.__main__._run_ai")
    @patch("zhs.__main__._load_config_and_session")
    def test_ai_course_ai_class_routes_ai(
        self,
        mock_load: MagicMock,
        mock_run_ai: MagicMock,
    ) -> None:
        """--ai-course + --ai-class 路由到 AI"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "--ai-course", "100", "--ai-class", "200"])
        mock_run_ai.assert_called_once()
        # 验证传入的是 int
        call_args = mock_run_ai.call_args[0]
        assert call_args[2] == 100
        assert call_args[3] == 200

    @patch("zhs.__main__._load_config_and_session")
    def test_tree_view_and_progressbar_always_enabled(
        self,
        mock_load: MagicMock,
    ) -> None:
        """tree_view / progressbar_view 默认启用"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        with patch("zhs.__main__._run_all"):
            runner.invoke(app, ["play"])
        assert mock_config.tree_view is True
        assert mock_config.progressbar_view is True


class TestPlayOverridesConfig:
    """play 命令 CLI 参数覆盖配置值"""

    @patch("zhs.__main__._run_all")
    @patch("zhs.__main__._load_config_and_session")
    def test_speed_override(
        self,
        mock_load: MagicMock,
        mock_run_all: MagicMock,
    ) -> None:
        """--speed 覆盖 config 中的 speed"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "--speed", "2.0"])
        # --speed 同时覆盖 zhidao_speed、hike_speed、ai_speed
        assert mock_config.zhidao_speed == 2.0
        assert mock_config.hike_speed == 2.0
        assert mock_config.ai_speed == 2.0


class TestHomeworkCommand:
    """homework 命令"""

    @patch("zhs.__main__._run_ai_homework_by_str")
    @patch("zhs.__main__._load_config_and_session")
    def test_homework_ai_type(
        self,
        mock_load: MagicMock,
        mock_run_ai_homework_by_str: MagicMock,
    ) -> None:
        """zhs homework --type ai 路由到 AI 作业"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "-c", "100:200", "--type", "ai"])
        mock_run_ai_homework_by_str.assert_called_once()

    @patch("zhs.__main__._run_ai_homework")
    @patch("zhs.__main__._load_config_and_session")
    def test_homework_ai_course_ai_class(
        self,
        mock_load: MagicMock,
        mock_run_ai_homework: MagicMock,
    ) -> None:
        """zhs homework --ai-course + --ai-class 路由到 AI 作业"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "--ai-course", "100", "--ai-class", "200"])
        mock_run_ai_homework.assert_called_once()
        call_args = mock_run_ai_homework.call_args[0]
        assert call_args[2] == 100
        assert call_args[3] == 200

    @patch("zhs.__main__._load_config_and_session")
    def test_homework_no_ai_disables_ai(
        self,
        mock_load: MagicMock,
    ) -> None:
        """--no-ai 禁用 AI"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "--no-ai"])
        assert mock_config.ai.enabled is False

    @patch("zhs.__main__._load_config_and_session")
    def test_homework_threshold_override(
        self,
        mock_load: MagicMock,
    ) -> None:
        """--homework-threshold 覆盖配置"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "--homework-threshold", "80"])
        assert mock_config.homework_threshold == 80

    @patch("zhs.__main__._load_config_and_session")
    def test_max_submit_override(
        self,
        mock_load: MagicMock,
    ) -> None:
        """--max-submit 覆盖配置"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "--max-submit", "5"])
        assert mock_config.max_submit == 5


class TestInitCommand:
    """init 命令"""

    def test_init_no_error(self) -> None:
        """zhs init 不报错"""
        result = runner.invoke(app, ["init"])
        # init 不需要登录，应该正常执行
        assert result.exit_code == 0


class TestExamCommand:
    """exam 命令（暂未实现）"""

    @patch("zhs.__main__._load_config_and_session")
    def test_exam_not_implemented(self, mock_load: MagicMock) -> None:
        """zhs exam 提示暂未实现"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        result = runner.invoke(app, ["exam"])
        assert result.exit_code == 1
        assert "暂未实现" in result.output

    def test_exam_help_no_error(self) -> None:
        """zhs exam --help 不报错"""
        result = runner.invoke(app, ["exam", "--help"])
        assert result.exit_code == 0


class TestValidateCourseType:
    """--type 参数校验"""

    def test_valid_types(self) -> None:
        """有效类型通过"""
        assert _validate_course_type("zhidao") == "zhidao"
        assert _validate_course_type("hike") == "hike"
        assert _validate_course_type("ai") == "ai"
        assert _validate_course_type("auto") == "auto"

    def test_none_passes(self) -> None:
        """None 通过"""
        assert _validate_course_type(None) is None

    def test_invalid_type_prints_error(self) -> None:
        """无效类型打印错误并返回 None"""
        result = _validate_course_type("asdf")
        assert result is None

    @patch("zhs.__main__._load_config_and_session")
    def test_play_with_invalid_type_shows_error(self, mock_load: MagicMock) -> None:
        """zhs play --type asdf 显示错误并退出"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        result = runner.invoke(app, ["play", "--type", "asdf"])
        assert "不支持的课程类型" in result.output
        assert result.exit_code == 1


class TestTypeFilterInRunAll:
    """--type 在全刷模式下过滤"""

    @patch("zhs.__main__._run_all")
    @patch("zhs.__main__._load_config_and_session")
    def test_type_ai_only_runs_ai(self, mock_load: MagicMock, mock_run_all: MagicMock) -> None:
        """zhs play --type ai 传递 type 到 _run_all"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "--type", "ai"])
        mock_run_all.assert_called_once()
        # 验证 course_type 参数传入了 "ai"
        call_args = mock_run_all.call_args
        assert call_args[0][2] == "ai"

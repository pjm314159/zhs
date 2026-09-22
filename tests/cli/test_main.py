"""__main__.py CLI TDD — 命令式接口"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from zhs.__main__ import _detect_course_type, _validate_course_type, app

runner = CliRunner()


def _make_mock_config() -> MagicMock:
    """创建标准 mock 配置对象"""
    mock_config = MagicMock()
    mock_config.save_cookies = True
    mock_config.threshold = 0.91
    mock_config.limit = 0

    # 嵌套配置
    mock_config.video = MagicMock()
    mock_config.video.zhidao_speed = 1.5
    mock_config.video.hike_speed = 1.25
    mock_config.video.ai_speed = 1.5

    mock_config.homework = MagicMock()
    mock_config.homework.threshold = 100
    mock_config.homework.max_submit = 3

    mock_config.display = MagicMock()
    mock_config.display.log_level = "INFO"

    mock_config.proxies = MagicMock()
    mock_config.proxies.to_dict = MagicMock(return_value={})

    mock_config.qr = MagicMock()
    mock_config.qr.image_path = ""

    mock_config.ai = MagicMock()
    mock_config.ai.enabled = True
    mock_config.ai.use_builtin_ai = True

    mock_config.question_bank = MagicMock()
    mock_config.question_bank.enabled = True

    mock_config.urls = MagicMock()
    mock_config.crypto = MagicMock()
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

    def test_letters_rejected(self) -> None:
        """含字母的 recruitAndCourseId 传给 -c → ValueError"""
        with pytest.raises(ValueError, match="recruitAndCourseId 请通过 --url 传入"):
            _detect_course_type("ABC123")

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

    @patch("zhs.cli.bootstrap.try_restore_cookies", return_value=False)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_play_no_cookies_prompts_login(
        self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock, mock_restore: MagicMock
    ) -> None:
        """zhs play 未登录时提示运行 zhs login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        result = runner.invoke(app, ["play"])
        assert result.exit_code == 1
        assert "zhs login" in result.output

    @patch("zhs.cli.bootstrap.try_restore_cookies", return_value=False)
    @patch("zhs.__main__.ZhsSession")
    @patch("zhs.__main__.ConfigManager")
    def test_homework_no_cookies_prompts_login(
        self, mock_config_mgr: MagicMock, mock_session_cls: MagicMock, mock_restore: MagicMock
    ) -> None:
        """zhs homework 未登录时提示运行 zhs login"""
        mock_config = _make_mock_config()
        mock_config_mgr.return_value.load.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

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
    def test_rac_id_via_course_arg_rejected(
        self,
        mock_load: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """-c 传 recruitAndCourseId → 报错提示改用 --url，不刷课"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        result = runner.invoke(app, ["play", "-c", "ABC123"])
        assert "recruitAndCourseId" in result.output
        assert "--url" in result.output
        mock_run_zhidao.assert_not_called()

    @patch("zhs.__main__._run_zhidao")
    @patch("zhs.__main__._resolve_course_id")
    @patch("zhs.__main__._load_config_and_session")
    def test_numeric_course_id_routes_zhidao_with_rac(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """-c 传数字 courseId → 反查出 rac_id 后路由到知到"""
        from zhs.cli.course_resolver import ResolvedCourse

        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)
        mock_resolve.return_value = ResolvedCourse(type="zhidao", course_id=1000008156, rac_id="rac_abc")

        runner.invoke(app, ["play", "-c", "1000008156"])
        mock_run_zhidao.assert_called_once()
        assert mock_run_zhidao.call_args.args[2] == "rac_abc"

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
        assert mock_config.video.zhidao_speed == 2.0
        assert mock_config.video.hike_speed == 2.0
        assert mock_config.video.ai_speed == 2.0


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

    @patch("zhs.__main__._run_zhidao_homework")
    @patch("zhs.__main__._resolve_course_id")
    @patch("zhs.__main__._load_config_and_session")
    def test_homework_zhidao_course_routes_with_recruit_id(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run_zhidao_homework: MagicMock,
    ) -> None:
        """homework -c <知到 courseId> → 解析出 recruit_id 后运行知到作业"""
        from zhs.cli.course_resolver import ResolvedCourse

        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)
        mock_resolve.return_value = ResolvedCourse(
            type="zhidao", course_id=1000008156, rac_id="rac_abc", recruit_id=789
        )

        runner.invoke(app, ["homework", "-c", "1000008156"])

        mock_session.exam_sso_login.assert_called_once()
        mock_run_zhidao_homework.assert_called_once()
        assert mock_run_zhidao_homework.call_args.args[2] == "789"
        assert mock_run_zhidao_homework.call_args.args[3] == 1000008156

    @patch("zhs.__main__._run_zhidao_homework")
    @patch("zhs.__main__._resolve_course_id")
    @patch("zhs.__main__._load_config_and_session")
    def test_homework_zhidao_missing_recruit_id_skipped(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run_zhidao_homework: MagicMock,
    ) -> None:
        """知到课程缺少 recruitId → 跳过并提示，不调用作业流程"""
        from zhs.cli.course_resolver import ResolvedCourse

        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)
        mock_resolve.return_value = ResolvedCourse(type="zhidao", course_id=1000008156, rac_id="rac_abc")

        result = runner.invoke(app, ["homework", "-c", "1000008156"])

        assert "缺少 recruitId" in result.output
        mock_run_zhidao_homework.assert_not_called()
        mock_session.exam_sso_login.assert_not_called()

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
    def test_homework_no_question_bank_disables_bank(
        self,
        mock_load: MagicMock,
    ) -> None:
        """--no-question-bank 禁用题库"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["homework", "--no-question-bank"])
        assert mock_config.question_bank.enabled is False

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
        assert mock_config.homework.threshold == 80

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
        assert mock_config.homework.max_submit == 5


class TestInitCommand:
    """init 命令"""

    def test_init_no_error(self) -> None:
        """zhs init 不报错"""
        result = runner.invoke(app, ["init"])
        # init 不需要登录，应该正常执行
        assert result.exit_code == 0


class TestExamCommand:
    """exam 命令"""

    @patch("zhs.__main__._load_config_and_session")
    def test_exam_without_type_prompts_message(self, mock_load: MagicMock) -> None:
        """zhs exam 不带 --type ai 提示仅支持 AI 课程"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        result = runner.invoke(app, ["exam"])
        assert result.exit_code == 1
        assert "仅支持 AI 课程考试" in result.output

    def test_exam_help_no_error(self) -> None:
        """zhs exam --help 不报错"""
        result = runner.invoke(app, ["exam", "--help"])
        assert result.exit_code == 0

    @patch("zhs.__main__._run_ai_exam")
    @patch("zhs.__main__._load_config_and_session")
    def test_exam_no_question_bank_disables_bank(
        self,
        mock_load: MagicMock,
        mock_run_ai_exam: MagicMock,
    ) -> None:
        """--no-question-bank 禁用题库"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["exam", "--type", "ai", "--no-question-bank"])
        assert mock_config.question_bank.enabled is False


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
        """zhs play --type AI 传递 type 到 _run_all"""
        mock_config = _make_mock_config()
        mock_session = MagicMock()
        mock_load.return_value = (mock_config, mock_session)

        runner.invoke(app, ["play", "--type", "ai"])
        mock_run_all.assert_called_once()
        # 验证 course_type 参数传入了 "ai"
        call_args = mock_run_all.call_args
        assert call_args[0][2] == "ai"

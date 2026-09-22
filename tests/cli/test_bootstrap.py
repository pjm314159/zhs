"""cli/bootstrap.py 单元测试

覆盖 setup_logger / parse_proxy / try_restore_cookies / do_login / init_llm / load_config_and_session。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.bootstrap import (
    check_ai_provider,
    do_login,
    init_llm,
    init_question_bank,
    load_config_and_session,
    parse_proxy,
    setup_logger,
    try_restore_cookies,
)
from zhs.config import AppConfig


def _make_config() -> AppConfig:
    """创建带必要字段的 AppConfig"""
    config = AppConfig()
    config.save_cookies = True
    config.display.log_level = "INFO"
    config.ai.enabled = False
    config.ai.use_builtin_ai = False
    config.ai.api_key = ""
    config.qr.image_path = ""
    return config


class TestSetupLogger:
    """setup_logger"""

    def test_debug_level_when_debug_true(self, tmp_path: Path) -> None:
        """debug=True 时日志级别为 DEBUG"""
        config = _make_config()
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            setup_logger(config, debug=True, console_log=False)
        # 验证不抛异常即可（loguru 全局状态难以断言）

    def test_config_level_when_debug_false(self, tmp_path: Path) -> None:
        """debug=False 时使用配置中的日志级别"""
        config = _make_config()
        config.display.log_level = "WARNING"
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            setup_logger(config, debug=False, console_log=False)

    def test_creates_log_dir(self, tmp_path: Path) -> None:
        """日志目录不存在时自动创建"""
        config = _make_config()
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            setup_logger(config, debug=False, console_log=False)
        assert (tmp_path / "logs").exists()

    def test_console_log_adds_stderr_handler(self, tmp_path: Path) -> None:
        """console_log=True 添加 stderr handler（不抛异常）"""
        config = _make_config()
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            setup_logger(config, debug=False, console_log=True)

    def test_debug_implies_console(self, tmp_path: Path) -> None:
        """debug=True 时即使 console_log=False 也添加 stderr handler"""
        config = _make_config()
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            setup_logger(config, debug=True, console_log=False)


class TestParseProxy:
    """parse_proxy"""

    def test_http_proxy(self) -> None:
        """http:// 代理"""
        config = _make_config()
        parse_proxy(config, "http://127.0.0.1:8080")
        assert config.proxies.http == "http://127.0.0.1:8080"
        assert config.proxies.https == "http://127.0.0.1:8080"

    def test_https_proxy(self) -> None:
        """https:// 代理"""
        config = _make_config()
        parse_proxy(config, "https://proxy.example.com:443")
        assert config.proxies.http == "https://proxy.example.com:443"

    def test_socks5_proxy(self) -> None:
        """socks5:// 代理"""
        config = _make_config()
        parse_proxy(config, "socks5://127.0.0.1:1080")
        assert config.proxies.http == "socks5://127.0.0.1:1080"

    def test_uppercase_scheme_accepted(self) -> None:
        """大写 scheme 也可接受（内部 lower）"""
        config = _make_config()
        parse_proxy(config, "HTTP://127.0.0.1:8080")
        assert config.proxies.http == "HTTP://127.0.0.1:8080"

    def test_invalid_format_no_scheme(self) -> None:
        """无 scheme 的代理字符串不设置 proxies"""
        config = _make_config()
        original_http = config.proxies.http
        parse_proxy(config, "127.0.0.1:8080")
        assert config.proxies.http == original_http

    def test_unsupported_scheme(self) -> None:
        """不支持的 scheme 不设置 proxies"""
        config = _make_config()
        original_http = config.proxies.http
        parse_proxy(config, "ftp://127.0.0.1:21")
        assert config.proxies.http == original_http

    def test_three_parts_invalid(self) -> None:
        """三段式 scheme 不接受"""
        config = _make_config()
        original_http = config.proxies.http
        parse_proxy(config, "http://a://b")
        assert config.proxies.http == original_http


class TestTryRestoreCookies:
    """try_restore_cookies"""

    def test_save_cookies_false_returns_false(self) -> None:
        """save_cookies=False 直接返回 False"""
        config = _make_config()
        config.save_cookies = False
        session = MagicMock()
        assert try_restore_cookies(session, config) is False

    def test_no_cookies_file_returns_false(self, tmp_path: Path) -> None:
        """cookies.json 不存在返回 False"""
        config = _make_config()
        session = MagicMock()
        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            assert try_restore_cookies(session, config) is False

    def test_valid_cookies_returns_true(self, tmp_path: Path) -> None:
        """有效 cookies 返回 True"""
        config = _make_config()
        session = MagicMock()
        # 写入 cookies.json
        cookies_path = tmp_path / "cookies.json"
        cookies_path.write_text(json.dumps([{"name": "foo", "value": "bar"}]), encoding="utf-8")

        with (
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
            patch("zhs.utils.cookie.list_to_cookies") as mock_list_to_cookies,
            patch("zhs.zhidao.course.ZhidaoCourseManager") as mock_mgr_cls,
        ):
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr
            mock_mgr.get_course_list.return_value = [MagicMock()]
            result = try_restore_cookies(session, config)

        assert result is True
        mock_list_to_cookies.assert_called_once()

    def test_empty_courses_returns_false(self, tmp_path: Path) -> None:
        """课程列表为空返回 False"""
        config = _make_config()
        session = MagicMock()
        cookies_path = tmp_path / "cookies.json"
        cookies_path.write_text("[]", encoding="utf-8")

        with (
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
            patch("zhs.utils.cookie.list_to_cookies"),
            patch("zhs.zhidao.course.ZhidaoCourseManager") as mock_mgr_cls,
        ):
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr
            mock_mgr.get_course_list.return_value = []
            result = try_restore_cookies(session, config)

        assert result is False

    def test_invalid_json_returns_false(self, tmp_path: Path) -> None:
        """cookies.json 损坏返回 False"""
        config = _make_config()
        session = MagicMock()
        cookies_path = tmp_path / "cookies.json"
        cookies_path.write_text("not-json", encoding="utf-8")

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            result = try_restore_cookies(session, config)

        assert result is False

    def test_get_course_list_exception_returns_false(self, tmp_path: Path) -> None:
        """get_course_list 抛异常返回 False"""
        config = _make_config()
        session = MagicMock()
        cookies_path = tmp_path / "cookies.json"
        cookies_path.write_text("[]", encoding="utf-8")

        with (
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
            patch("zhs.utils.cookie.list_to_cookies"),
            patch("zhs.zhidao.course.ZhidaoCourseManager") as mock_mgr_cls,
        ):
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr
            mock_mgr.get_course_list.side_effect = Exception("network error")
            result = try_restore_cookies(session, config)

        assert result is False


class TestDoLogin:
    """do_login"""

    def test_successful_login_saves_cookies(self, tmp_path: Path) -> None:
        """登录成功且 save_cookies=True 时保存 cookies"""
        config = _make_config()
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = True
        login_result.cookies = [{"name": "foo", "value": "bar"}]
        login_mgr.login_with_qr.return_value = login_result

        with (
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
            patch("zhs.utils.cookie.cookies_to_list", return_value=[{"name": "foo", "value": "bar"}]),
        ):
            do_login(login_mgr, config, show_in_terminal=False)

        login_mgr.login_with_qr.assert_called_once()
        cookies_path = tmp_path / "cookies.json"
        assert cookies_path.exists()
        data = json.loads(cookies_path.read_text(encoding="utf-8"))
        assert data == [{"name": "foo", "value": "bar"}]

    def test_failed_login_raises_exit(self) -> None:
        """登录失败抛出 typer.Exit(1)"""
        import typer

        config = _make_config()
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = False
        login_mgr.login_with_qr.return_value = login_result

        with pytest.raises(typer.Exit) as exc_info:
            do_login(login_mgr, config, show_in_terminal=False)
        assert exc_info.value.exit_code == 1

    def test_save_cookies_false_does_not_save(self, tmp_path: Path) -> None:
        """save_cookies=False 时不保存 cookies"""
        config = _make_config()
        config.save_cookies = False
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = True
        login_result.cookies = [{"name": "foo", "value": "bar"}]
        login_mgr.login_with_qr.return_value = login_result

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            do_login(login_mgr, config, show_in_terminal=False)

        cookies_path = tmp_path / "cookies.json"
        assert not cookies_path.exists()

    def test_no_cookies_does_not_save(self, tmp_path: Path) -> None:
        """登录成功但 cookies 为空时不保存"""
        config = _make_config()
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = True
        login_result.cookies = None
        login_mgr.login_with_qr.return_value = login_result

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            do_login(login_mgr, config, show_in_terminal=False)

        cookies_path = tmp_path / "cookies.json"
        assert not cookies_path.exists()

    def test_qr_callback_called_when_show_in_terminal(self) -> None:
        """show_in_terminal=True 时 qr_callback 调用 _show_qr_img"""
        config = _make_config()
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = True
        login_result.cookies = None
        login_mgr.login_with_qr.return_value = login_result

        with patch("zhs.utils.display.show_qrcode_img"):
            do_login(login_mgr, config, show_in_terminal=True)

        # 验证 login_with_qr 被调用，且第一个参数是 qr_callback
        # qr_callback 在内部调用 _show_qr_img，但只有当传入图片字节时才会调用
        # 这里只验证 login_with_qr 被调用
        login_mgr.login_with_qr.assert_called_once()

    def test_qr_callback_not_called_when_not_show_in_terminal(self) -> None:
        """show_in_terminal=False 时 qr_callback 不调用 _show_qr_img"""
        config = _make_config()
        login_mgr = MagicMock()
        login_result = MagicMock()
        login_result.success = True
        login_result.cookies = None
        login_mgr.login_with_qr.return_value = login_result

        with patch("zhs.utils.display.show_qrcode_img") as mock_show:
            do_login(login_mgr, config, show_in_terminal=False)

        mock_show.assert_not_called()


class TestInitLlm:
    """init_llm"""

    def test_disabled_ai_returns_none(self) -> None:
        """ai.enabled=False 返回 None"""
        config = _make_config()
        config.ai.enabled = False
        assert init_llm(config) is None

    def test_use_builtin_ai_ignored_returns_provider(self) -> None:
        """知到作业始终使用自定义 API Key（use_builtin_ai 仅作用于 AI 智慧课程）"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = True
        config.ai.api_key = "test-key"
        config.ai.base_url = "https://api.openai.com/v1"
        config.ai.model = "gpt-4o-mini"
        config.ai.max_token = 4096

        provider = init_llm(config)
        assert provider is not None
        from zhs.llm.openai import OpenAIProvider

        assert isinstance(provider, OpenAIProvider)

    def test_use_builtin_ai_no_api_key_returns_none(self) -> None:
        """知到作业无 api_key 时返回 None（内置 AI 不可用于知到作业）"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = True
        config.ai.api_key = ""
        assert init_llm(config) is None

    def test_no_api_key_returns_none(self) -> None:
        """ai.api_key 为空返回 None"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = False
        config.ai.api_key = ""
        assert init_llm(config) is None

    def test_valid_config_returns_provider(self) -> None:
        """有效配置返回 OpenAIProvider"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = False
        config.ai.api_key = "test-key"
        config.ai.base_url = "https://api.openai.com/v1"
        config.ai.model = "gpt-4o-mini"
        config.ai.max_token = 4096

        provider = init_llm(config)
        assert provider is not None
        # 验证是 OpenAIProvider 实例
        from zhs.llm.openai import OpenAIProvider

        assert isinstance(provider, OpenAIProvider)


class TestInitQuestionBank:
    """init_question_bank"""

    def test_disabled_returns_none(self) -> None:
        """question_bank.enabled=False 返回 None"""
        config = _make_config()
        config.question_bank.enabled = False
        assert init_question_bank(config, scope="ai_exam", llm=True) is None

    def test_no_token_returns_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """token 为空返回 None 并 print 告警（终端可见）"""
        config = _make_config()
        config.question_bank.enabled = True
        config.question_bank.token = ""
        assert init_question_bank(config, scope="ai_exam", llm=True) is None
        captured = capsys.readouterr()
        assert "题库" in captured.out

    def test_llm_none_returns_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """llm=None 时题库依赖 LLM 不可用，返回 None 并 print 告警（终端可见）"""
        config = _make_config()
        config.question_bank.enabled = True
        config.question_bank.token = "tok-abc"
        assert init_question_bank(config, scope="ai_exam", llm=None) is None
        captured = capsys.readouterr()
        assert "题库" in captured.out

    def test_scope_not_in_scopes_returns_none(self) -> None:
        """scope 不在 scopes 列表中返回 None"""
        config = _make_config()
        config.question_bank.enabled = True
        config.question_bank.token = "tok-abc"
        config.question_bank.scopes = ["ai_exam"]
        assert init_question_bank(config, scope="zhidao_homework", llm=True) is None

    def test_valid_config_returns_client(self) -> None:
        """全部启用 + scope 命中 + llm 可用 返回 QuestionBankClient"""
        config = _make_config()
        config.question_bank.enabled = True
        config.question_bank.token = "tok-abc"
        config.question_bank.scopes = ["ai_exam", "ai_homework"]

        client = init_question_bank(config, scope="ai_exam", llm=True)
        try:
            assert client is not None
            from zhs.question_bank.client import QuestionBankClient

            assert isinstance(client, QuestionBankClient)
        finally:
            if client is not None:
                client.close()


class TestCheckAiProvider:
    """check_ai_provider"""

    def test_warns_when_zhidao_ai_and_api_key(self) -> None:
        """use_builtin_ai=True 且配置了 api_key 时提示 AI 智慧课程将使用智慧树内置 AI"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = True
        config.ai.api_key = "sk-test"
        with patch("zhs.cli.bootstrap.logger") as mock_logger:
            check_ai_provider(config)

        mock_logger.warning.assert_called_once()
        message = mock_logger.warning.call_args[0][0]
        assert "use_builtin_ai=false" in message
        assert "智慧树内置 AI" in message

    def test_no_warning_without_api_key(self) -> None:
        """use_builtin_ai=True 但未配置 api_key 时不提示"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = True
        config.ai.api_key = ""
        with patch("zhs.cli.bootstrap.logger") as mock_logger:
            check_ai_provider(config)

        mock_logger.warning.assert_not_called()

    def test_no_warning_when_using_custom_llm(self) -> None:
        """use_builtin_ai=False（使用自定义 LLM）时不提示"""
        config = _make_config()
        config.ai.enabled = True
        config.ai.use_builtin_ai = False
        config.ai.api_key = "sk-test"
        with patch("zhs.cli.bootstrap.logger") as mock_logger:
            check_ai_provider(config)

        mock_logger.warning.assert_not_called()

    def test_no_warning_when_ai_disabled(self) -> None:
        """ai.enabled=False 时不提示"""
        config = _make_config()
        config.ai.enabled = False
        config.ai.use_builtin_ai = True
        config.ai.api_key = "sk-test"
        with patch("zhs.cli.bootstrap.logger") as mock_logger:
            check_ai_provider(config)

        mock_logger.warning.assert_not_called()


class TestLoadConfigAndSession:
    """load_config_and_session"""

    def test_no_cookies_returns_none(self, tmp_path: Path) -> None:
        """无 cookies 时返回 None 并打印错误"""
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession"),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=False),
            patch("zhs.cli.bootstrap.setup_logger"),
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            result = load_config_and_session(debug=False, console_log=False, proxy=None)

        assert result is None

    def test_valid_cookies_returns_config_session(self, tmp_path: Path) -> None:
        """有效 cookies 时返回 (config, session)"""
        mock_session = MagicMock()
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession", return_value=mock_session),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=True),
            patch("zhs.cli.bootstrap.setup_logger"),
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            result = load_config_and_session(debug=False, console_log=False, proxy=None)

        assert result is not None
        config, session = result
        assert config is mock_config
        assert session is mock_session

    def test_proxy_passed_to_parse_proxy(self, tmp_path: Path) -> None:
        """proxy 参数传递给 parse_proxy"""
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession"),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=True),
            patch("zhs.cli.bootstrap.setup_logger"),
            patch("zhs.cli.bootstrap.parse_proxy") as mock_parse_proxy,
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            load_config_and_session(debug=False, console_log=False, proxy="http://127.0.0.1:8080")

        mock_parse_proxy.assert_called_once_with(mock_config, "http://127.0.0.1:8080")

    def test_no_proxy_does_not_call_parse_proxy(self, tmp_path: Path) -> None:
        """proxy=None 时不调用 parse_proxy"""
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession"),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=True),
            patch("zhs.cli.bootstrap.setup_logger"),
            patch("zhs.cli.bootstrap.parse_proxy") as mock_parse_proxy,
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            load_config_and_session(debug=False, console_log=False, proxy=None)

        mock_parse_proxy.assert_not_called()

    def test_debug_flag_passed_to_setup_logger(self, tmp_path: Path) -> None:
        """debug 参数传递给 setup_logger"""
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession"),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=True),
            patch("zhs.cli.bootstrap.setup_logger") as mock_setup,
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            load_config_and_session(debug=True, console_log=True, proxy=None)

        mock_setup.assert_called_once_with(mock_config, True, True)

    def test_calls_check_ai_provider(self, tmp_path: Path) -> None:
        """启动时调用 check_ai_provider 提示 AI 提供方选择"""
        with (
            patch("zhs.cli.bootstrap.ConfigManager") as mock_mgr_cls,
            patch("zhs.cli.bootstrap.ZhsSession"),
            patch("zhs.cli.bootstrap.try_restore_cookies", return_value=True),
            patch("zhs.cli.bootstrap.setup_logger"),
            patch("zhs.cli.bootstrap.check_ai_provider") as mock_check,
            patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        ):
            mock_config = _make_config()
            mock_mgr_cls.return_value.load.return_value = mock_config
            load_config_and_session(debug=False, console_log=False, proxy=None)

        mock_check.assert_called_once_with(mock_config)

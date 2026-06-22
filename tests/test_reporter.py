"""ProgressReporter / ConsoleReporter / SilentReporter 单元测试"""

from unittest.mock import patch

from zhs.reporter import ConsoleReporter, ProgressReporter, SilentReporter


class TestSilentReporter:
    """SilentReporter — 所有方法均为空操作"""

    def setup_method(self) -> None:
        self.reporter = SilentReporter()

    def test_print_no_output(self, capsys: object) -> None:
        """print 不产生输出"""
        self.reporter.print("hello")
        # SilentReporter 不应输出任何内容

    def test_tree_print_no_output(self) -> None:
        """tree_print 不产生输出"""
        self.reporter.tree_print("hello", depth=2)

    def test_tree_print_disabled_no_output(self) -> None:
        """tree_print enabled=False 不产生输出"""
        self.reporter.tree_print("hello", enabled=False)

    def test_progress_no_output(self) -> None:
        """progress 不产生输出"""
        self.reporter.progress("loading...")

    def test_wipe_line_no_output(self) -> None:
        """wipe_line 不产生输出"""
        self.reporter.wipe_line()

    def test_satisfies_protocol(self) -> None:
        """SilentReporter 满足 ProgressReporter 协议"""
        reporter: ProgressReporter = SilentReporter()
        assert reporter is not None


class TestConsoleReporter:
    """ConsoleReporter — 委托给 utils.display 的默认实现"""

    def setup_method(self) -> None:
        self.reporter = ConsoleReporter()

    def test_print_outputs_text(self, capsys: object) -> None:
        """print 输出文本"""
        from zhs.utils.display import msg_done

        self.reporter.print(msg_done("完成"))
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "完成" in captured.out

    def test_print_empty(self, capsys: object) -> None:
        """print() 输出空行"""
        self.reporter.print()
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert captured.out == "\n"

    def test_tree_print_outputs_text(self, capsys: object) -> None:
        """tree_print 输出带缩进的文本"""
        self.reporter.tree_print("hello", depth=1)
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "hello" in captured.out

    def test_tree_print_disabled_no_output(self, capsys: object) -> None:
        """tree_print enabled=False 不输出"""
        self.reporter.tree_print("hello", enabled=False)
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert captured.out == ""

    def test_progress_outputs_line(self, capsys: object) -> None:
        """progress 输出行（无换行）"""
        self.reporter.progress("loading...")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "loading..." in captured.out

    @patch("zhs.reporter._wipe_line")
    def test_wipe_line_delegates(self, mock_wipe: object) -> None:
        """wipe_line 委托给 utils.display.wipe_line"""
        self.reporter.wipe_line()
        mock_wipe.assert_called_once()  # type: ignore[attr-defined]

    def test_satisfies_protocol(self) -> None:
        """ConsoleReporter 满足 ProgressReporter 协议"""
        reporter: ProgressReporter = ConsoleReporter()
        assert reporter is not None


class TestProtocolConformance:
    """协议一致性测试"""

    def test_silent_is_progress_reporter(self) -> None:
        """SilentReporter 可赋值给 ProgressReporter"""
        r: ProgressReporter = SilentReporter()
        assert hasattr(r, "print")
        assert hasattr(r, "tree_print")
        assert hasattr(r, "progress")
        assert hasattr(r, "wipe_line")

    def test_console_is_progress_reporter(self) -> None:
        """ConsoleReporter 可赋值给 ProgressReporter"""
        r: ProgressReporter = ConsoleReporter()
        assert hasattr(r, "print")
        assert hasattr(r, "tree_print")
        assert hasattr(r, "progress")
        assert hasattr(r, "wipe_line")

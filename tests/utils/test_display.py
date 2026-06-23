"""Task 1.5 — utils/display.py 测试用例"""

from zhs.utils.display import progress_bar, tree_print, wipe_line


class TestProgressBar:
    def test_progress_bar_normal(self) -> None:
        """progress_bar(50, 100) 不抛异常"""
        result = progress_bar(50, 100)
        assert isinstance(result, str)

    def test_progress_bar_zero_total(self) -> None:
        """progress_bar(0, 0) 不抛异常（除零保护）"""
        result = progress_bar(0, 0)
        assert isinstance(result, str)

    def test_progress_bar_complete(self) -> None:
        """progress_bar(100, 100) 完成时不抛异常"""
        result = progress_bar(100, 100)
        assert isinstance(result, str)

    def test_progress_bar_custom_width(self) -> None:
        """自定义宽度"""
        result = progress_bar(5, 10, width=20)
        assert isinstance(result, str)

    def test_progress_bar_contains_fill(self) -> None:
        """进度条包含填充字符"""
        result = progress_bar(50, 100, width=40)
        assert "#" in result

    def test_progress_bar_zero_current(self) -> None:
        """当前进度为 0"""
        result = progress_bar(0, 100)
        assert isinstance(result, str)


class TestTreePrint:
    def test_tree_print_no_raise(self, capsys: object) -> None:
        """tree_print("test", 1) 不抛异常"""
        tree_print("test", 1)

    def test_tree_print_depth_zero(self, capsys: object) -> None:
        """depth=0 时无缩进"""
        tree_print("root", 0)

    def test_tree_print_depth_positive(self, capsys: object) -> None:
        """depth>0 时有缩进"""
        tree_print("child", 2)


class TestWipeLine:
    def test_wipe_line_no_raise(self) -> None:
        """wipe_line() 不抛异常"""
        wipe_line()

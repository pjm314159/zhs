"""进度报告器 — 解耦业务层与显示层

业务类通过 ProgressReporter 协议输出进度，不直接调用 print/tree_print。
- ConsoleReporter: 默认实现，委托给 zhs.utils.display
- SilentReporter: 空操作实现，用于测试

格式化函数（msg_done / msg_error / progress_bar / styled / course_tag）仍由
zhs.utils.display 提供，业务类可导入用于构建字符串，仅最终输出通过 reporter。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from zhs.utils.display import tree_print as _tree_print
from zhs.utils.display import wipe_line as _wipe_line


@runtime_checkable
class ProgressReporter(Protocol):
    """进度报告器协议 — 业务类通过此协议输出，不直接调用 print"""

    def print(self, text: str = "") -> None:
        """普通输出（默认换行）"""
        ...

    def tree_print(self, text: str, depth: int = 0, enabled: bool = True) -> None:
        """树形缩进输出"""
        ...

    def progress(self, line: str) -> None:
        """原地刷新进度行（\\r 前缀，不换行）"""
        ...

    def wipe_line(self) -> None:
        """清除当前终端行"""
        ...


class ConsoleReporter:
    """默认报告器 — 委托给 zhs.utils.display 的现有函数"""

    def print(self, text: str = "") -> None:
        print(text)

    def tree_print(self, text: str, depth: int = 0, enabled: bool = True) -> None:
        _tree_print(text, depth=depth, enabled=enabled)

    def progress(self, line: str) -> None:
        print(f"\r{line}", end="", flush=True)

    def wipe_line(self) -> None:
        _wipe_line()


class SilentReporter:
    """静默报告器 — 所有方法均为空操作，用于测试"""

    def print(self, text: str = "") -> None:
        pass

    def tree_print(self, text: str, depth: int = 0, enabled: bool = True) -> None:
        pass

    def progress(self, line: str) -> None:
        pass

    def wipe_line(self) -> None:
        pass


__all__ = [
    "ConsoleReporter",
    "ProgressReporter",
    "SilentReporter",
]

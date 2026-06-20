"""显示工具模块：进度条、树形打印、终端清行、二维码显示

ANSI 颜色定义：
  - 课程类型标签: 知到=青色, Hike=黄色, AI=品红
  - 状态: 跳过=暗灰, 完成=绿色, 错误=红色, 警告=黄色
  - 进度条: 填充=青色, 百分比=绿色
"""

import os

from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# ANSI 颜色辅助
# ---------------------------------------------------------------------------


class _C:
    """ANSI 颜色常量"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # 前景色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # 亮色
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_MAGENTA = "\033[95m"


def _supports_color() -> bool:
    """检测终端是否支持 ANSI 颜色"""
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            return bool(mode.value & 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            return False
    return hasattr(os, "isatty") and os.isatty(1)


_COLOR = _supports_color()


def styled(text: str, *styles: str) -> str:
    """应用 ANSI 样式到文本，自动检测颜色支持"""
    if not _COLOR:
        return text
    return "".join(styles) + text + _C.RESET


# ---------------------------------------------------------------------------
# 课程类型标签
# ---------------------------------------------------------------------------


def course_tag(course_type: str) -> str:
    """生成带颜色的课程类型标签，如 [知到] [Hike] [AI]"""
    if course_type == "zhidao":
        return styled("[知到]", _C.BOLD, _C.BRIGHT_CYAN)
    elif course_type == "hike":
        return styled("[Hike]", _C.BOLD, _C.BRIGHT_YELLOW)
    elif course_type == "ai":
        return styled("[AI]", _C.BOLD, _C.BRIGHT_MAGENTA)
    return styled(f"[{course_type}]", _C.BOLD)


# ---------------------------------------------------------------------------
# 进度条
# ---------------------------------------------------------------------------


def progress_bar(current: int, total: int, width: int = 40) -> str:
    """生成带颜色的进度条字符串，total 为 0 时安全返回"""
    if total == 0:
        bar = " " * width
        return styled(f"[{bar}] 0%", _C.DIM)
    percent = current / total
    filled = int(width * percent)
    bar_fill = styled("#" * filled, _C.CYAN)
    bar_empty = styled(" " * (width - filled), _C.DIM)
    pct = styled(f"{int(percent * 100)}%", _C.GREEN if percent >= 1.0 else _C.WHITE)
    return f"[{bar_fill}{bar_empty}] {pct}"


# ---------------------------------------------------------------------------
# 树形打印
# ---------------------------------------------------------------------------


def tree_print(text: str, depth: int = 0, enabled: bool = True) -> None:
    """带缩进前缀的树形打印，depth 控制缩进层级，enabled=False 时不输出"""
    if not enabled:
        return
    prefix = styled("  |", _C.DIM) * depth
    connector = styled("__", _C.DIM) if depth > 0 else ""
    print(f"{prefix}{connector}{text}")


# ---------------------------------------------------------------------------
# 状态消息快捷函数
# ---------------------------------------------------------------------------


def msg_skip(text: str) -> str:
    """跳过消息（暗灰色）"""
    return styled(text, _C.DIM)


def msg_done(text: str) -> str:
    """完成消息（绿色）"""
    return styled(text, _C.GREEN)


def msg_error(text: str) -> str:
    """错误消息（红色）"""
    return styled(text, _C.RED)


def msg_warn(text: str) -> str:
    """警告消息（黄色）"""
    return styled(text, _C.YELLOW)


def msg_info(text: str) -> str:
    """信息消息（青色）"""
    return styled(text, _C.CYAN)


# ---------------------------------------------------------------------------
# 终端工具
# ---------------------------------------------------------------------------


def wipe_line() -> None:
    """清除当前终端行"""
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80
    print("\r" + " " * width, end="\r", flush=True)


def show_qrcode_img(img_bytes: bytes) -> None:
    """从 PNG bytes 直接显示二维码图片到终端"""
    import io

    img = Image.open(io.BytesIO(img_bytes))
    _display_qr_terminal(img)
    print("请扫描二维码")


def _display_qr_terminal(img: Image.Image) -> None:
    """在终端中以 ANSI 颜色块显示二维码图片"""
    qr = img.resize((39, 39), Image.Resampling.NEAREST)
    qr = ImageOps.grayscale(qr)
    white = "\033[0;37;47m  "
    black = "\033[0;37;40m  "
    new_line = "\033[0m\n"
    col, row = qr.size
    border = 1
    qr_str = white * (col + border * 2) + new_line
    for i in range(row):
        qr_str += white * border
        for j in range(col):
            pixel = qr.getpixel((j, i))
            qr_str += white if isinstance(pixel, int) and pixel > 128 else black
        qr_str += white * border + new_line
    qr_str += white * (col + border * 2) + new_line
    print(qr_str)

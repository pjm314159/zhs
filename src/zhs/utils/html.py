"""HTML 文本提取工具

使用 BeautifulSoup 从 HTML 中提取纯文本，处理标签剥离、实体转义和空白合并。
"""

import re

from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    """从 HTML 中提取纯文本

    - 用 BeautifulSoup 的 get_text(separator=" ") 提取文本，多级标签用空格分隔
    - &nbsp; 等实体自动转义（&nbsp; → \\xa0 → 空格）
    - 合并连续空白为单个空格
    - 去除前导/尾随空白

    Args:
        html: HTML 格式的字符串

    Returns:
        纯文本字符串
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    # 合并连续空白（含 \\xa0 不间断空格）为单个空格
    text = re.sub(r"[\s\xa0]+", " ", text)
    return text.strip()


__all__ = ["extract_text"]

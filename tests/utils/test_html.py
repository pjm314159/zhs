"""utils/html.py 单元测试

覆盖 extract_text 函数：HTML 标签剥离 + 实体转义 + 空白合并。
"""

from zhs.utils.html import extract_text


class TestExtractText:
    """extract_text"""

    def test_plain_text(self) -> None:
        """纯文本原样返回"""
        assert extract_text("hello world") == "hello world"

    def test_simple_tag(self) -> None:
        """简单标签剥离"""
        assert extract_text("<p>hello</p>") == "hello"

    def test_nested_tags(self) -> None:
        """多级嵌套标签用空格分隔"""
        assert extract_text("<p><span>hello</span> world</p>") == "hello world"

    def test_nbsp_entity(self) -> None:
        """&nbsp; 实体转为空格并合并"""
        assert extract_text("&nbsp;hello") == "hello"

    def test_multiple_nbsp(self) -> None:
        """连续 &nbsp; 合并为单个空格"""
        assert extract_text("a&nbsp;&nbsp;b") == "a b"

    def test_html_entities(self) -> None:
        """HTML 实体正确转义"""
        assert extract_text("&amp;&lt;&gt;") == "&<>"

    def test_mixed_tags_and_entities(self) -> None:
        """混合标签和实体"""
        assert extract_text("<p>&nbsp;题目&nbsp;</p>") == "题目"

    def test_empty_string(self) -> None:
        """空字符串"""
        assert extract_text("") == ""

    def test_only_tags(self) -> None:
        """只有标签"""
        assert extract_text("<br/>") == ""

    def test_br_tag_as_separator(self) -> None:
        """<br> 标签作为分隔符"""
        assert extract_text("<p>line1<br>line2</p>") == "line1 line2"

    def test_real_world_question(self) -> None:
        """真实题目文本（含 &nbsp; 和多级标签）"""
        html = "2026年大学毕业生人数达到（&nbsp; &nbsp; ），再创历史新高？"
        assert extract_text(html) == "2026年大学毕业生人数达到（ ），再创历史新高？"

    def test_real_world_option(self) -> None:
        """真实选项文本（含 span 标签）"""
        html = '<p><span style="text-wrap-mode: wrap;">农民工</span></p>'
        assert extract_text(html) == "农民工"

    def test_whitespace_collapse(self) -> None:
        """连续空白合并为单个空格"""
        assert extract_text("a   b\n\n\tc") == "a b c"

    def test_strips_leading_trailing_whitespace(self) -> None:
        """去除前导和尾随空白"""
        assert extract_text("  <p> hello </p>  ") == "hello"

"""cli/course_type.py 单元测试

覆盖 detect_course_type / validate_course_type / parse_ai_course_str / parse_homework_url。
"""

import pytest

from zhs.cli.course_type import (
    VALID_COURSE_TYPES,
    detect_course_type,
    parse_ai_course_str,
    parse_homework_url,
    validate_course_type,
)


class TestValidCourseTypes:
    """VALID_COURSE_TYPES 常量"""

    def test_contains_all_expected_types(self) -> None:
        """包含 zhidao/hike/ai/auto"""
        assert set(VALID_COURSE_TYPES) == {"zhidao", "hike", "ai", "auto"}


class TestDetectCourseType:
    """detect_course_type"""

    def test_letters_route_zhidao(self) -> None:
        """含字母 → zhidao"""
        assert detect_course_type("ABC123") == "zhidao"

    def test_pure_digits_route_hike(self) -> None:
        """纯数字 → hike"""
        assert detect_course_type("12345") == "hike"

    def test_explicit_type_overrides_detection(self) -> None:
        """显式 type 优先于自动检测"""
        assert detect_course_type("ABC123", "hike") == "hike"
        assert detect_course_type("12345", "zhidao") == "zhidao"
        assert detect_course_type("12345", "ai") == "ai"

    def test_empty_string_routes_hike(self) -> None:
        """空字符串（无字母）→ hike"""
        assert detect_course_type("") == "hike"

    def test_mixed_case_letters_route_zhidao(self) -> None:
        """大小写混合字母 → zhidao"""
        assert detect_course_type("AbC123") == "zhidao"


class TestValidateCourseType:
    """validate_course_type"""

    def test_valid_types_pass_through(self) -> None:
        """有效类型原样返回"""
        assert validate_course_type("zhidao") == "zhidao"
        assert validate_course_type("hike") == "hike"
        assert validate_course_type("ai") == "ai"
        assert validate_course_type("auto") == "auto"

    def test_none_passes_through(self) -> None:
        """None 原样返回"""
        assert validate_course_type(None) is None

    def test_invalid_type_returns_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """无效类型返回 None 并打印错误"""
        result = validate_course_type("asdf")
        assert result is None
        captured = capsys.readouterr()
        assert "不支持的课程类型" in captured.out
        assert "asdf" in captured.out

    def test_invalid_type_lists_valid_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        """错误信息中列出所有可选值"""
        validate_course_type("foo")
        captured = capsys.readouterr()
        for t in VALID_COURSE_TYPES:
            assert t in captured.out


class TestParseAiCourseStr:
    """parse_ai_course_str"""

    def test_valid_format(self) -> None:
        """合法的 courseId:classId 返回 (int, int)"""
        assert parse_ai_course_str("100:200") == (100, 200)

    def test_valid_format_large_numbers(self) -> None:
        """大整数 ID"""
        assert parse_ai_course_str("7123456789012345678:523456") == (7123456789012345678, 523456)

    def test_missing_colon_returns_none(self) -> None:
        """缺少冒号返回 None"""
        assert parse_ai_course_str("100200") is None

    def test_too_many_colons_returns_none(self) -> None:
        """多个冒号返回 None"""
        assert parse_ai_course_str("100:200:300") is None

    def test_non_integer_parts_return_none(self) -> None:
        """非整数部分返回 None"""
        assert parse_ai_course_str("abc:200") is None
        assert parse_ai_course_str("100:xyz") is None

    def test_empty_string_returns_none(self) -> None:
        """空字符串返回 None"""
        assert parse_ai_course_str("") is None

    def test_negative_numbers_accepted(self) -> None:
        """负数被 int() 接受（语法合法）"""
        # int("-100") 是合法的，因此 parse_ai_course_str 接受负数
        assert parse_ai_course_str("-100:200") == (-100, 200)


class TestParseHomeworkUrl:
    """parse_homework_url"""

    def test_valid_url(self) -> None:
        """合法 URL 解析"""
        url = "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/100/200/300/400/500/0"
        result = parse_homework_url(url)
        assert result == {
            "recruit_id": "100",
            "stu_exam_id": "200",
            "exam_id": "300",
            "course_id": "400",
            "school_id": "500",
        }

    def test_url_with_trailing_slash(self) -> None:
        """URL 末尾带斜杠"""
        url = "https://example.com/dohomework/100/200/300/400/500/"
        result = parse_homework_url(url)
        assert result["recruit_id"] == "100"
        assert result["school_id"] == "500"

    def test_url_without_dohomework_raises(self) -> None:
        """URL 不含 dohomework/ 路径 → ValueError"""
        url = "https://example.com/other/100/200"
        with pytest.raises(ValueError, match="无法解析作业 URL"):
            parse_homework_url(url)

    def test_url_with_too_few_segments_raises(self) -> None:
        """URL 参数不足 5 个 → ValueError"""
        url = "https://example.com/dohomework/100/200/300"
        with pytest.raises(ValueError, match="无法解析作业 URL"):
            parse_homework_url(url)

    def test_field_order_stu_exam_before_exam(self) -> None:
        """URL 中 stuExamId 在 examId 之前（与 HomeworkItem 字段名相反）"""
        url = "https://example.com/dohomework/R1/STU1/EXAM1/C1/S1/0"
        result = parse_homework_url(url)
        # 第 2 个参数是 stu_exam_id，第 3 个是 exam_id
        assert result["stu_exam_id"] == "STU1"
        assert result["exam_id"] == "EXAM1"

    def test_url_with_query_string(self) -> None:
        """URL 带 query string 仍可解析"""
        url = "https://example.com/dohomework/100/200/300/400/500/0?foo=bar"
        result = parse_homework_url(url)
        assert result["recruit_id"] == "100"
        assert result["school_id"] == "500"

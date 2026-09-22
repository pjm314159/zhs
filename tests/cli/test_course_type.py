"""cli/course_type.py 单元测试

覆盖 detect_course_type / validate_course_type / parse_ai_course_str / parse_homework_url。
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.course_type import (
    VALID_COURSE_TYPES,
    detect_course,
    detect_course_type,
    parse_ai_course_str,
    parse_homework_url,
    validate_course_type,
)


@pytest.fixture
def mock_zhidao_session() -> Iterator[MagicMock]:
    """session 中 zhidao 课程列表能匹配到 courseId=1000008156"""
    mock_course = MagicMock()
    mock_course.course_id = 1000008156
    mock_mgr = MagicMock()
    mock_mgr.find_course.return_value = mock_course
    with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
        yield mock_mgr


@pytest.fixture
def mock_zhidao_session_empty() -> Iterator[MagicMock]:
    """session 中 zhidao 课程列表无匹配项"""
    mock_mgr = MagicMock()
    mock_mgr.find_course.return_value = None
    with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
        yield mock_mgr


class TestValidCourseTypes:
    """VALID_COURSE_TYPES 常量"""

    def test_contains_all_expected_types(self) -> None:
        """包含 zhidao/hike/ai/auto"""
        assert set(VALID_COURSE_TYPES) == {"zhidao", "hike", "ai", "auto"}


class TestDetectCourseType:
    """detect_course_type"""

    def test_letters_rejected_with_url_hint(self) -> None:
        """含字母的 recruitAndCourseId 传给 -c → ValueError 并提示改用 --url"""
        with pytest.raises(ValueError, match="recruitAndCourseId 请通过 --url 传入"):
            detect_course_type("ABC123")

    def test_pure_digits_route_hike(self) -> None:
        """纯数字（无 session）→ hike"""
        assert detect_course_type("12345") == "hike"

    def test_explicit_type_overrides_detection(self) -> None:
        """显式 type 优先于自动检测"""
        assert detect_course_type("ABC123", "hike") == "hike"
        assert detect_course_type("12345", "zhidao") == "zhidao"
        assert detect_course_type("12345", "ai") == "ai"

    def test_auto_type_falls_back_to_detection(self) -> None:
        """--type auto 视为自动检测"""
        assert detect_course_type("12345", "auto") == "hike"

    def test_empty_string_raises(self) -> None:
        """空字符串 → ValueError"""
        with pytest.raises(ValueError, match="无法识别的课程 ID"):
            detect_course_type("")

    def test_mixed_case_letters_rejected(self) -> None:
        """大小写混合字母 → ValueError"""
        with pytest.raises(ValueError, match="recruitAndCourseId 请通过 --url 传入"):
            detect_course_type("AbC123")

    def test_colon_routes_ai(self) -> None:
        """含冒号 → ai（courseId:classId）"""
        assert detect_course_type("100:200") == "ai"

    def test_colon_overrides_letters(self) -> None:
        """含冒号优先于字母判断 → ai"""
        assert detect_course_type("ABC:123") == "ai"

    def test_pure_digits_with_session_zhidao_match(self, mock_zhidao_session: MagicMock) -> None:
        """纯数字 + session 且匹配 zhidao 列表 → zhidao"""
        assert detect_course_type("1000008156", session=mock_zhidao_session) == "zhidao"

    def test_pure_digits_with_session_no_match(self, mock_zhidao_session_empty: MagicMock) -> None:
        """纯数字 + session 但不匹配 zhidao 列表 → hike"""
        assert detect_course_type("9999999999", session=mock_zhidao_session_empty) == "hike"

    def test_pure_digits_no_session_routes_hike(self) -> None:
        """纯数字 + 无 session → hike（不查列表）"""
        assert detect_course_type("12345") == "hike"

    def test_numeric_course_id_matched_routes_zhidao(self) -> None:
        """find_course 命中 → zhidao"""
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = MagicMock()
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            assert detect_course_type("1000008156", session=session) == "zhidao"

        mock_mgr.find_course.assert_called_once_with(1000008156)

    def test_zero_course_id_raises(self) -> None:
        """courseId=0 → ValueError（0 不是有效课程 ID）"""
        with pytest.raises(ValueError, match="必须为正整数"):
            detect_course_type("0")

    def test_zhidao_list_fetch_failure_raises(self) -> None:
        """知到列表拉取失败 → ValueError 提示用 --type，不静默回退 hike"""
        mock_mgr = MagicMock()
        mock_mgr.find_course.side_effect = RuntimeError("网络错误")
        session = MagicMock()

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr),
            pytest.raises(ValueError, match="请用 --type 显式指定"),
        ):
            detect_course_type("1000008156", session=session)


class TestDetectCourse:
    """detect_course（一次查询同时返回类型与匹配课程）"""

    def test_returns_matched_course(self) -> None:
        """命中知到 → 返回 (zhidao, 课程对象)"""
        mock_course = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = mock_course
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            detected, course = detect_course("1000008156", session=session)

        assert detected == "zhidao"
        assert course is mock_course
        mock_mgr.find_course.assert_called_once_with(1000008156)

    def test_hike_returns_none_course(self) -> None:
        """无 session → hike，且不带课程对象"""
        detected, course = detect_course("12345")
        assert detected == "hike"
        assert course is None

    def test_ai_returns_none_course(self) -> None:
        """含冒号 → ai，且不带课程对象"""
        detected, course = detect_course("100:200")
        assert detected == "ai"
        assert course is None

    def test_explicit_zhidao_missing_course_raises(self) -> None:
        """显式 zhidao 但列表无匹配 → ValueError"""
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = None
        session = MagicMock()

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr),
            pytest.raises(ValueError, match="未找到 courseId=1000008156 的知到课程"),
        ):
            detect_course("1000008156", "zhidao", session)


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

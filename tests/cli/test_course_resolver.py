"""cli/course_resolver.py 单元测试

覆盖 resolve_course_id 统一解析 -c 参数。
"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.course_resolver import ResolvedCourse, resolve_course_id


class TestResolveCourseId:
    """resolve_course_id"""

    def test_hike_explicit_type(self) -> None:
        """显式 hike → 直接返回 course_id"""
        result = resolve_course_id("12345", "hike")
        assert result.type == "hike"
        assert result.course_id == 12345
        assert result.class_id is None
        assert result.rac_id is None

    def test_ai_explicit_type(self) -> None:
        """显式 ai + courseId:classId → 解析两个 ID"""
        result = resolve_course_id("100:200", "ai")
        assert result.type == "ai"
        assert result.course_id == 100
        assert result.class_id == 200

    def test_ai_auto_detected_by_colon(self) -> None:
        """含冒号自动检测为 ai"""
        result = resolve_course_id("300:400")
        assert result.type == "ai"
        assert result.course_id == 300
        assert result.class_id == 400

    def test_zhidao_explicit_type_finds_rac_id(self) -> None:
        """显式 zhidao + session → 反查 recruitAndCourseId"""
        mock_course = MagicMock()
        mock_course.course_id = 1000008156
        mock_course.secret = "encrypted_rac_id"
        mock_mgr = MagicMock()
        mock_mgr.get_course_list.return_value = [mock_course]
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", "zhidao", session)

        assert result.type == "zhidao"
        assert result.course_id == 1000008156
        assert result.rac_id == "encrypted_rac_id"

    def test_zhidao_not_found_raises(self) -> None:
        """知到 courseId 不在列表中 → ValueError"""
        mock_mgr = MagicMock()
        mock_mgr.get_course_list.return_value = []
        session = MagicMock()

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr),
            pytest.raises(ValueError, match="未找到 courseId=99999 的知到课程"),
        ):
            resolve_course_id("99999", "zhidao", session)

    def test_zhidao_without_session_raises(self) -> None:
        """知到课程但无 session → ValueError"""
        with pytest.raises(ValueError, match="知到课程需 session"):
            resolve_course_id("1000008156", "zhidao")

    def test_auto_detect_zhidao_with_session(self) -> None:
        """自动检测 + session → 纯数字匹配 zhidao 列表"""
        mock_course = MagicMock()
        mock_course.course_id = 1000008156
        mock_course.secret = "rac_secret"
        mock_mgr = MagicMock()
        mock_mgr.get_course_list.return_value = [mock_course]
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", session=session)

        assert result.type == "zhidao"
        assert result.rac_id == "rac_secret"

    def test_auto_detect_hike_no_session(self) -> None:
        """自动检测 + 无 session → hike"""
        result = resolve_course_id("12345")
        assert result.type == "hike"
        assert result.course_id == 12345

    def test_auto_detect_hike_not_in_zhidao_list(self) -> None:
        """自动检测 + session 但不匹配 zhidao → hike"""
        mock_mgr = MagicMock()
        mock_mgr.get_course_list.return_value = []
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("99999", session=session)

        assert result.type == "hike"
        assert result.course_id == 99999


class TestResolvedCourse:
    """ResolvedCourse 数据类"""

    def test_defaults(self) -> None:
        """默认值"""
        r = ResolvedCourse(type="hike", course_id=123)
        assert r.class_id is None
        assert r.rac_id is None

    def test_ai_fields(self) -> None:
        """AI 课程字段"""
        r = ResolvedCourse(type="ai", course_id=100, class_id=200)
        assert r.class_id == 200
        assert r.rac_id is None

    def test_zhidao_fields(self) -> None:
        """知到课程字段"""
        r = ResolvedCourse(type="zhidao", course_id=100, rac_id="secret")
        assert r.rac_id == "secret"
        assert r.class_id is None

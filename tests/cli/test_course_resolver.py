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
        mock_mgr.find_course.return_value = mock_course
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", "zhidao", session)

        assert result.type == "zhidao"
        assert result.course_id == 1000008156
        assert result.rac_id == "encrypted_rac_id"
        # 只查一次课程列表（不再二次反查 rac_id）
        mock_mgr.find_course.assert_called_once_with(1000008156)

    def test_zhidao_not_found_raises(self) -> None:
        """知到 courseId 不在列表中 → ValueError"""
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = None
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

    def test_zhidao_non_digit_rejected(self) -> None:
        """显式 zhidao + 非数字（recruitAndCourseId）→ ValueError 提示改用 --url"""
        session = MagicMock()
        with pytest.raises(ValueError, match="recruitAndCourseId 请通过 --url 传入"):
            resolve_course_id("ABC123", "zhidao", session)

    def test_hike_non_digit_rejected(self) -> None:
        """显式 hike + 非数字 → ValueError"""
        with pytest.raises(ValueError, match="必须为纯数字 courseId"):
            resolve_course_id("ABC123", "hike")

    def test_zhidao_course_info_fallback_finds_rac_id(self) -> None:
        """顶层 courseId 为 0 时，用 courseInfo.courseId 反查 rac_id"""
        mock_course = MagicMock()
        mock_course.course_id = 0
        mock_course.course_info.course_id = 1000008156
        mock_course.secret = "rac_secret"
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = mock_course
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", "zhidao", session)

        assert result.type == "zhidao"
        assert result.rac_id == "rac_secret"

    def test_non_positive_course_id_rejected(self) -> None:
        """courseId=0 → ValueError"""
        with pytest.raises(ValueError, match="必须为正整数"):
            resolve_course_id("0", "hike")

    def test_zhidao_returns_recruit_id(self) -> None:
        """知到解析同时返回 recruit_id（作业/考试需要）"""
        mock_course = MagicMock()
        mock_course.secret = "rac_secret"
        mock_course.recruit_id = 789
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = mock_course
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", "zhidao", session)

        assert result.recruit_id == 789

    def test_zhidao_missing_recruit_id_is_none(self) -> None:
        """课程无 recruitId 时返回 None（调用方需据此跳过作业/考试）"""
        mock_course = MagicMock()
        mock_course.secret = "rac_secret"
        mock_course.recruit_id = None
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = mock_course
        session = MagicMock()

        with patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=mock_mgr):
            result = resolve_course_id("1000008156", "zhidao", session)

        assert result.recruit_id is None
        assert result.rac_id == "rac_secret"

    def test_auto_detect_zhidao_with_session(self) -> None:
        """自动检测 + session → 纯数字匹配 zhidao 列表"""
        mock_course = MagicMock()
        mock_course.course_id = 1000008156
        mock_course.secret = "rac_secret"
        mock_mgr = MagicMock()
        mock_mgr.find_course.return_value = mock_course
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
        mock_mgr.find_course.return_value = None
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
        assert r.recruit_id is None

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

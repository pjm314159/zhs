"""cli/services/fetch_service.py 单元测试

覆盖 fetch_course_list。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.services.fetch_service import fetch_course_list


class TestFetchCourseList:
    """fetch_course_list"""

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_fetch_all_writes_execution_json(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """fetch_type=all 写入 execution.json"""
        # 准备 mock 数据
        mock_zhidao_course = MagicMock()
        mock_zhidao_course.course_name = "知到课程1"
        mock_zhidao_course.secret = "ABC123"
        mock_zhidao_cls.return_value.get_course_list.return_value = [mock_zhidao_course]

        mock_hike_course = MagicMock()
        mock_hike_course.course_name = "Hike课程1"
        mock_hike_course.course_id = 12345
        mock_hike_cls.return_value.get_course_list.return_value = [mock_hike_course]

        mock_ai_cls.return_value.get_ai_course_list.return_value = [
            {"courseName": "AI课程1", "courseId": 100, "classId": 200}
        ]

        session = MagicMock()

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            fetch_course_list(session, fetch_type="all")

        exec_path = tmp_path / "execution.json"
        assert exec_path.exists()
        data = json.loads(exec_path.read_text(encoding="utf-8"))
        assert "zhidao" in data
        assert "hike" in data
        assert "ai" in data
        assert len(data["zhidao"]) == 1
        assert data["zhidao"][0]["name"] == "知到课程1"
        assert data["zhidao"][0]["id"] == "ABC123"
        assert len(data["hike"]) == 1
        assert data["hike"][0]["id"] == "12345"
        assert len(data["ai"]) == 1
        assert data["ai"][0]["courseId"] == 100

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_fetch_all_prints_course_counts(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fetch_type=all 打印课程数量"""
        mock_zhidao_cls.return_value.get_course_list.return_value = []
        mock_hike_cls.return_value.get_course_list.return_value = []
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        session = MagicMock()

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            fetch_course_list(session, fetch_type="all")

        captured = capsys.readouterr()
        assert "0 门课程" in captured.out

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_fetch_non_course_type_skips_list_fetch(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """fetch_type 非 all/course 时不调用课程列表 API"""
        session = MagicMock()

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            fetch_course_list(session, fetch_type="homework")

        mock_zhidao_cls.assert_not_called()
        mock_hike_cls.assert_not_called()
        mock_ai_cls.assert_not_called()

        # 但仍写入空的 execution.json
        exec_path = tmp_path / "execution.json"
        assert exec_path.exists()
        data = json.loads(exec_path.read_text(encoding="utf-8"))
        assert data == {"zhidao": [], "hike": [], "ai": []}

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_fetch_course_type_fetches_lists(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """fetch_type=course 等价于 all，调用所有列表 API"""
        mock_zhidao_cls.return_value.get_course_list.return_value = []
        mock_hike_cls.return_value.get_course_list.return_value = []
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        session = MagicMock()

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            fetch_course_list(session, fetch_type="course")

        mock_zhidao_cls.return_value.get_course_list.assert_called_once()
        mock_hike_cls.return_value.get_course_list.assert_called_once()
        mock_ai_cls.return_value.get_ai_course_list.assert_called_once()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.hike.course.HikeCourseManager")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_execution_json_indent_4(
        self,
        mock_zhidao_cls: MagicMock,
        mock_hike_cls: MagicMock,
        mock_ai_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """execution.json 使用 indent=4 格式化"""
        mock_zhidao_cls.return_value.get_course_list.return_value = []
        mock_hike_cls.return_value.get_course_list.return_value = []
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        session = MagicMock()

        with patch("zhs.utils.path.get_data_dir", return_value=tmp_path):
            fetch_course_list(session, fetch_type="all")

        exec_path = tmp_path / "execution.json"
        content = exec_path.read_text(encoding="utf-8")
        # indent=4 应包含 4 个空格的缩进
        assert "    " in content

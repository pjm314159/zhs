"""Task 6.2 — ai/ppt.py TDD"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from zhs.ai.ppt import PptConverter


class TestPptConverterInit:
    """PptConverter 初始化"""

    def test_default_params_no_api_key(self) -> None:
        """无 api_key 时使用本地模式"""
        converter = PptConverter()
        assert converter._use_api is False
        assert converter._client is None
        assert converter._should_cleanup_local is True
        assert converter._delete_after_convert is True

    def test_api_key_mode(self) -> None:
        """有 api_key 时使用 MoonShot API 模式"""
        converter = PptConverter(api_key="test-key")
        assert converter._use_api is True
        assert converter._client is not None
        assert converter._client.api_key == "test-key"
        assert str(converter._client.base_url).startswith("https://api.moonshot.cn/v1")

    def test_custom_params(self) -> None:
        """自定义参数"""
        converter = PptConverter(
            api_key="key",
            base_url="https://custom.api.com/v1",
            cleanup_local=False,
            delete_after_convert=False,
        )
        assert str(converter._client.base_url).startswith("https://custom.api.com/v1")
        assert converter._should_cleanup_local is False
        assert converter._delete_after_convert is False


class TestCleanupLocal:
    """本地文件清理"""

    def test_cleanup_local_deletes_file(self, tmp_path: Path) -> None:
        """cleanup_local=True 删除临时文件"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=True)
        converter._cleanup_local(test_file)
        assert not test_file.exists()

    def test_cleanup_local_disabled(self, tmp_path: Path) -> None:
        """cleanup_local=False 时 convert 不调用 _cleanup_local"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=False)
        with (
            patch.object(converter, "_download", return_value=test_file),
            patch.object(converter, "_upload", return_value="file-abc"),
            patch.object(converter, "_extract", return_value="内容"),
            patch.object(converter, "_cleanup_local") as mock_cleanup,
        ):
            converter.convert("https://example.com/test.pptx")
            mock_cleanup.assert_not_called()

    def test_cleanup_nonexistent_file_no_error(self, tmp_path: Path) -> None:
        """清理不存在的文件不报错"""
        test_file = tmp_path / "nonexistent.pptx"
        converter = PptConverter(api_key="test", cleanup_local=True)
        converter._cleanup_local(test_file)  # 不应抛异常


class TestExtract:
    """文本提取"""

    def test_extract_json_parse_priority(self) -> None:
        """_extract 先尝试 JSON 解析取 content 字段"""
        converter = PptConverter(api_key="test")
        json_text = json.dumps({"content": "提取的内容"})
        with patch.object(converter, "_extract_from_api", return_value=json_text):
            result = converter._extract("file-abc")
        assert result == "提取的内容"

    def test_extract_json_no_content_field(self) -> None:
        """JSON 无 content 字段返回原始文本"""
        converter = PptConverter(api_key="test")
        json_text = json.dumps({"other": "数据"})
        with patch.object(converter, "_extract_from_api", return_value=json_text):
            result = converter._extract("file-abc")
        assert result == json_text

    def test_extract_plain_text_fallback(self) -> None:
        """纯文本兜底"""
        converter = PptConverter(api_key="test")
        plain = "这是纯文本内容"
        with patch.object(converter, "_extract_from_api", return_value=plain):
            result = converter._extract("file-abc")
        assert result == "这是纯文本内容"

    def test_extract_empty_string(self) -> None:
        """空字符串"""
        converter = PptConverter(api_key="test")
        with patch.object(converter, "_extract_from_api", return_value=""):
            result = converter._extract("file-abc")
        assert result == ""


class TestConvert:
    """完整转换流程"""

    @patch("zhs.ai.ppt.PptConverter._cleanup_local")
    @patch("zhs.ai.ppt.PptConverter._delete_remote")
    @patch("zhs.ai.ppt.PptConverter._extract")
    @patch("zhs.ai.ppt.PptConverter._upload")
    @patch("zhs.ai.ppt.PptConverter._download")
    def test_convert_full_flow(
        self,
        mock_download: MagicMock,
        mock_upload: MagicMock,
        mock_extract: MagicMock,
        mock_delete_remote: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """完整流程：download → upload → extract → delete_remote → cleanup_local"""
        mock_download.return_value = Path("/tmp/test.pptx")
        mock_upload.return_value = "file-abc123"
        mock_extract.return_value = "PPT 文本内容"

        converter = PptConverter(api_key="test")
        result = converter.convert("https://example.com/test.pptx")

        assert result == "PPT 文本内容"
        mock_download.assert_called_once_with("https://example.com/test.pptx")
        mock_upload.assert_called_once_with(Path("/tmp/test.pptx"))
        mock_extract.assert_called_once_with("file-abc123")
        mock_delete_remote.assert_called_once_with("file-abc123")
        mock_cleanup.assert_called_once_with(Path("/tmp/test.pptx"))

    @patch("zhs.ai.ppt.PptConverter._cleanup_local")
    @patch("zhs.ai.ppt.PptConverter._delete_remote")
    @patch("zhs.ai.ppt.PptConverter._extract")
    @patch("zhs.ai.ppt.PptConverter._upload")
    @patch("zhs.ai.ppt.PptConverter._download")
    def test_convert_no_delete_remote(
        self,
        mock_download: MagicMock,
        mock_upload: MagicMock,
        mock_extract: MagicMock,
        mock_delete_remote: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """delete_after_convert=False 不删除远程文件"""
        mock_download.return_value = Path("/tmp/test.pptx")
        mock_upload.return_value = "file-abc123"
        mock_extract.return_value = "内容"

        converter = PptConverter(api_key="test", delete_after_convert=False)
        converter.convert("https://example.com/test.pptx")

        mock_delete_remote.assert_not_called()

    @patch("zhs.ai.ppt.PptConverter._cleanup_local")
    @patch("zhs.ai.ppt.PptConverter._extract")
    @patch("zhs.ai.ppt.PptConverter._upload")
    @patch("zhs.ai.ppt.PptConverter._download")
    def test_convert_download_error_returns_empty(
        self,
        mock_download: MagicMock,
        mock_upload: MagicMock,
        mock_extract: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """下载失败返回空字符串"""
        mock_download.side_effect = Exception("Network error")

        converter = PptConverter(api_key="test")
        result = converter.convert("https://example.com/bad.pptx")

        assert result == ""
        mock_upload.assert_not_called()


class TestManageCache:
    """缓存管理"""

    def test_manage_cache_removes_oldest(self) -> None:
        """LRU 策略删除最旧文件"""
        converter = PptConverter(api_key="test", max_cache_files=2)
        converter._file_cache = {
            "old.pptx": {"id": "file-old", "size": 100, "created_at": 1000},
            "mid.pptx": {"id": "file-mid", "size": 200, "created_at": 2000},
            "new.pptx": {"id": "file-new", "size": 300, "created_at": 3000},
        }

        with patch.object(converter, "_delete_remote") as mock_delete:
            converter._manage_cache()
            # 应删除最旧的 old.pptx
            mock_delete.assert_called_once_with("file-old")

    def test_manage_cache_within_limits(self) -> None:
        """缓存未超限不删除"""
        converter = PptConverter(api_key="test", max_cache_files=100)
        converter._file_cache = {
            "a.pptx": {"id": "file-a", "size": 100, "created_at": 1000},
        }

        with patch.object(converter, "_delete_remote") as mock_delete:
            converter._manage_cache()
            mock_delete.assert_not_called()


class TestExtractLocal:
    """python-pptx 本地提取"""

    @staticmethod
    def _create_pptx(path: Path, slides_data: list[list[str]]) -> None:
        """创建测试用 .pptx 文件"""
        from pptx import Presentation
        from pptx.util import Inches

        prs = Presentation()
        for texts in slides_data:
            slide = prs.slides.add_slide(prs.slide_layouts[1])  # 使用标题+内容布局
            for i, text in enumerate(texts):
                if i == 0 and slide.shapes.title:
                    slide.shapes.title.text = text
                elif len(slide.shapes.placeholders) > 1:
                    ph = slide.shapes.placeholders[1]
                    ph.text = text
                else:
                    from pptx.util import Emu

                    txBox = slide.shapes.add_textbox(Emu(0), Emu(0), Inches(5), Inches(1))
                    txBox.text_frame.text = text
        prs.save(str(path))

    def test_extract_local_single_slide(self, tmp_path: Path) -> None:
        """单张幻灯片提取"""
        pptx_path = tmp_path / "test.pptx"
        self._create_pptx(pptx_path, [["标题1", "内容1"]])

        converter = PptConverter()
        result = converter._extract_local(pptx_path)
        assert "标题1" in result
        assert "内容1" in result
        assert "[幻灯片 1]" in result

    def test_extract_local_multiple_slides(self, tmp_path: Path) -> None:
        """多张幻灯片提取"""
        pptx_path = tmp_path / "multi.pptx"
        self._create_pptx(pptx_path, [["标题1", "内容1"], ["标题2", "内容2"]])

        converter = PptConverter()
        result = converter._extract_local(pptx_path)
        assert "[幻灯片 1]" in result
        assert "[幻灯片 2]" in result
        assert "标题1" in result
        assert "标题2" in result

    def test_extract_local_empty_slide_skipped(self, tmp_path: Path) -> None:
        """空幻灯片不出现在结果中"""
        pptx_path = tmp_path / "empty.pptx"
        self._create_pptx(pptx_path, [["有内容"], []])

        converter = PptConverter()
        result = converter._extract_local(pptx_path)
        assert "[幻灯片 1]" in result
        assert "[幻灯片 2]" not in result

    def test_extract_local_table(self, tmp_path: Path) -> None:
        """表格内容提取"""
        from pptx import Presentation
        from pptx.util import Inches

        pptx_path = tmp_path / "table.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # 空白布局
        rows, cols = 2, 2
        table_shape = slide.shapes.add_table(rows, cols, Inches(1), Inches(1), Inches(4), Inches(2))
        table = table_shape.table
        table.cell(0, 0).text = "姓名"
        table.cell(0, 1).text = "分数"
        table.cell(1, 0).text = "张三"
        table.cell(1, 1).text = "95"
        prs.save(str(pptx_path))

        converter = PptConverter()
        result = converter._extract_local(pptx_path)
        assert "姓名" in result
        assert "张三" in result
        assert "95" in result

    def test_convert_local_mode(self, tmp_path: Path) -> None:
        """本地模式完整转换流程（不调用 MoonShot API）"""
        pptx_path = tmp_path / "local.pptx"
        self._create_pptx(pptx_path, [["测试标题", "测试内容"]])

        converter = PptConverter(cleanup_local=False)
        with patch.object(converter, "_download", return_value=pptx_path):
            result = converter.convert("https://example.com/test.pptx")

        assert "测试标题" in result
        assert "测试内容" in result

    def test_convert_local_mode_no_api_calls(self, tmp_path: Path) -> None:
        """本地模式不调用任何 MoonShot API 方法"""
        pptx_path = tmp_path / "no_api.pptx"
        self._create_pptx(pptx_path, [["标题"]])

        converter = PptConverter(cleanup_local=False)
        with (
            patch.object(converter, "_download", return_value=pptx_path),
            patch.object(converter, "_upload") as mock_upload,
            patch.object(converter, "_extract") as mock_extract,
            patch.object(converter, "_delete_remote") as mock_delete,
        ):
            result = converter.convert("https://example.com/test.pptx")

        assert "标题" in result
        mock_upload.assert_not_called()
        mock_extract.assert_not_called()
        mock_delete.assert_not_called()

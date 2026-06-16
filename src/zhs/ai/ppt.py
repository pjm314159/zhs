"""PPT 转文本（本地 python-pptx / MoonShot API）"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from zhs.utils.path import get_data_dir


class PptConverter:
    """PPT 转文本

    优先使用 python-pptx 本地提取（无需 API Key）；
    如需 MoonShot API 提取（支持更多格式），传入 api_key 即可。
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.moonshot.cn/v1",
        max_file_size_mb: int = 100,
        max_cache_files: int = 500,
        max_cache_size_gb: int = 8,
        delete_after_convert: bool = True,
        cleanup_local: bool = True,
    ) -> None:
        self._use_api = bool(api_key)
        self._client: Any = None
        if self._use_api:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._max_file_size = max_file_size_mb * 1024 * 1024
        self._max_cache_files = max_cache_files
        self._max_cache_size = max_cache_size_gb * 1024 * 1024 * 1024
        self._delete_after_convert = delete_after_convert
        self._should_cleanup_local = cleanup_local
        self._download_path = get_data_dir() / "AiDownloadCache"
        self._file_cache: dict[str, dict[str, Any]] = {}
        # 预加载远程文件缓存
        if self._use_api:
            self._initialize_cache()

    def _initialize_cache(self) -> None:
        """预加载远程文件列表"""
        try:
            files = self._client.files.list()
            for f in files.data:
                self._file_cache[f.filename] = {
                    "id": f.id,
                    "size": getattr(f, "bytes", 0),
                    "created_at": f.created_at,
                }
        except Exception as e:
            logger.debug(f"预加载远程文件缓存失败（可忽略）: {e}")

    def convert(self, url: str) -> str:
        """下载 PPT 并转为文本，完成后清理本地临时文件"""
        try:
            local_path = self._download(url)
            if self._use_api:
                file_id = self._upload(local_path)
                text = self._extract(file_id)
                if self._delete_after_convert:
                    self._delete_remote(file_id)
                self._manage_cache()
            else:
                text = self._extract_local(local_path)
            if self._should_cleanup_local:
                self._cleanup_local(local_path)
            return text
        except Exception as e:
            logger.error(f"PPT 转换失败: {e}")
            return ""

    def _download(self, url: str) -> Path:
        """下载 PPT 文件到本地"""
        from urllib.parse import urlparse

        import httpx

        parsed = urlparse(url)
        file_path = parsed.path.lstrip("/")
        local_path = self._download_path / file_path

        if local_path.exists():
            logger.info(f"文件已存在: {local_path}")
            return local_path

        local_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.stream("GET", url) as response:
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        logger.info(f"文件已下载: {local_path}")
        return local_path

    def _upload(self, file_path: Path) -> str:
        """上传文件到 MoonShot，返回 file_id"""
        filename = file_path.name
        file_size = file_path.stat().st_size

        # 检查缓存
        if filename in self._file_cache and self._file_cache[filename]["size"] == file_size:
            logger.info(f"文件 {filename} 已存在于服务器，使用缓存")
            return str(self._file_cache[filename]["id"])

        file_object = self._client.files.create(file=file_path, purpose="file-extract")
        self._file_cache[filename] = {
            "id": file_object.id,
            "size": file_size,
            "created_at": file_object.created_at,
        }
        return str(file_object.id)

    def _extract(self, file_id: str) -> str:
        """提取文本，先通过 API 获取内容，再尝试 JSON 解析取 content 字段"""
        raw_text = self._extract_from_api(file_id)
        try:
            json_content = json.loads(raw_text)
            return str(json_content.get("content", raw_text))
        except (json.JSONDecodeError, TypeError):
            return raw_text

    def _extract_from_api(self, file_id: str) -> str:
        """通过 MoonShot API 提取文件内容"""
        return str(self._client.files.content(file_id=file_id).text)

    def _extract_local(self, file_path: Path) -> str:
        """使用 python-pptx 本地提取 PPT 文本"""
        from pptx import Presentation

        prs = Presentation(str(file_path))
        texts: list[str] = []
        for slide_idx, slide in enumerate(prs.slides, 1):
            slide_texts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_texts.append(text)
                if shape.has_table:
                    for row in shape.table.rows:
                        row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_texts:
                            slide_texts.append(" | ".join(row_texts))
            if slide_texts:
                texts.append(f"[幻灯片 {slide_idx}]\n" + "\n".join(slide_texts))
        return "\n\n".join(texts)

    def _delete_remote(self, file_id: str) -> None:
        """删除远程文件"""
        try:
            self._client.files.delete(file_id=file_id)
            logger.info(f"远程文件 {file_id} 已删除")
            self._file_cache = {k: v for k, v in self._file_cache.items() if v["id"] != file_id}
        except Exception as e:
            logger.error(f"删除远程文件 {file_id} 失败: {e}")

    def _cleanup_local(self, file_path: Path) -> None:
        """清理本地临时文件"""
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"本地文件已清理: {file_path}")
        except Exception as e:
            logger.error(f"清理本地文件失败: {e}")

    def _manage_cache(self) -> None:
        """按 LRU 策略清理远程缓存"""
        total_size = sum(f["size"] for f in self._file_cache.values())
        total_files = len(self._file_cache)

        while (total_files > self._max_cache_files or total_size > self._max_cache_size) and self._file_cache:
            oldest_name = min(self._file_cache, key=lambda k: self._file_cache[k]["created_at"])
            oldest = self._file_cache[oldest_name]
            self._delete_remote(oldest["id"])
            total_size -= oldest["size"]
            total_files -= 1

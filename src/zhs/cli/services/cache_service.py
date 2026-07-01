"""缓存管理服务 — export / import

zhs cache export -c COURSE_ID [--type zhidao/ai/auto] [-o OUTPUT_DIR]
zhs cache import PATH [PATH ...]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from zhs.cache.ai_cache import AiExamCache
from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
from zhs.utils.path import get_data_dir


def export_course(
    course_id: int,
    course_type: str = "auto",
    output_dir: str | None = None,
) -> Path:
    """导出课程缓存为 JSON 文件

    Args:
        course_id: 课程 ID
        course_type: 课程类型 zhidao/ai/auto
        output_dir: 输出目录，默认 ~/.zhs/cache/

    Returns:
        导出的文件路径
    """
    cache_dir = get_data_dir() / "cache"
    out_dir = Path(output_dir) if output_dir else cache_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 自动检测：先试知到，无数据再试 AI
    if course_type == "auto":
        zhidao_cache = ZhidaoHomeworkCache(cache_dir=cache_dir)
        zhidao_data = zhidao_cache.export_course(course_id)
        if zhidao_data["exams"]:
            return _write_export(out_dir / "zhidao", zhidao_data)
        ai_cache = AiExamCache(cache_dir=cache_dir)
        ai_data = ai_cache.export_course(course_id)
        if ai_data["exams"]:
            return _write_export(out_dir / "ai", ai_data)
        logger.warning(f"课程 {course_id} 无缓存数据（zhidao/ai 均为空）")
        raise ValueError(f"课程 {course_id} 无缓存数据")

    if course_type == "zhidao":
        data = ZhidaoHomeworkCache(cache_dir=cache_dir).export_course(course_id)
        return _write_export(out_dir / "zhidao", data)

    if course_type == "ai":
        data = AiExamCache(cache_dir=cache_dir).export_course(course_id)
        return _write_export(out_dir / "ai", data)

    raise ValueError(f"不支持的课程类型: {course_type}（支持 zhidao/ai/auto）")


def _write_export(subdir: Path, data: dict[str, Any]) -> Path:
    """写入导出文件，返回路径"""
    subdir.mkdir(parents=True, exist_ok=True)
    course_id = data["course_id"]
    path = subdir / f"{course_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"导出完成: {path}")
    return path


def import_files(file_paths: list[str]) -> int:
    """导入缓存 JSON 文件

    Args:
        file_paths: JSON 文件路径列表

    Returns:
        成功导入的文件数
    """
    cache_dir = get_data_dir() / "cache"
    zhidao_cache = ZhidaoHomeworkCache(cache_dir=cache_dir)
    ai_cache = AiExamCache(cache_dir=cache_dir)

    count = 0
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            logger.error(f"文件不存在: {path}")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"读取文件失败 {path}: {e}")
            continue

        data_type = data.get("type", "")
        if data_type == "zhidao":
            zhidao_cache.import_course(data)
            logger.info(f"导入知到缓存: {path}（{len(data.get('exams', []))} 个 exam）")
            count += 1
        elif data_type == "ai":
            ai_cache.import_course(data)
            logger.info(f"导入 AI 缓存: {path}（{len(data.get('exams', []))} 个 exam）")
            count += 1
        else:
            logger.error(f"未知缓存类型 '{data_type}'，跳过: {path}")

    return count

"""课程类型检测与 URL 解析

从原 __main__.py 抽离的课程类型相关纯函数：
- detect_course_type: 检测课程类型（zhidao/hike/ai）
- validate_course_type: 校验 --type 参数
- parse_ai_course_str: 解析 "courseId:classId" 字符串
- parse_homework_url: 解析作业 URL
"""

import re

from loguru import logger

VALID_COURSE_TYPES = ("zhidao", "hike", "ai", "auto")


def validate_course_type(course_type: str | None) -> str | None:
    """校验 --type 参数，无效值打印错误并返回 None"""
    if course_type is None:
        return None
    if course_type not in VALID_COURSE_TYPES:
        from zhs.utils.display import msg_error

        print(msg_error(f"不支持的课程类型: {course_type}，可选值: {', '.join(VALID_COURSE_TYPES)}"))
        return None
    return course_type


def detect_course_type(course_id: str, course_type: str | None = None) -> str:
    """检测课程类型

    - 显式 type 优先
    - 含字母 → zhidao
    - 纯数字 → hike
    """
    if course_type:
        return course_type
    if re.search(r"[a-zA-Z]", course_id):
        return "zhidao"
    return "hike"


def parse_ai_course_str(course_id_str: str) -> tuple[int, int] | None:
    """解析 AI 课程字符串 "courseId:classId"

    Returns:
        (course_id, class_id) 或 None（格式错误时）
    """
    parts = course_id_str.split(":")
    if len(parts) != 2:
        logger.error(f"AI 课程 ID 格式错误，应为 courseId:classId，实际: {course_id_str}")
        return None
    try:
        course_id = int(parts[0])
        class_id = int(parts[1])
    except ValueError:
        logger.error(f"AI 课程 ID 格式错误，courseId/classId 必须为整数: {course_id_str}")
        return None
    return course_id, class_id


def parse_homework_url(url: str) -> dict[str, str]:
    """解析作业 URL

    URL 格式:
    https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/{recruitId}/{stuExamId}/{examId}/{courseId}/{schoolId}/0

    注意: URL 中参数顺序是 stuExamId 在前，examId 在后，与 HomeworkItem 字段名相反。

    Returns:
        包含 recruit_id, exam_id, stu_exam_id, course_id, school_id 的字典
    """
    # 匹配 dohomework/ 后的路径参数
    pattern = r"dohomework/([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)"
    m = re.search(pattern, url)
    if not m:
        raise ValueError(
            f"无法解析作业 URL，"
            f"格式应为: dohomework/{{recruitId}}/{{stuExamId}}/"
            f"{{examId}}/{{courseId}}/{{schoolId}}/...\n"
            f"实际 URL: {url}"
        )

    return {
        "recruit_id": m.group(1),
        "stu_exam_id": m.group(2),  # URL 第 2 个参数是 stuExamId
        "exam_id": m.group(3),  # URL 第 3 个参数是 examId
        "course_id": m.group(4),
        "school_id": m.group(5),
    }


__all__ = [
    "VALID_COURSE_TYPES",
    "detect_course_type",
    "parse_ai_course_str",
    "parse_homework_url",
    "validate_course_type",
]

"""课程类型检测与 URL 解析

从原 __main__.py 抽离的课程类型相关纯函数：
- detect_course: 解析 -c，返回 (类型, 匹配到的知到课程)
- detect_course_type: 只返回类型（显式 --type 时零查询）
- validate_course_type: 校验 --type 参数
- parse_ai_course_str: 解析 "courseId:classId" 字符串
- parse_homework_url: 解析作业 URL
"""

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from zhs.zhidao.models import ZhidaoCourse

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


def _ensure_numeric_course_id(course_id: str) -> int:
    """校验 courseId 为纯数字且为正整数，返回 int

    Raises:
        ValueError: 非纯数字（如 recruitAndCourseId）或非正整数
    """
    if not course_id.isdigit():
        raise ValueError(
            f"无法识别的课程 ID: {course_id!r}。课程 ID 必须为纯数字 courseId（AI 课程为 courseId:classId）；"
            f"recruitAndCourseId 请通过 --url 传入"
        )
    cid_int = int(course_id)
    if cid_int <= 0:
        raise ValueError(f"课程 ID 必须为正整数，实际: {course_id!r}")
    return cid_int


def detect_course(
    course_id: str,
    course_type: str | None = None,
    session: "object | None" = None,
) -> tuple[str, "ZhidaoCourse | None"]:
    """解析 `-c` 课程 ID，返回 (类型, 匹配到的知到课程)

    只查询一次知到课程列表，同时得出类型与课程对象（供反查 rac_id 使用）。

    - 显式 type 优先（`auto` 视为自动检测）
    - 含冒号 → `("ai", None)`
    - 显式 hike → `("hike", None)`
    - 显式 zhidao / 纯数字自动检测 → 查一次知到列表：
      命中 → `("zhidao", course)`；未命中且显式 zhidao → 报错；否则 → `("hike", None)`
    - 列表拉取失败 → 抛 ValueError，提示用 --type 显式指定（不静默回退 hike）

    Args:
        course_id: 课程 ID 字符串
        course_type: 显式类型（优先；`auto` 表示自动检测）
        session: ZhsSession，知到课程查询/Hike 兜底需要

    Raises:
        ValueError: 课程 ID 非法、知到课程未找到、或无法获取知到课程列表
    """
    explicit = course_type if course_type not in (None, "auto") else None

    if explicit == "ai" or (explicit is None and ":" in course_id):
        return "ai", None
    if explicit == "hike":
        _ensure_numeric_course_id(course_id)
        return "hike", None
    if explicit not in (None, "zhidao"):
        raise ValueError(f"未知课程类型: {explicit}")

    cid_int = _ensure_numeric_course_id(course_id)

    # 显式 zhidao 需要 session 反查 rac_id；自动检测无 session 时无法查列表
    if explicit == "zhidao" and session is None:
        raise ValueError("知到课程需 session 来反查 recruitAndCourseId")
    if session is None:
        return "hike", None

    try:
        from zhs.zhidao.course import ZhidaoCourseManager

        mgr = ZhidaoCourseManager(session)  # type: ignore[arg-type]
        course = mgr.find_course(cid_int)
    except Exception as e:
        # 不静默回退 hike：列表拉取失败时无法判断，交由用户显式指定
        logger.error(f"获取知到课程列表失败: {e}")
        raise ValueError(
            f"无法获取知到课程列表，无法自动判断课程类型；请用 --type 显式指定 zhidao 或 hike（原始错误: {e}）"
        ) from e

    if course is not None:
        return "zhidao", course
    if explicit == "zhidao":
        raise ValueError(f"未找到 courseId={cid_int} 的知到课程")
    return "hike", None


def detect_course_type(
    course_id: str,
    course_type: str | None = None,
    session: "object | None" = None,
) -> str:
    """检测课程类型（只需要类型、不需要课程对象时使用）

    显式 `--type` 为纯透传，不触发任何网络查询；自动检测等价于 `detect_course()[0]`。

    Raises:
        ValueError: 课程 ID 非法、知到课程未找到、或无法获取知到课程列表
    """
    if course_type and course_type != "auto":
        return course_type
    return detect_course(course_id, None, session)[0]


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
    "detect_course",
    "detect_course_type",
    "parse_ai_course_str",
    "parse_homework_url",
    "validate_course_type",
]

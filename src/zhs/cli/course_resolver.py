"""统一 -c 参数解析

将 courseId 字符串解析为 ResolvedCourse，包含类型和必要的内部 ID。

- 知到: courseId（纯数字）→ 需反查 recruitAndCourseId
- Hike: courseId（纯数字）→ 直接用
- AI: courseId:classId → 两个 ID
"""

from dataclasses import dataclass

from loguru import logger

from zhs.cli.course_type import detect_course_type, parse_ai_course_str


@dataclass
class ResolvedCourse:
    """解析后的课程信息"""

    type: str  # "zhidao" / "hike" / "ai"
    course_id: int
    # AI 课程专用
    class_id: int | None = None
    # 知到专用（recruitAndCourseId）
    rac_id: str | None = None


def resolve_course_id(
    course_id_str: str,
    course_type: str | None = None,
    session: "object | None" = None,
) -> ResolvedCourse:
    """统一解析 -c 参数

    Args:
        course_id_str: 课程 ID 字符串（courseId 或 courseId:classId）
        course_type: 显式类型（优先于自动检测）
        session: ZhsSession，知到课程反查 recruitAndCourseId 时需要

    Returns:
        ResolvedCourse: 包含 type + 必要的内部 ID
    """
    detected = detect_course_type(course_id_str, course_type, session)

    # 知到：courseId → 需查 recruitAndCourseId
    if detected == "zhidao":
        if session is None:
            raise ValueError("知到课程需 session 来反查 recruitAndCourseId")
        rac_id = _find_rac_by_course_id(session, int(course_id_str))
        return ResolvedCourse(
            type="zhidao",
            course_id=int(course_id_str),
            rac_id=rac_id,
        )

    # Hike：courseId 直接用
    if detected == "hike":
        return ResolvedCourse(type="hike", course_id=int(course_id_str))

    # AI：courseId:classId
    if detected == "ai":
        parsed = parse_ai_course_str(course_id_str)
        if parsed is None:
            raise ValueError(f"AI 课程 ID 格式错误: {course_id_str}")
        return ResolvedCourse(type="ai", course_id=parsed[0], class_id=parsed[1])

    raise ValueError(f"未知课程类型: {detected}")


def _find_rac_by_course_id(session: "object", course_id: int) -> str:
    """通过 courseId 反查 recruitAndCourseId

    遍历课程列表（列表 API 已返回 courseId），找到匹配项。

    Args:
        session: ZhsSession
        course_id: 知到课程 courseId

    Returns:
        recruitAndCourseId 字符串

    Raises:
        ValueError: 未找到匹配课程
    """
    from zhs.zhidao.course import ZhidaoCourseManager

    mgr = ZhidaoCourseManager(session)  # type: ignore[arg-type]
    for c in mgr.get_course_list():
        if c.course_id == course_id:
            return c.secret
    logger.error(f"未找到 courseId={course_id} 的知到课程")
    raise ValueError(f"未找到 courseId={course_id} 的知到课程")


__all__ = ["ResolvedCourse", "resolve_course_id"]

"""统一 -c 参数解析

将 courseId 字符串解析为 ResolvedCourse，包含类型和必要的内部 ID。

- 知到: courseId（纯数字）→ 需反查 recruitAndCourseId
- Hike: courseId（纯数字）→ 直接用
- AI: courseId:classId → 两个 ID

`-c/--course` 只接受 courseId；recruitAndCourseId 只能通过 `--url` 传入。
"""

from dataclasses import dataclass

from zhs.cli.course_type import detect_course, parse_ai_course_str


@dataclass
class ResolvedCourse:
    """解析后的课程信息"""

    type: str  # "zhidao" / "hike" / "ai"
    course_id: int
    # AI 课程专用
    class_id: int | None = None
    # 知到专用（recruitAndCourseId）
    rac_id: str | None = None
    # 知到专用（recruitId；作业/考试需要，课程未提供时为 None）
    recruit_id: int | None = None


def resolve_course_id(
    course_id_str: str,
    course_type: str | None = None,
    session: "object | None" = None,
) -> ResolvedCourse:
    """统一解析 -c 参数

    知到课程列表只查询一次：`detect_course` 同时给出类型与匹配到的课程，

    Args:
        course_id_str: 课程 ID 字符串（courseId 或 courseId:classId）
        course_type: 显式类型（优先于自动检测）
        session: ZhsSession，知到课程查询时需要

    Returns:
        ResolvedCourse: 包含 type + 必要的内部 ID

    Raises:
        ValueError: 课程 ID 无法识别、知到列表获取失败，或知到课程未找到
    """
    detected, course = detect_course(course_id_str, course_type, session)

    # 知到：courseId → rac_id / recruit_id 均来自匹配到的课程
    if detected == "zhidao":
        if course is None:
            raise ValueError(f"未找到 courseId={course_id_str} 的知到课程")
        return ResolvedCourse(
            type="zhidao",
            course_id=int(course_id_str),
            rac_id=course.secret,
            recruit_id=course.recruit_id,
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


__all__ = ["ResolvedCourse", "resolve_course_id"]

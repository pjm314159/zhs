"""刷视频编排服务

从原 __main__.py 抽离的刷视频相关 _run_* 函数。
"""

from loguru import logger

from zhs.cli.course_type import detect_course_type, parse_ai_course_str
from zhs.config import AppConfig
from zhs.session import ZhsSession


def dispatch_play_url(session: ZhsSession, config: AppConfig, url: str) -> None:
    """解析 play URL 并分发到对应流程"""
    from zhs.cli.url_parser import parse_play_url

    parsed = parse_play_url(url)
    if parsed.type == "zhidao":
        assert parsed.rac_id is not None
        run_zhidao(session, config, parsed.rac_id)
    elif parsed.type == "ai":
        assert parsed.course_id is not None
        assert parsed.class_id is not None
        run_ai(
            session,
            config,
            parsed.course_id,
            parsed.class_id,
            node_uid=parsed.node_uid,
        )


def run_courses(
    session: ZhsSession,
    config: AppConfig,
    courses: list[str],
    course_type: str | None,
) -> None:
    """按课程列表刷课"""
    for c in courses:
        detected_type = detect_course_type(c, course_type)
        try:
            if detected_type == "zhidao":
                run_zhidao(session, config, c)
            elif detected_type == "hike":
                run_hike(session, config, c)
            elif detected_type == "ai":
                run_ai_by_str(session, config, c)
            else:
                print(f"未知的课程类型: {detected_type}，跳过课程 {c}")
        except Exception as e:
            logger.error(f"课程 {c} 处理失败: {e}")
            print(f"课程 {c} 处理失败: {e}")


def run_ai(
    session: ZhsSession,
    config: AppConfig,
    course_id: int,
    class_id: int,
    node_uid: int | None = None,
) -> None:
    """刷 AI 课程（仅视频/知识点，不做作业）

    Args:
        node_uid: 知识点 ID。非 None 时走直接模式（只刷该知识点），None 时全刷
    """
    from zhs.ai.course import AiCourseManager

    mgr = AiCourseManager(session)
    mgr.run_course(
        course_id,
        class_id,
        config.ai,
        config.homework,
        video_config=config.video,
        no_homework=True,
        speed=config.video.ai_speed,
        learn_optional=config.video.ai_learn_optional,
        node_uid=node_uid,
    )


def run_ai_by_str(session: ZhsSession, config: AppConfig, course_id_str: str) -> None:
    """刷 AI 课程（字符串格式 courseId:classId）"""
    parsed = parse_ai_course_str(course_id_str)
    if parsed is None:
        return
    course_id, class_id = parsed
    run_ai(session, config, course_id, class_id)


def run_zhidao(session: ZhsSession, config: AppConfig, course_id: str) -> None:
    """刷知到课程"""
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.video import ZhidaoVideoPlayer

    mgr = ZhidaoCourseManager(session)
    player = ZhidaoVideoPlayer(
        session,
        speed=config.video.zhidao_speed,
        end_threshold=config.threshold,
        time_limit=config.limit * 60,
    )

    rac_id = course_id
    # 如果传入的是纯数字的 courseId（而不是 34 位十六进制 secret），先查询课程列表换取 secret
    if course_id.isdigit():
        courses = mgr.get_course_list()
        for c in courses:
            c_id = getattr(c, "course_id", None) or getattr(c, "courseId", None)
            if c_id is not None and str(c_id) == str(course_id):
                rac_id = c.secret
                break
            if getattr(c, "course_info", None) and str(getattr(c.course_info, "id", "")) == str(course_id):
                rac_id = c.secret
                break
        else:
            logger.warning(f"未能通过 courseId {course_id} 找到对应的 secret，尝试直接作为 rac_id 请求")

    ctx = mgr.get_context(rac_id)
    player.play_course(rac_id, ctx)


def run_hike(session: ZhsSession, config: AppConfig, course_id: str) -> None:
    """刷 Hike 课程"""
    from zhs.hike.course import HikeCourseManager
    from zhs.hike.video import HikeVideoPlayer

    mgr = HikeCourseManager(session)
    player = HikeVideoPlayer(
        session,
        speed=config.video.hike_speed,
        end_threshold=config.threshold,
        time_limit=config.limit * 60,
    )

    root = mgr.get_context(course_id)
    player.play_course(course_id, root)


def run_all(session: ZhsSession, config: AppConfig, course_type: str | None = None) -> None:
    """全刷模式：按 --type 过滤，先刷知到再刷 Hike 再刷 AI"""
    from zhs.ai.course import AiCourseManager
    from zhs.hike.course import HikeCourseManager
    from zhs.hike.video import HikeVideoPlayer
    from zhs.utils.display import course_tag
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.video import ZhidaoVideoPlayer

    # 知到
    if course_type in (None, "auto", "zhidao"):
        try:
            zhidao_mgr = ZhidaoCourseManager(session)
            zhidao_player = ZhidaoVideoPlayer(
                session,
                speed=config.video.zhidao_speed,
                end_threshold=config.threshold,
                time_limit=config.limit * 60,
            )
            courses = zhidao_mgr.get_course_list()
            print(f"\n{course_tag('zhidao')} 发现 {len(courses)} 门课程")
            for c in courses:
                try:
                    ctx = zhidao_mgr.get_context(c.secret)
                    zhidao_player.play_course(c.secret, ctx)
                except Exception as e:
                    logger.error(f"知到课程 {c.course_name} 处理失败: {e}")
                    print(f"知到课程 {c.course_name} 处理失败: {e}")
        except Exception as e:
            logger.error(f"获取知到课程列表失败: {e}")
            print(f"获取知到课程列表失败: {e}")

    # Hike
    if course_type in (None, "auto", "hike"):
        try:
            hike_mgr = HikeCourseManager(session)
            hike_player = HikeVideoPlayer(
                session,
                speed=config.video.hike_speed,
                end_threshold=config.threshold,
                time_limit=config.limit * 60,
            )
            hike_courses = hike_mgr.get_course_list()
            print(f"\n{course_tag('hike')} 发现 {len(hike_courses)} 门课程")
            for hc in hike_courses:
                try:
                    root = hike_mgr.get_context(str(hc.course_id))
                    hike_player.play_course(str(hc.course_id), root)
                except Exception as e:
                    logger.error(f"Hike 课程 {hc.course_name} 处理失败: {e}")
                    print(f"Hike 课程 {hc.course_name} 处理失败: {e}")
        except Exception as e:
            logger.error(f"获取 Hike 课程列表失败: {e}")
            print(f"获取 Hike 课程列表失败: {e}")

    # AI
    if course_type in (None, "auto", "ai"):
        try:
            ai_mgr = AiCourseManager(session)
            ai_courses = ai_mgr.get_ai_course_list()
            print(f"\n{course_tag('ai')} 发现 {len(ai_courses)} 门课程")
            for ac in ai_courses:
                try:
                    course_id = ac.get("courseId")
                    class_id = ac.get("classId")
                    course_name = ac.get("courseName", "")
                    if course_id and class_id:
                        ai_mgr.run_course(
                            int(course_id),
                            int(class_id),
                            config.ai,
                            config.homework,
                            video_config=config.video,
                            no_homework=True,
                            speed=config.video.ai_speed,
                            learn_optional=config.video.ai_learn_optional,
                        )
                    else:
                        logger.warning(f"AI 课程 {course_name} 缺少 courseId 或 classId")
                        print(f"AI 课程 {course_name} 缺少 courseId 或 classId")
                except Exception as e:
                    logger.error(f"AI 课程 {ac.get('courseName', '')} 处理失败: {e}")
                    print(f"AI 课程 {ac.get('courseName', '')} 处理失败: {e}")
        except Exception as e:
            logger.error(f"获取 AI 课程列表失败: {e}")
            print(f"获取 AI 课程列表失败: {e}")


__all__ = [
    "dispatch_play_url",
    "run_ai",
    "run_ai_by_str",
    "run_all",
    "run_courses",
    "run_hike",
    "run_zhidao",
]

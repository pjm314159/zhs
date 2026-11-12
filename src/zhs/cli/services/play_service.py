"""刷视频编排服务

从原 __main__.py 抽离的刷视频相关 _run_* 函数。
"""

from typing import TYPE_CHECKING

from loguru import logger

from zhs.cli.course_type import parse_ai_course_str
from zhs.config import AppConfig
from zhs.session import ZhsSession

if TYPE_CHECKING:
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.models import ZhidaoContext, ZhidaoCourse


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
    """按课程列表刷课

    `-c` 传入 courseId：知到课程会先反查 recruitAndCourseId 再刷课；
    recruitAndCourseId 只能通过 `--url` 传入。
    """
    from zhs.cli.course_resolver import resolve_course_id

    for c in courses:
        try:
            resolved = resolve_course_id(c, course_type, session)
            if resolved.type == "zhidao":
                assert resolved.rac_id is not None
                run_zhidao(session, config, resolved.rac_id)
            elif resolved.type == "hike":
                run_hike(session, config, c)
            elif resolved.type == "ai":
                run_ai_by_str(session, config, c)
            else:
                logger.warning(f"未知的课程类型: {resolved.type}，跳过课程 {c}")
                print(f"未知的课程类型: {resolved.type}，跳过课程 {c}")
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


def run_zhidao(session: ZhsSession, config: AppConfig, rac_id: str) -> None:
    """刷知到课程

    Args:
        rac_id: recruitAndCourseId，仅由 --url 解析或课程列表（secret）提供
    """
    from zhs.zhidao.course import ZhidaoCourseManager

    mgr = ZhidaoCourseManager(session)
    ctx = mgr.get_context(rac_id)
    end_ms = next((c.course_end_time for c in _safe_course_list(mgr) if c.secret == rac_id), None)
    play_zhidao_course(session, config, rac_id, ctx, end_ms)


def _safe_course_list(mgr: "ZhidaoCourseManager") -> list["ZhidaoCourse"]:
    """课程列表（只用来取截止时间，取不到不影响播放）"""
    try:
        return mgr.get_course_list()
    except Exception as e:
        logger.debug(f"课程列表获取失败，计划不考虑截止日: {e}")
        return []


def play_zhidao_course(
    session: ZhsSession,
    config: AppConfig,
    rac_id: str,
    ctx: "ZhidaoContext",
    end_ms: int | None,
) -> None:
    """按学习计划播放一门知到课程

    zhidao_plan 开启时：首日刷大部分，之后每天按配额学，今天的预算用作播放器的时间上限。
    --limit 显式给出时两者取更小的那个。
    """
    from datetime import date

    from zhs.utils.display import msg_info, msg_skip
    from zhs.utils.path import get_data_dir
    from zhs.zhidao.schedule import StudyLedger, end_date_from_ms, plan_today
    from zhs.zhidao.video import ZhidaoVideoPlayer

    time_limit = config.limit * 60
    ledger: StudyLedger | None = None
    today = date.today()

    if config.video.zhidao_plan:
        ledger = StudyLedger(get_data_dir() / "study_plan.json")
        plan = plan_today(
            remaining_seconds=_remaining_seconds(ctx, config.threshold),
            today=today,
            first_day=ledger.first_day(rac_id, today),
            end_day=end_date_from_ms(end_ms),
            studied_today=ledger.studied(rac_id, today),
            daily_minutes=config.video.zhidao_daily_minutes,
        )
        logger.info(f"学习计划 {rac_id}: {plan}")
        if plan.budget_seconds <= 0:
            print(msg_skip(plan.describe()))
            return
        print(msg_info(plan.describe()))
        time_limit = min(time_limit, plan.budget_seconds) if time_limit > 0 else plan.budget_seconds

    player = ZhidaoVideoPlayer(
        session,
        speed=config.video.zhidao_speed,
        end_threshold=config.threshold,
        time_limit=time_limit,
    )
    before = ctx.fucked_time
    try:
        player.play_course(rac_id, ctx)
    finally:
        if ledger is not None:
            ledger.add(rac_id, today, ctx.fucked_time - before)


def _remaining_seconds(ctx: "ZhidaoContext", threshold: float) -> int:
    """课程还需观看的秒数（真实时间，按 1.0 倍估算）

    旧版课：未完成视频的 (时长 × 阈值 − 已看位置)；位置用 studyTotalTime 夹在时长内估算。
    新版图谱课：视频进度要逐节点查询，这里按全部节点时长未知处理，返回 0 表示不限
    （由 plan_today 的最低配额兜底）。
    """
    if ctx.mode == "map":
        return 0
    total = 0
    for v in ctx.videos.values():
        if v.watch_state == 1:
            continue
        target = int(v.video_sec * min(threshold, 1.0))
        watched = min(v.study_total_time, v.video_sec)
        total += max(target - watched, 0)
    return total


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

    # 知到
    if course_type in (None, "auto", "zhidao"):
        try:
            zhidao_mgr = ZhidaoCourseManager(session)
            courses = zhidao_mgr.get_course_list()
            print(f"\n{course_tag('zhidao')} 发现 {len(courses)} 门课程")
            for c in courses:
                try:
                    ctx = zhidao_mgr.get_context(c.secret)
                    play_zhidao_course(session, config, c.secret, ctx, c.course_end_time)
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

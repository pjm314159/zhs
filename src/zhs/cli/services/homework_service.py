"""作业编排服务

从原 __main__.py 抽离的作业相关 _run_* 函数。
"""

from loguru import logger

from zhs.cli.course_type import parse_ai_course_str, parse_homework_url
from zhs.config import AppConfig
from zhs.exceptions import SliderVerificationRequired
from zhs.session import ZhsSession


def run_homework_from_url(session: ZhsSession, config: AppConfig, url: str) -> None:
    """从 URL 运行作业"""
    from zhs.utils.display import course_tag, msg_done, msg_warn, tree_print

    params = parse_homework_url(url)
    logger.info(
        f"解析 URL: recruitId={params['recruit_id']}, examId={params['exam_id']}, "
        f"stuExamId={params['stu_exam_id']}, courseId={params['course_id']}, schoolId={params['school_id']}"
    )

    # CAS SSO
    session.exam_sso_login()

    # 扫描该课程的所有作业
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
    from zhs.zhidao.homework.models import HomeworkItem
    from zhs.zhidao.homework.scanner import HomeworkScanner
    from zhs.zhidao.homework.worker import HomeworkWorker

    scanner = HomeworkScanner(session, config)
    course_id = int(params["course_id"])
    all_items = scanner.scan_homework(params["recruit_id"], course_id)

    # 找到指定的作业
    target = None
    for item in all_items:
        if item.exam_id == params["exam_id"]:
            target = item
            break

    if target is None:
        # URL 指定的作业不在列表中，构造一个 HomeworkItem
        logger.info(f"作业 {params['exam_id']} 不在扫描列表中，使用 URL 参数构造")
        target = HomeworkItem(
            id=params["stu_exam_id"],
            exam_id=params["exam_id"],
            state=1,
            course_id=course_id,
            course_name="",
            exam_name="指定作业",
            total_score="10",
        )

    tree_print(f"{course_tag('zhidao')} 作业: {target.exam_name}", enabled=True)
    logger.info(
        f"  state={target.state}, score={target.score}, backNum={target.back_num}, isMarking={target.is_marking}"
    )

    from zhs.cli.bootstrap import init_llm

    llm = init_llm(config)
    cache = ZhidaoHomeworkCache()
    worker = HomeworkWorker(session, config, cache, llm=llm)
    score_rate = worker.run_homework(target, params["recruit_id"], params["school_id"])

    if score_rate >= config.homework.threshold:
        tree_print(msg_done(f"达标: {target.exam_name} {score_rate:.1f}%"), depth=1, enabled=True)
    else:
        tree_print(msg_warn(f"未达标: {target.exam_name} {score_rate:.1f}%"), depth=1, enabled=True)


def run_zhidao_homework_by_course(
    session: ZhsSession, config: AppConfig, recruit_and_course_id: str
) -> None:
    """按 recruitAndCourseId 运行知到作业

    Args:
        recruit_and_course_id: 课程的 recruitAndCourseId（secret 字符串）
    """
    from zhs.zhidao.course import ZhidaoCourseManager

    # CAS SSO
    session.exam_sso_login()

    # 通过 secret（recruitAndCourseId）匹配课程，获取 recruit_id 和数字 courseId
    mgr = ZhidaoCourseManager(session)
    courses = mgr.get_course_list()
    matched = None
    for c in courses:
        if c.secret == recruit_and_course_id and c.recruit_id:
            matched = c
            break

    if matched is None:
        logger.error(f"未找到课程 {recruit_and_course_id}（recruitAndCourseId 未匹配到任何课程）")
        print(f"未找到课程 {recruit_and_course_id} 的 recruitId")
        return

    logger.info(
        f"匹配到课程: {matched.course_name} "
        f"(courseId={matched.course_id}, recruitId={matched.recruit_id})"
    )
    run_zhidao_homework(session, config, str(matched.recruit_id), matched.course_id)


def run_zhidao_homework(
    session: ZhsSession,
    config: AppConfig,
    recruit_id: str,
    course_id: int,
    depth: int = 0,
) -> None:
    """运行知到课程的所有待处理作业

    Args:
        depth: 树形打印深度（0=顶层，1=在课程循环中）
    """
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
    from zhs.utils.display import (
        course_tag,
        msg_done,
        msg_error,
        msg_skip,
        msg_warn,
        tree_print,
    )
    from zhs.zhidao.homework.scanner import HomeworkScanner
    from zhs.zhidao.homework.worker import HomeworkWorker

    scanner = HomeworkScanner(session, config)
    all_items = scanner.scan_homework(recruit_id, course_id)

    tree_print(f"{course_tag('zhidao')} 课程作业: 共 {len(all_items)} 个", depth=depth, enabled=True)

    pending = scanner.filter_pending(all_items)

    if not pending:
        tree_print(msg_skip("无待处理作业"), depth=depth + 1, enabled=True)
        return

    tree_print(msg_done(f"待处理: {len(pending)} 个作业"), depth=depth + 1, enabled=True)

    from zhs.cli.bootstrap import init_llm

    llm = init_llm(config)
    cache = ZhidaoHomeworkCache()
    worker = HomeworkWorker(session, config, cache, llm=llm)

    for item in pending:
        try:
            logger.info(f"开始做作业: {item.exam_name} (state={item.state}, score={item.score})")
            score_rate = worker.run_homework(item, recruit_id, "625")
            if score_rate >= config.homework.threshold:
                tree_print(
                    msg_done(f"完成: {item.exam_name} {score_rate:.1f}%"),
                    depth=depth + 2,
                    enabled=True,
                )
            else:
                tree_print(
                    msg_warn(f"未达标: {item.exam_name} {score_rate:.1f}%"),
                    depth=depth + 2,
                    enabled=True,
                )
        except SliderVerificationRequired:
            # 滑块验证：服务端状态，后续作业也会失败，立即停止
            raise
        except Exception as e:
            logger.error(f"作业 {item.exam_name} 处理失败: {e}")
            tree_print(msg_error(f"失败: {item.exam_name} {e}"), depth=depth + 2, enabled=True)


def run_all_zhidao_homework(session: ZhsSession, config: AppConfig) -> None:
    """全刷模式：扫描所有知到课程的作业"""
    from zhs.utils.display import course_tag, msg_error, msg_skip, tree_print
    from zhs.zhidao.course import ZhidaoCourseManager

    # CAS SSO
    session.exam_sso_login()

    mgr = ZhidaoCourseManager(session)
    courses = mgr.get_course_list()
    tree_print(f"{course_tag('zhidao')} 发现 {len(courses)} 门课程", enabled=True)
    for c in courses:
        if not c.recruit_id:
            tree_print(msg_skip(f"跳过(无招募ID): {c.course_name}"), depth=1, enabled=True)
            continue
        try:
            recruit_id = str(c.recruit_id)
            # 优先使用直接的 courseId，如果为 0 则回退到 courseInfo.courseId
            course_id = c.course_id if c.course_id > 0 else (c.course_info.course_id if c.course_info else 0)
            if course_id == 0:
                tree_print(msg_skip(f"跳过(无课程ID): {c.course_name}"), depth=1, enabled=True)
                continue
            run_zhidao_homework(session, config, recruit_id, course_id, depth=1)
        except SliderVerificationRequired:
            # 滑块验证：服务端状态，后续课程也会失败，立即停止
            raise
        except Exception as e:
            logger.error(f"知到课程 {c.course_name} 作业处理失败: {e}")
            tree_print(msg_error(f"课程失败: {c.course_name} {e}"), depth=1, enabled=True)


def run_ai_homework(session: ZhsSession, config: AppConfig, course_id: int, class_id: int) -> None:
    """AI 课程作业（仅做作业，不刷视频）"""
    from zhs.ai.course import AiCourseManager

    mgr = AiCourseManager(session)
    mgr.run_course(course_id, class_id, config.ai, config.homework, speed=config.video.ai_speed)


def run_ai_homework_by_str(session: ZhsSession, config: AppConfig, course_id_str: str) -> None:
    """AI 课程作业（字符串格式 courseId:classId）"""
    parsed = parse_ai_course_str(course_id_str)
    if parsed is None:
        return
    course_id, class_id = parsed
    run_ai_homework(session, config, course_id, class_id)


def run_all_homework(session: ZhsSession, config: AppConfig, course_type: str | None) -> None:
    """全刷作业模式"""
    from zhs.ai.course import AiCourseManager
    from zhs.utils.display import course_tag

    # 知到课程作业
    if course_type in (None, "auto", "zhidao"):
        try:
            run_all_zhidao_homework(session, config)
        except SliderVerificationRequired:
            # 滑块验证：立即停止，不继续 AI 课程作业
            raise
        except Exception as e:
            logger.error(f"知到课程作业处理失败: {e}")
            print(f"知到课程作业处理失败: {e}")

    # AI 课程作业
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
                            speed=config.video.ai_speed,
                        )
                    else:
                        logger.warning(f"AI 课程 {course_name} 缺少 courseId 或 classId")
                except Exception as e:
                    logger.error(f"AI 课程 {ac.get('courseName', '')} 作业处理失败: {e}")
        except Exception as e:
            logger.error(f"获取 AI 课程列表失败: {e}")


__all__ = [
    "run_ai_homework",
    "run_ai_homework_by_str",
    "run_all_homework",
    "run_all_zhidao_homework",
    "run_homework_from_url",
    "run_zhidao_homework",
    "run_zhidao_homework_by_course",
]

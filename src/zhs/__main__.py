"""ZHS CLI 入口

智慧树自动刷课工具，支持知到/Hike/AI 课程。

用法:
  zhs init                初始化配置
  zhs login               扫码登录
  zhs play                刷视频
  zhs exam                考试（暂未实现）
  zhs homework            写作业
  zhs fetch               获取课程列表
"""

import sys
from typing import Any

import typer
from loguru import logger

from zhs.config import AppConfig, ConfigManager
from zhs.llm.base import LLMProvider
from zhs.login import LoginManager
from zhs.session import ZhsSession

app = typer.Typer(name="zhs", help="智慧树自动刷课工具", no_args_is_help=True)


# ---------------------------------------------------------------------------
# 公共辅助函数
# ---------------------------------------------------------------------------


def _setup_logger(config: AppConfig, debug: bool, console_log: bool) -> None:
    """配置日志"""
    log_level = "DEBUG" if debug else config.display.log_level
    logger.remove()
    from zhs.utils.path import get_data_dir

    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_pattern = str(log_dir / "zhs_{time:YYYY-MM-DD}.log")
    logger.add(
        log_file_pattern,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {thread.name} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )
    if console_log or debug:
        console_fmt = "<level>{level:<7}</level> | <cyan>{name}</cyan> - {message}"
        logger.add(sys.stderr, level="INFO", format=console_fmt)
    logger.info(f"日志目录: {log_dir}")


def _parse_proxy(config: AppConfig, proxy: str) -> None:
    """解析代理字符串"""
    parts = proxy.lower().split("://")
    if len(parts) != 2:
        logger.error(f"不支持的代理格式: {proxy}")
        return

    schema, _ = parts
    if schema in ("http", "https", "socks5"):
        config.proxies.http = proxy
        config.proxies.https = proxy
    else:
        logger.error(f"不支持的代理类型: {schema}")


def _load_config_and_session(debug: bool, console_log: bool, proxy: str | None) -> tuple[AppConfig, ZhsSession] | None:
    """加载配置、创建 session、恢复 cookies。失败返回 None。"""
    config_mgr = ConfigManager()
    config = config_mgr.load()

    if proxy:
        _parse_proxy(config, proxy)

    _setup_logger(config, debug, console_log)

    session = ZhsSession(config)

    if not _try_restore_cookies(session, config):
        from zhs.utils.display import msg_error

        print(msg_error("未登录或 Cookie 已过期，请先运行 zhs login 登录"))
        return None

    return config, session


def _try_restore_cookies(session: ZhsSession, config: AppConfig) -> bool:
    """尝试恢复 cookies，成功返回 True"""
    if not config.save_cookies:
        return False

    from zhs.utils.cookie import list_to_cookies
    from zhs.utils.path import get_data_dir

    cookies_path = get_data_dir() / "cookies.json"
    if not cookies_path.exists():
        return False

    try:
        import json

        with open(cookies_path, encoding="utf-8") as f:
            raw = json.load(f)
        session.cookies = list_to_cookies(raw)

        # 验证 cookies 有效性
        from zhs.zhidao.course import ZhidaoCourseManager

        mgr = ZhidaoCourseManager(session)
        courses = mgr.get_course_list()
        if courses:
            logger.info("Cookie 恢复成功")
            from zhs.utils.display import msg_done

            print(msg_done("登录状态有效"))
            return True
    except Exception as e:
        logger.debug(f"Cookie 恢复失败: {e}")

    return False


def _do_login(login_mgr: LoginManager, config: AppConfig, show_in_terminal: bool) -> None:
    """执行扫码登录"""
    from zhs.utils.display import show_qrcode_img as _show_qr_img

    def qr_callback(img_bytes: bytes) -> None:
        if show_in_terminal:
            _show_qr_img(img_bytes)

    result = login_mgr.login_with_qr(qr_callback, image_path=config.qr.image_path)
    if not result.success:
        logger.error("登录失败")
        raise typer.Exit(1)

    logger.info("登录成功")

    # 保存 cookies
    if config.save_cookies and result.cookies:
        import json

        from zhs.utils.cookie import cookies_to_list
        from zhs.utils.path import get_data_dir

        cookies_path = get_data_dir() / "cookies.json"
        with open(cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies_to_list(result.cookies), f, indent=2, ensure_ascii=False)
        logger.info(f"Cookie 已保存到 {cookies_path}")


# ---------------------------------------------------------------------------
# zhs init
# ---------------------------------------------------------------------------


@app.command()
def init() -> None:
    """初始化 .zhs/ 目录及默认配置"""
    from zhs.utils.path import get_data_dir

    data_dir = get_data_dir()
    config_mgr = ConfigManager()

    # 创建目录结构
    (data_dir / "cache").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    # 保存默认配置
    config_path = config_mgr.config_path
    if not config_path.exists():
        config_mgr.save(AppConfig())
        print(f"配置文件已创建: {config_path}")
    else:
        print(f"配置文件已存在: {config_path}")

    print(f"数据目录: {data_dir}")


# ---------------------------------------------------------------------------
# zhs login
# ---------------------------------------------------------------------------


@app.command()
def login(
    show_in_terminal: bool = typer.Option(False, "--show-in-terminal", help="终端显示二维码"),  # noqa: B008
    image_path: str | None = typer.Option(None, "--image-path", help="二维码保存路径"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """扫码登录智慧树"""
    from zhs.login import LoginManager
    from zhs.utils.display import msg_done, msg_info, msg_warn

    config_mgr = ConfigManager()
    config = config_mgr.load()

    if image_path:
        config.qr.image_path = image_path
    if not config.qr.image_path:
        from zhs.utils.path import get_data_dir

        config.qr.image_path = str(get_data_dir() / "qrcode.png")
    if proxy:
        _parse_proxy(config, proxy)

    _setup_logger(config, debug, console_log)

    session = ZhsSession(config)
    login_mgr = LoginManager(session, config)

    print(msg_info("请使用智慧树 APP 扫描二维码登录"))
    print(msg_warn(f"二维码已保存到: {config.qr.image_path}"))
    _do_login(login_mgr, config, show_in_terminal)
    print(msg_done("登录成功！Cookie 已保存，现在可以运行 zhs play 刷课了"))


# ---------------------------------------------------------------------------
# zhs play
# ---------------------------------------------------------------------------


@app.command()
def play(
    course: list[str] | None = typer.Option(None, "-c", "--course", help="课程 ID"),  # noqa: B008
    course_type: str | None = typer.Option(None, "--type", help="课程类型: zhidao/hike/ai/auto"),  # noqa: B008
    ai_course: int | None = typer.Option(None, "--ai-course", help="AI 课程 courseId"),  # noqa: B008
    ai_class: int | None = typer.Option(None, "--ai-class", help="AI 课程 classId"),  # noqa: B008
    speed: float | None = typer.Option(None, "-s", "--speed", help="播放速度"),  # noqa: B008
    limit: int = typer.Option(0, "-l", "--limit", help="每门课程时间限制(分钟)", min=0),  # noqa: B008
    learn_optional: bool = typer.Option(False, "--learn-optional", help="AI 课程学习选学资源"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """刷视频"""
    result = _load_config_and_session(debug, console_log, proxy)
    if result is None:
        raise typer.Exit(1)
    config, session = result

    # 校验 --type
    validated_type = _validate_course_type(course_type)
    if course_type is not None and validated_type is None:
        # 无效的 --type，不继续运行
        raise typer.Exit(1)

    # CLI 参数覆盖配置
    if speed is not None:
        config.video.zhidao_speed = speed
        config.video.hike_speed = speed
        config.video.ai_speed = speed
    if limit:
        config.limit = limit
    if learn_optional:
        config.video.ai_learn_optional = True

    # AI 课程走 --ai-course + --ai-class
    if ai_course is not None and ai_class is not None:
        _run_ai(session, config, ai_course, ai_class)
    elif course:
        _run_courses(session, config, course, validated_type)
    else:
        _run_all(session, config, validated_type)


# ---------------------------------------------------------------------------
# zhs homework
# ---------------------------------------------------------------------------


@app.command()
def homework(
    course: list[str] | None = typer.Option(None, "-c", "--course", help="课程 ID"),  # noqa: B008
    course_type: str | None = typer.Option(None, "--type", help="课程类型: zhidao/ai/auto"),  # noqa: B008
    url: str | None = typer.Option(None, "--url", help="作业 URL（从浏览器复制）"),  # noqa: B008
    ai_course: int | None = typer.Option(None, "--ai-course", help="AI 课程 courseId"),  # noqa: B008
    ai_class: int | None = typer.Option(None, "--ai-class", help="AI 课程 classId"),  # noqa: B008
    no_ai: bool = typer.Option(False, "--no-ai", help="不使用 AI 模型（随机生成）"),  # noqa: B008
    homework_threshold: int | None = typer.Option(None, "--homework-threshold", help="满分阈值百分比(0-100)"),  # noqa: B008
    max_submit: int | None = typer.Option(None, "--max-submit", help="最大提交次数"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """写作业"""
    result = _load_config_and_session(debug, console_log, proxy)
    if result is None:
        raise typer.Exit(1)
    config, session = result

    # 校验 --type
    validated_type = _validate_course_type(course_type)
    if course_type is not None and validated_type is None:
        raise typer.Exit(1)

    # CLI 参数覆盖配置
    if no_ai:
        config.ai.enabled = False
    if homework_threshold is not None:
        config.homework.threshold = homework_threshold
    if max_submit is not None:
        config.homework.max_submit = max_submit

    # --url 模式：直接指定作业
    if url:
        try:
            _run_homework_from_url(session, config, url)
        except Exception as e:
            logger.error(f"URL 作业处理失败: {e}")
            print(f"URL 作业处理失败: {e}")
            raise typer.Exit(1) from e
    # AI 课程走 --ai-course + --ai-class
    elif ai_course is not None and ai_class is not None:
        try:
            _run_ai_homework(session, config, ai_course, ai_class)
        except Exception as e:
            logger.error(f"AI 课程 {ai_course} 作业处理失败: {e}")
            print(f"AI 课程 {ai_course} 作业处理失败: {e}")
    elif course:
        for c in course:
            detected_type = _detect_course_type(c, validated_type)
            try:
                if detected_type == "ai":
                    _run_ai_homework_by_str(session, config, c)
                elif detected_type == "zhidao":
                    _run_zhidao_homework_by_course(session, config, c)
                else:
                    logger.warning(f"暂不支持 {detected_type} 课程的作业功能")
                    print(f"暂不支持 {detected_type} 课程的作业功能")
            except Exception as e:
                logger.error(f"课程 {c} 作业处理失败: {e}")
                print(f"课程 {c} 作业处理失败: {e}")
    else:
        _run_all_homework(session, config, validated_type)


# ---------------------------------------------------------------------------
# zhs exam
# ---------------------------------------------------------------------------


@app.command()
def exam(
    course: list[str] | None = typer.Option(None, "-c", "--course", help="课程 ID"),  # noqa: B008
    course_type: str | None = typer.Option(None, "--type", help="课程类型: zhidao/ai/auto"),  # noqa: B008
    ai_course: int | None = typer.Option(None, "--ai-course", help="AI 课程 courseId"),  # noqa: B008
    ai_class: int | None = typer.Option(None, "--ai-class", help="AI 课程 classId"),  # noqa: B008
    submit: bool = typer.Option(False, "--submit", help="答题后提交考试（默认不提交）"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """AI 课程考试"""
    result = _load_config_and_session(debug, console_log, proxy)
    if result is None:
        raise typer.Exit(1)
    config, session = result

    from zhs.utils.display import msg_warn

    if course_type != "ai" and not ai_course:
        print(msg_warn("目前仅支持 AI 课程考试，请使用 --type ai 或 --ai-course 指定"))
        raise typer.Exit(1)

    _run_ai_exam(session, config, ai_course, ai_class, submit)


# ---------------------------------------------------------------------------
# zhs fetch
# ---------------------------------------------------------------------------


@app.command()
def fetch(
    fetch_type: str = typer.Option("all", "--type", help="数据类型: all/course/homework"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """获取课程数据"""
    result = _load_config_and_session(debug, console_log, proxy)
    if result is None:
        raise typer.Exit(1)
    config, session = result

    _fetch_course_list(session, fetch_type)


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


VALID_COURSE_TYPES = ("zhidao", "hike", "ai", "auto")


def _validate_course_type(course_type: str | None) -> str | None:
    """校验 --type 参数，无效值打印错误并返回 None"""
    if course_type is None:
        return None
    if course_type not in VALID_COURSE_TYPES:
        from zhs.utils.display import msg_error

        print(msg_error(f"不支持的课程类型: {course_type}，可选值: {', '.join(VALID_COURSE_TYPES)}"))
        return None
    return course_type


def _detect_course_type(course_id: str, course_type: str | None = None) -> str:
    """检测课程类型

    - 显式 type 优先
    - 含字母 → zhidao
    - 纯数字 → hike
    """
    import re

    if course_type:
        return course_type
    if re.search(r"[a-zA-Z]", course_id):
        return "zhidao"
    return "hike"


def _run_courses(
    session: ZhsSession,
    config: AppConfig,
    courses: list[str],
    course_type: str | None,
) -> None:
    """按课程列表刷课"""
    for c in courses:
        detected_type = _detect_course_type(c, course_type)
        try:
            if detected_type == "zhidao":
                _run_zhidao(session, config, c)
            elif detected_type == "hike":
                _run_hike(session, config, c)
            elif detected_type == "ai":
                _run_ai_by_str(session, config, c)
            else:
                print(f"未知的课程类型: {detected_type}，跳过课程 {c}")
        except Exception as e:
            logger.error(f"课程 {c} 处理失败: {e}")
            print(f"课程 {c} 处理失败: {e}")


def _run_ai(session: ZhsSession, config: AppConfig, course_id: int, class_id: int) -> None:
    """刷 AI 课程（仅视频/知识点，不做作业）"""
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
    )


def _run_ai_by_str(session: ZhsSession, config: AppConfig, course_id_str: str) -> None:
    """刷 AI 课程（字符串格式 courseId:classId）"""
    parts = course_id_str.split(":")
    if len(parts) != 2:
        logger.error(f"AI 课程 ID 格式错误，应为 courseId:classId，实际: {course_id_str}")
        return
    try:
        course_id = int(parts[0])
        class_id = int(parts[1])
    except ValueError:
        logger.error(f"AI 课程 ID 格式错误，courseId/classId 必须为整数: {course_id_str}")
        return

    _run_ai(session, config, course_id, class_id)


def _run_zhidao(session: ZhsSession, config: AppConfig, course_id: str) -> None:
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

    ctx = mgr.get_context(course_id)
    player.play_course(course_id, ctx)


def _run_hike(session: ZhsSession, config: AppConfig, course_id: str) -> None:
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


def _run_all(session: ZhsSession, config: AppConfig, course_type: str | None = None) -> None:
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


def _run_ai_homework(session: ZhsSession, config: AppConfig, course_id: int, class_id: int) -> None:
    """AI 课程作业（仅做作业，不刷视频）"""
    from zhs.ai.course import AiCourseManager

    mgr = AiCourseManager(session)
    mgr.run_course(course_id, class_id, config.ai, config.homework, speed=config.video.ai_speed)


def _run_ai_exam(
    session: ZhsSession,
    config: AppConfig,
    ai_course: int | None,
    ai_class: int | None,
    submit: bool = False,
) -> None:
    """AI 课程考试

    流程：
    1. 获取 AI 课程列表（或使用指定的 courseId/classId）
    2. 对每门课程调用 taskList 获取未完成考试
    3. 对每个考试创建 ExamCtx 执行答题
    4. 若 submit=True，提交后通过 openExamDetail 判断是否可查看答案，可查看则保存缓存
    """
    from zhs.ai.course import AiCourseManager
    from zhs.ai.exam import ExamCtx
    from zhs.utils.display import course_tag, msg_done, msg_info, msg_warn

    mgr = AiCourseManager(session)

    # 获取课程列表
    if ai_course and ai_class:
        courses = [{"courseId": str(ai_course), "classId": str(ai_class), "courseName": ""}]
    else:
        courses = mgr.get_ai_course_list()

    print(f"\n{course_tag('ai')} 发现 {len(courses)} 门课程")

    total_exams = 0
    for ac in courses:
        course_id = str(ac.get("courseId", ""))
        class_id = str(ac.get("classId", ""))
        course_name = ac.get("courseName", "")
        if not course_id:
            logger.warning(f"AI 课程 {course_name} 缺少 courseId")
            continue

        try:
            # 获取未完成考试任务列表
            tasks = mgr.get_exam_tasks(course_id)
            if not tasks:
                print(f"  {course_name}: 无未完成考试")
                continue

            print(f"  {course_name}: 发现 {len(tasks)} 个未完成考试")
            for task in tasks:
                exam_test_id = str(task.get("examTestId", ""))
                exam_paper_id = str(task.get("examPaperId", ""))
                task_name = task.get("taskName", "")
                task_id = str(task.get("id", ""))
                student_id = int(task.get("userId", 0))
                if not exam_test_id or not exam_paper_id:
                    logger.warning(f"考试任务 {task_name} 缺少 examTestId 或 examPaperId")
                    continue

                submit_tag = " (提交)" if submit else " (不提交)"
                print(f"    开始考试: {task_name} (examTestId={exam_test_id}){submit_tag}")
                try:
                    ctx = ExamCtx(
                        session=session,
                        course_id=course_id,
                        class_id=class_id,
                        exam_test_id=exam_test_id,
                        exam_paper_id=exam_paper_id,
                        ai_config=config.ai,
                        exam_config=config.exam,
                        op_extra={"courseName": course_name},
                        student_id=student_id,
                        task_id=task_id,
                    )
                    all_correct, correct, total = ctx.start(submit=submit)
                    if submit:
                        if all_correct:
                            print(f"    {msg_done(f'考试完成: {correct}/{total} 全对')}")
                        elif correct == 0:
                            print(f"    {msg_info('考试已提交，无法查看答案')}")
                        else:
                            print(f"    {msg_warn(f'考试完成: {correct}/{total} 正确')}")
                    else:
                        print(f"    {msg_info(f'答题完成（未提交）: {total} 题，可以使用--submit提交')}")
                    total_exams += 1
                except Exception as e:
                    logger.error(f"考试 {task_name} 处理失败: {e}")
                    print(f"    考试 {task_name} 处理失败: {e}")
        except Exception as e:
            logger.error(f"AI 课程 {course_name} 考试处理失败: {e}")
            print(f"  AI 课程 {course_name} 考试处理失败: {e}")

    print(f"\n共完成 {total_exams} 个考试")


def _run_ai_homework_by_str(session: ZhsSession, config: AppConfig, course_id_str: str) -> None:
    """AI 课程作业（字符串格式 courseId:classId）"""
    parts = course_id_str.split(":")
    if len(parts) != 2:
        logger.error(f"AI 课程 ID 格式错误，应为 courseId:classId，实际: {course_id_str}")
        return
    try:
        course_id = int(parts[0])
        class_id = int(parts[1])
    except ValueError:
        logger.error(f"AI 课程 ID 格式错误，courseId/classId 必须为整数: {course_id_str}")
        return

    _run_ai_homework(session, config, course_id, class_id)


def _run_all_homework(session: ZhsSession, config: AppConfig, course_type: str | None) -> None:
    """全刷作业模式"""
    from zhs.ai.course import AiCourseManager
    from zhs.utils.display import course_tag

    # 知到课程作业
    if course_type in (None, "auto", "zhidao"):
        try:
            _run_all_zhidao_homework(session, config)
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


def _parse_homework_url(url: str) -> dict[str, str]:
    """解析作业 URL

    URL 格式:
    https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/{recruitId}/{stuExamId}/{examId}/{courseId}/{schoolId}/0

    注意: URL 中参数顺序是 stuExamId 在前，examId 在后，与 HomeworkItem 字段名相反。

    Returns:
        包含 recruit_id, exam_id, stu_exam_id, course_id, school_id 的字典
    """
    import re

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


def _init_llm(config: AppConfig) -> LLMProvider | None:
    """初始化 LLM 提供者"""
    from zhs.llm.openai import OpenAIProvider

    ai = config.ai
    if not ai.enabled:
        return None
    if ai.use_zhidao_ai:
        return None
    if not ai.api_key:
        logger.warning("API key 为空，LLM 不可用，将使用随机答题")
        return None
    return OpenAIProvider(
        api_key=ai.api_key,
        base_url=ai.base_url,
        model_name=ai.model,
        max_token=ai.max_token,
    )


def _run_homework_from_url(session: ZhsSession, config: AppConfig, url: str) -> None:
    """从 URL 运行作业"""
    from zhs.utils.display import course_tag, msg_done, msg_warn, tree_print

    params = _parse_homework_url(url)
    logger.info(
        f"解析 URL: recruitId={params['recruit_id']}, examId={params['exam_id']}, "
        f"stuExamId={params['stu_exam_id']}, courseId={params['course_id']}, schoolId={params['school_id']}"
    )

    # CAS SSO
    session.exam_sso_login()

    # 扫描该课程的所有作业
    from zhs.zhidao.homework.cache import HomeworkCache
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

    llm = _init_llm(config)
    cache = HomeworkCache()
    worker = HomeworkWorker(session, config, cache, llm=llm)
    score_rate = worker.run_homework(target, params["recruit_id"], params["school_id"])

    if score_rate >= config.homework.threshold:
        tree_print(msg_done(f"达标: {target.exam_name} {score_rate:.1f}%"), depth=1, enabled=True)
    else:
        tree_print(msg_warn(f"未达标: {target.exam_name} {score_rate:.1f}%"), depth=1, enabled=True)


def _run_zhidao_homework_by_course(session: ZhsSession, config: AppConfig, course_id: str) -> None:
    """按课程 ID 运行知到作业"""
    from zhs.zhidao.course import ZhidaoCourseManager

    # CAS SSO
    session.exam_sso_login()

    # 获取 recruit_id
    mgr = ZhidaoCourseManager(session)
    courses = mgr.get_course_list()
    recruit_id = None
    for c in courses:
        if c.secret == course_id and c.recruit_id:
            recruit_id = str(c.recruit_id)
            break

    if not recruit_id:
        logger.error(f"未找到课程 {course_id} 的 recruitId")
        print(f"未找到课程 {course_id} 的 recruitId")
        return

    _run_zhidao_homework(session, config, recruit_id, int(course_id) if course_id.isdigit() else 0)


def _run_zhidao_homework(
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
    from zhs.utils.display import course_tag, msg_done, msg_error, msg_skip, msg_warn, tree_print
    from zhs.zhidao.homework.cache import HomeworkCache
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

    llm = _init_llm(config)
    cache = HomeworkCache()
    worker = HomeworkWorker(session, config, cache, llm=llm)

    for item in pending:
        try:
            logger.info(f"开始做作业: {item.exam_name} (state={item.state}, score={item.score})")
            score_rate = worker.run_homework(item, recruit_id, "625")
            if score_rate >= config.homework.threshold:
                tree_print(msg_done(f"完成: {item.exam_name} {score_rate:.1f}%"), depth=depth + 2, enabled=True)
            else:
                tree_print(msg_warn(f"未达标: {item.exam_name} {score_rate:.1f}%"), depth=depth + 2, enabled=True)
        except Exception as e:
            logger.error(f"作业 {item.exam_name} 处理失败: {e}")
            tree_print(msg_error(f"失败: {item.exam_name} {e}"), depth=depth + 2, enabled=True)


def _run_all_zhidao_homework(session: ZhsSession, config: AppConfig) -> None:
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
            _run_zhidao_homework(session, config, recruit_id, course_id, depth=1)
        except Exception as e:
            logger.error(f"知到课程 {c.course_name} 作业处理失败: {e}")
            tree_print(msg_error(f"课程失败: {c.course_name} {e}"), depth=1, enabled=True)


def _fetch_course_list(session: ZhsSession, fetch_type: str = "all") -> None:
    """获取课程列表"""
    import json

    from zhs.ai.course import AiCourseManager
    from zhs.hike.course import HikeCourseManager
    from zhs.utils.display import course_tag
    from zhs.utils.path import get_data_dir
    from zhs.zhidao.course import ZhidaoCourseManager

    zhidao_ids: list[dict[str, str]] = []
    hike_ids: list[dict[str, str]] = []
    ai_ids: list[dict[str, Any]] = []

    if fetch_type in ("all", "course"):
        zhidao_mgr = ZhidaoCourseManager(session)
        hike_mgr = HikeCourseManager(session)
        ai_mgr = AiCourseManager(session)

        zhidao_ids = [{"name": c.course_name, "id": c.secret} for c in zhidao_mgr.get_course_list()]
        hike_ids = [{"name": c.course_name, "id": str(c.course_id)} for c in hike_mgr.get_course_list()]
        ai_ids = [
            {"name": c.get("courseName", ""), "courseId": c.get("courseId"), "classId": c.get("classId")}
            for c in ai_mgr.get_ai_course_list()
        ]

        print(f"{course_tag('zhidao')} {len(zhidao_ids)} 门课程")
        for c in zhidao_ids:
            print(f"  {c['name']} ({c['id']})")
        print(f"{course_tag('hike')} {len(hike_ids)} 门课程")
        for c in hike_ids:
            print(f"  {c['name']} ({c['id']})")
        print(f"{course_tag('ai')} {len(ai_ids)} 门课程")
        for c in ai_ids:
            print(f"  {c['name']} (courseId={c['courseId']}, classId={c['classId']})")

    exec_path = get_data_dir() / "execution.json"
    data = {"zhidao": zhidao_ids, "hike": hike_ids, "ai": ai_ids}
    with open(exec_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    logger.info(f"课程列表已保存到 {exec_path}")


if __name__ == "__main__":
    app()

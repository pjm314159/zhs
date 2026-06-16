"""ZHS CLI 入口

智慧树自动刷课工具，支持知到/Hike/AI 课程。

用法:
  zhs login              扫码登录
  zhs -c COURSE_ID       刷指定课程
  zhs -f                 获取课程列表
  zhs                    全刷模式
"""

import re
import sys

import typer
from loguru import logger

from zhs.config import AppConfig, ConfigManager
from zhs.login import LoginManager
from zhs.session import ZhsSession
from zhs.utils import display

app = typer.Typer(name="zhs", help="智慧树自动刷课工具")


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


# ---------------------------------------------------------------------------
# login 子命令
# ---------------------------------------------------------------------------


@app.command()
def login(  # noqa: B008
    show_in_terminal: bool = typer.Option(False, help="终端显示二维码"),  # noqa: B008
    image_path: str | None = typer.Option(None, "--image-path", help="二维码保存路径"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """扫码登录智慧树"""
    from zhs.utils.display import msg_done, msg_info, msg_warn

    config_mgr = ConfigManager()
    config = config_mgr.load()

    if image_path:
        config.image_path = image_path
    if not config.image_path:
        from zhs.utils.path import get_data_dir

        config.image_path = str(get_data_dir() / "qrcode.png")
    if proxy:
        _parse_proxy(config, proxy)

    _setup_logger(config, debug, console_log)

    session = ZhsSession(config)
    login_mgr = LoginManager(session, config)

    print(msg_info("请使用智慧树 APP 扫描二维码登录"))
    print(msg_warn(f"二维码已保存到: {config.image_path}"))
    _do_login(login_mgr, config, show_in_terminal)
    print(msg_done("登录成功！Cookie 已保存，现在可以运行 zhs 刷课了"))


# ---------------------------------------------------------------------------
# 主命令（刷课）
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(  # noqa: B008
    ctx: typer.Context,  # noqa: B008
    course: list[str] | None = typer.Option(None, "-c", "--course", help="课程 ID"),  # noqa: B008
    course_type: str | None = typer.Option(None, "--type", help="课程类型: zhidao/hike/ai"),  # noqa: B008
    videos: list[str] | None = typer.Option(None, "-v", "--videos", help="视频 ID"),  # noqa: B008
    speed: float | None = typer.Option(None, "-s", "--speed", help="播放速度"),  # noqa: B008
    threshold: float | None = typer.Option(None, "-t", "--threshold", help="完成阈值"),  # noqa: B008
    limit: int = typer.Option(0, "-l", "--limit", help="每门课程时间限制(分钟)"),  # noqa: B008
    fetch: bool = typer.Option(False, "-f", "--fetch", help="获取课程列表"),  # noqa: B008
    debug: bool = typer.Option(False, "-d", "--debug", help="调试模式"),  # noqa: B008
    proxy: str | None = typer.Option(None, "--proxy", help="代理"),  # noqa: B008
    tree_view: bool | None = typer.Option(None, help="树形视图"),  # noqa: B008
    progressbar_view: bool | None = typer.Option(None, help="进度条"),  # noqa: B008
    ai_course: int | None = typer.Option(None, "--ai-course", help="AI 课程 ID"),  # noqa: B008
    ai_class: int | None = typer.Option(None, "--ai-class", help="AI 班级 ID"),  # noqa: B008
    noexam: bool = typer.Option(False, "--noexam", help="禁用考试"),  # noqa: B008
    no_ai_exam: bool = typer.Option(False, "--no-ai-exam", help="禁用 AI 答题（使用随机兜底）"),  # noqa: B008
    console_log: bool = typer.Option(False, "--console-log", help="日志输出到控制台"),  # noqa: B008
) -> None:
    """智慧树自动刷课工具"""
    # 子命令（如 login）在执行时，跳过主命令逻辑
    if ctx.invoked_subcommand is not None:
        return
    config_mgr = ConfigManager()
    config = config_mgr.load()

    # CLI 参数覆盖配置
    if speed is not None:
        config.zhidao_speed = speed
        config.hike_speed = speed
    if threshold is not None:
        config.threshold = threshold
    if limit:
        config.limit = limit
    if tree_view is not None:
        config.tree_view = tree_view
    if progressbar_view is not None:
        config.progressbar_view = progressbar_view
    if proxy:
        _parse_proxy(config, proxy)

    _setup_logger(config, debug, console_log)

    # 创建 session
    session = ZhsSession(config)

    # 尝试恢复 cookies（不自动登录）
    if not _try_restore_cookies(session, config):
        from zhs.utils.display import msg_error

        print(msg_error("未登录或 Cookie 已过期，请先运行 zhs login 登录"))
        raise typer.Exit(1)

    # AI 课程分支
    if ai_course is not None and ai_class is not None:
        _run_ai_course(session, config, ai_course, ai_class, noexam, no_ai_exam)
        return
    elif ai_course is not None or ai_class is not None:
        print(display.msg_error("AI 课程需要同时提供 --ai-course 和 --ai-class"))
        raise typer.Exit(1)

    # fetch 模式
    if fetch:
        _fetch_course_list(session)
        return

    # 刷课
    if course:
        _run_courses(session, config, course, course_type, videos)
    else:
        _run_all(session, config)


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _setup_logger(config: AppConfig, debug: bool, console_log: bool) -> None:
    """配置日志"""
    log_level = "DEBUG" if debug else config.log_level
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
    if console_log:
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
    if schema in ("http", "https"):
        config.proxies["http"] = proxy
        config.proxies["https"] = proxy
    elif schema == "socks5":
        config.proxies["socks5"] = proxy
    elif schema == "all":
        config.proxies["http"] = proxy
        config.proxies["https"] = proxy
        config.proxies["socks5"] = proxy
    else:
        logger.error(f"不支持的代理类型: {schema}")


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

    result = login_mgr.login_with_qr(qr_callback, image_path=config.image_path)
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


def _run_ai_course(
    session: ZhsSession, config: AppConfig, course_id: int, class_id: int, noexam: bool, no_ai_exam: bool
) -> None:
    """执行 AI 课程"""
    from zhs.ai.course import AiCourseManager

    # --no-ai-exam 禁用 AI 答题，但仍允许随机兜底
    if no_ai_exam:
        config.ai.enabled = False

    mgr = AiCourseManager(session)
    mgr.run_course(course_id, class_id, config.ai, no_exam=noexam, speed=config.ai_speed)


def _fetch_course_list(session: ZhsSession) -> None:
    """获取课程列表"""
    import json

    from zhs.ai.course import AiCourseManager
    from zhs.hike.course import HikeCourseManager
    from zhs.utils.display import course_tag
    from zhs.utils.path import get_data_dir
    from zhs.zhidao.course import ZhidaoCourseManager

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


def _run_courses(
    session: ZhsSession,
    config: AppConfig,
    courses: list[str],
    course_type: str | None,
    videos: list[str] | None,
) -> None:
    """按课程列表刷课"""
    for c in courses:
        detected_type = detect_course_type(c, course_type)
        try:
            if detected_type == "zhidao":
                _run_zhidao(session, config, c, videos)
            elif detected_type == "hike":
                _run_hike(session, config, c, videos)
            elif detected_type == "ai":
                _run_ai_by_id(session, config, c)
        except Exception as e:
            logger.error(f"课程 {c} 处理失败: {e}")


def _run_ai_by_id(session: ZhsSession, config: AppConfig, course_id_str: str) -> None:
    """通过 courseId:classId 格式刷 AI 课程"""
    from zhs.ai.course import AiCourseManager

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

    mgr = AiCourseManager(session)
    mgr.run_course(course_id, class_id, config.ai, speed=config.ai_speed)


def _run_zhidao(session: ZhsSession, config: AppConfig, course_id: str, videos: list[str] | None) -> None:
    """刷知到课程"""
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.video import ZhidaoVideoPlayer

    mgr = ZhidaoCourseManager(session)
    player = ZhidaoVideoPlayer(
        session,
        speed=config.zhidao_speed,
        end_threshold=config.threshold,
        time_limit=config.limit * 60,
        progressbar_view=config.progressbar_view,
        tree_view=config.tree_view,
    )

    if videos:
        ctx = mgr.get_context(course_id)
        for v in videos:
            try:
                player.play_video(course_id, int(v), ctx)
            except Exception as e:
                logger.error(f"视频 {v} 处理失败: {e}")
    else:
        ctx = mgr.get_context(course_id)
        player.play_course(course_id, ctx)


def _run_hike(session: ZhsSession, config: AppConfig, course_id: str, videos: list[str] | None) -> None:
    """刷 Hike 课程"""
    from zhs.hike.course import HikeCourseManager
    from zhs.hike.video import HikeVideoPlayer

    mgr = HikeCourseManager(session)
    player = HikeVideoPlayer(
        session,
        speed=config.hike_speed,
        end_threshold=config.threshold,
        time_limit=config.limit * 60,
        progressbar_view=config.progressbar_view,
        tree_view=config.tree_view,
    )

    if videos:
        for v in videos:
            try:
                player.play_video(course_id, int(v))
            except Exception as e:
                logger.error(f"视频 {v} 处理失败: {e}")
    else:
        root = mgr.get_context(course_id)
        player.play_course(course_id, root)


def _run_all(session: ZhsSession, config: AppConfig) -> None:
    """全刷模式：先刷知到再刷 Hike 再刷 AI"""
    from zhs.ai.course import AiCourseManager
    from zhs.hike.course import HikeCourseManager
    from zhs.hike.video import HikeVideoPlayer
    from zhs.utils.display import course_tag
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.video import ZhidaoVideoPlayer

    # 知到
    try:
        zhidao_mgr = ZhidaoCourseManager(session)
        zhidao_player = ZhidaoVideoPlayer(
            session,
            speed=config.zhidao_speed,
            end_threshold=config.threshold,
            time_limit=config.limit * 60,
            progressbar_view=config.progressbar_view,
            tree_view=config.tree_view,
        )
        courses = zhidao_mgr.get_course_list()
        print(f"\n{course_tag('zhidao')} 发现 {len(courses)} 门课程")
        for c in courses:
            try:
                ctx = zhidao_mgr.get_context(c.secret)
                zhidao_player.play_course(c.secret, ctx)
            except Exception as e:
                logger.error(f"知到课程 {c.course_name} 处理失败: {e}")
    except Exception as e:
        logger.error(f"获取知到课程列表失败: {e}")

    # Hike
    try:
        hike_mgr = HikeCourseManager(session)
        hike_player = HikeVideoPlayer(
            session,
            speed=config.hike_speed,
            end_threshold=config.threshold,
            time_limit=config.limit * 60,
            progressbar_view=config.progressbar_view,
            tree_view=config.tree_view,
        )
        hike_courses = hike_mgr.get_course_list()
        print(f"\n{course_tag('hike')} 发现 {len(hike_courses)} 门课程")
        for hc in hike_courses:
            try:
                root = hike_mgr.get_context(str(hc.course_id))
                hike_player.play_course(str(hc.course_id), root)
            except Exception as e:
                logger.error(f"Hike 课程 {hc.course_name} 处理失败: {e}")
    except Exception as e:
        logger.error(f"获取 Hike 课程列表失败: {e}")

    # AI
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
                    ai_mgr.run_course(int(course_id), int(class_id), config.ai, speed=config.ai_speed)
                else:
                    logger.warning(f"AI 课程 {course_name} 缺少 courseId 或 classId")
            except Exception as e:
                logger.error(f"AI 课程 {ac.get('courseName', '')} 处理失败: {e}")
    except Exception as e:
        logger.error(f"获取 AI 课程列表失败: {e}")


if __name__ == "__main__":
    app()

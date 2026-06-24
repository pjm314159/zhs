"""ZHS CLI 入口

智慧树自动刷课工具，支持知到/Hike/AI 课程。

用法:
  zhs init                初始化配置
  zhs login               扫码登录
  zhs play                刷视频
  zhs exam                考试
  zhs homework            写作业
  zhs fetch               获取课程列表

本模块仅保留 typer 命令声明与参数解析，业务逻辑全部委托给 zhs.cli 子包。
为兼容现有测试（tests/cli/test_main.py 通过 patch("zhs.__main__._run_*") 注入 mock），
所有从 cli 子包导入的函数均以带下划线前缀的别名暴露在模块命名空间。
"""

import typer
from loguru import logger

from zhs.cli.bootstrap import do_login as _do_login
from zhs.cli.bootstrap import load_config_and_session as _load_config_and_session
from zhs.cli.bootstrap import parse_proxy as _parse_proxy
from zhs.cli.bootstrap import setup_logger as _setup_logger
from zhs.cli.bootstrap import try_restore_cookies as _try_restore_cookies  # noqa: F401
from zhs.cli.course_type import detect_course_type as _detect_course_type
from zhs.cli.course_type import validate_course_type as _validate_course_type
from zhs.cli.services.exam_service import run_ai_exam as _run_ai_exam
from zhs.cli.services.fetch_service import fetch_course_list as _fetch_course_list
from zhs.cli.services.homework_service import run_ai_homework as _run_ai_homework
from zhs.cli.services.homework_service import run_ai_homework_by_str as _run_ai_homework_by_str
from zhs.cli.services.homework_service import run_all_homework as _run_all_homework
from zhs.cli.services.homework_service import run_homework_from_url as _run_homework_from_url
from zhs.cli.services.homework_service import run_zhidao_homework_by_course as _run_zhidao_homework_by_course
from zhs.cli.services.play_service import run_ai as _run_ai
from zhs.cli.services.play_service import run_ai_by_str as _run_ai_by_str
from zhs.cli.services.play_service import run_all as _run_all
from zhs.cli.services.play_service import run_hike as _run_hike
from zhs.cli.services.play_service import run_zhidao as _run_zhidao
from zhs.config import AppConfig, ConfigManager
from zhs.exceptions import SliderVerificationRequired
from zhs.login import LoginManager
from zhs.session import ZhsSession

# 显式导出供 tests/cli/test_main.py 导入的别名
__all__ = [
    "_detect_course_type",
    "_validate_course_type",
    "app",
]

app = typer.Typer(name="zhs", help="智慧树自动刷课工具", no_args_is_help=True)


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
        # 内联路由循环，确保 _run_zhidao/_run_hike/_run_ai_by_str 从 __main__ 命名空间查找
        # （兼容 tests/cli/test_main.py 中 @patch("zhs.__main__._run_*") 的注入）
        for c in course:
            detected_type = _detect_course_type(c, validated_type)
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
            except SliderVerificationRequired:
                # 滑块验证：服务端状态，后续课程也会失败，立即停止
                raise
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


if __name__ == "__main__":
    app()

"""CLI 基础设施：日志、代理、配置加载、Cookie 恢复、登录

从原 __main__.py 抽离的非业务逻辑：
- setup_logger: 配置 loguru
- parse_proxy: 解析代理字符串
- load_config_and_session: 加载配置 + 创建 session + 恢复 cookies
- try_restore_cookies: 从本地文件恢复 cookies
- do_login: 执行扫码登录
"""

import json
import sys
from typing import Any

import typer
from loguru import logger

from zhs.config import AppConfig, ConfigManager
from zhs.session import ZhsSession


def setup_logger(config: AppConfig, debug: bool, console_log: bool) -> None:
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


def parse_proxy(config: AppConfig, proxy: str) -> None:
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


def load_config_and_session(debug: bool, console_log: bool, proxy: str | None) -> tuple[AppConfig, ZhsSession] | None:
    """加载配置、创建 session、恢复 cookies。失败返回 None。"""
    config_mgr = ConfigManager()
    config = config_mgr.load()

    if proxy:
        parse_proxy(config, proxy)

    setup_logger(config, debug, console_log)

    session = ZhsSession(config)

    if not try_restore_cookies(session, config):
        from zhs.utils.display import msg_error

        print(msg_error("未登录或 Cookie 已过期，请先运行 zhs login 登录"))
        return None

    return config, session


def try_restore_cookies(session: ZhsSession, config: AppConfig) -> bool:
    """尝试恢复 cookies，成功返回 True"""
    if not config.save_cookies:
        return False

    from zhs.utils.cookie import list_to_cookies
    from zhs.utils.path import get_data_dir

    cookies_path = get_data_dir() / "cookies.json"
    if not cookies_path.exists():
        return False

    try:
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


def do_login(
    login_mgr: Any,
    config: AppConfig,
    show_in_terminal: bool,
) -> None:
    """执行扫码登录

    Args:
        login_mgr: LoginManager 实例
        config: 应用配置
        show_in_terminal: 是否在终端显示二维码
    """
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
        from zhs.utils.cookie import cookies_to_list
        from zhs.utils.path import get_data_dir

        cookies_path = get_data_dir() / "cookies.json"
        with open(cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies_to_list(result.cookies), f, indent=2, ensure_ascii=False)
        logger.info(f"Cookie 已保存到 {cookies_path}")


def init_llm(config: AppConfig) -> Any:
    """初始化 LLM 提供者

    Returns:
        LLMProvider | None
    """
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


__all__ = [
    "do_login",
    "init_llm",
    "load_config_and_session",
    "parse_proxy",
    "setup_logger",
    "try_restore_cookies",
]

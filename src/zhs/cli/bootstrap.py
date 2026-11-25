"""CLI 基础设施：日志、代理、配置加载、Cookie 恢复、会话校验、登录

从原 __main__.py 抽离的非业务逻辑：
- setup_logger: 配置 loguru
- parse_proxy: 解析代理字符串
- load_config_and_session: 编排配置加载、Cookie 恢复与会话校验
- try_restore_cookies: 仅从本地文件恢复 cookies（不联网）
- verify_session: 向服务端校验会话是否有效
- do_login: 执行扫码登录
"""

import json
import sys
from typing import Any

import httpx
import typer
from loguru import logger
from pydantic import ValidationError

from zhs.api.session_auth import SessionStatus, verify_session
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


def check_ai_provider(config: AppConfig) -> None:
    """启动时提示 AI 智慧课程实际生效的提供方（仅提示，不改变行为）

    `use_builtin_ai`（默认 true）只作用于 AI 智慧课程：为 true 时使用智慧树内置 AI，
    此时已配置的自定义 api_key 不会被 AI 智慧课程使用（但知到作业/考试仍会用它，
    因为它们没有内置 AI 可用）。
    """
    ai = config.ai
    if ai.enabled and ai.use_builtin_ai and ai.api_key:
        logger.warning(
            "检测到已配置自定义 API Key 但 use_builtin_ai=true，AI 智慧课程将使用智慧树内置 AI；"
            "如需 AI 智慧课程也用自定义模型请设 use_builtin_ai=false"
            "（知到作业/考试没有内置 AI，仍会使用该 API Key）"
        )


def check_captcha_config(config: AppConfig) -> None:
    """验证码配置自检：``enabled=true`` 时 fp 与识图参数必须可用。"""
    cap = config.captcha
    if not cap.enabled:
        return

    from zhs.captcha.fp import normalize_fp, validate_fp_format
    from zhs.exceptions import ZhsError

    problems = validate_fp_format(normalize_fp(cap.fp))
    if problems:
        raise ZhsError(
            "captcha.enabled = true，但 fp 不可用：" + "；".join(problems) + "\n"
            "采集方法：Chrome 打开 https://login.zhihuishu.com/（无需登录），F12 → Console 执行\n"
            "  const raw = document.cookie.match(/(?:^|;\\s*)gdxidpyhxdE=([^;]+)/i)?.[1];\n"
            "  console.log(raw ? decodeURIComponent(raw) : '未找到 gdxidpyhxdE');\n"
            "把输出的整串（约 190 字符，尾段为 :13位时间戳）填入配置 [captcha] fp"
        )

    if not cap.api_key.strip() or not cap.model.strip():
        raise ZhsError("captcha.enabled = true，但 captcha.api_key / captcha.model 未配置；点选需要支持图片输入的模型")


def load_config_and_session(debug: bool, console_log: bool, proxy: str | None) -> tuple[AppConfig, ZhsSession] | None:
    """加载配置、创建 session、恢复 cookies 并校验会话。失败返回 None。"""
    from zhs.exceptions import ZhsError
    from zhs.utils.display import msg_done, msg_error

    config_mgr = ConfigManager()
    try:
        config = config_mgr.load()
    except ValidationError as exc:
        print(msg_error(f"配置错误：{_config_validation_message(exc)}"))
        return None

    if proxy:
        parse_proxy(config, proxy)

    setup_logger(config, debug, console_log)
    check_ai_provider(config)

    try:
        check_captcha_config(config)
    except ZhsError as exc:
        print(msg_error(str(exc)))
        return None

    session = ZhsSession(config)

    has_cookies = try_restore_cookies(session, config)
    if has_cookies:
        status = verify_session(session)
        if status is SessionStatus.UNAVAILABLE:
            print(msg_error("登录状态校验失败：接口不可用，请检查网络后重试"))
            return None
        if status is not SessionStatus.EXPIRED:
            print(msg_done("登录状态有效"))
            return config, session

    if not config.login.auto_login:
        if has_cookies:
            print(msg_error("登录状态已过期，请重新运行 zhs login 登录"))
        else:
            print(msg_error("未登录，请先运行 zhs login 登录"))
        return None

    if not _auto_login(session, config):
        return None

    print(msg_done("登录状态有效"))
    return config, session


def _config_validation_message(exc: ValidationError) -> str:
    """只取校验消息，避免 pydantic 把输入值（可能含密码）带进终端输出"""
    errors = exc.errors()
    if not errors:
        return "配置校验失败"
    return str(errors[0].get("msg", "配置校验失败")).removeprefix("Value error, ")


def _auto_login(session: ZhsSession, config: AppConfig) -> bool:
    """用配置的账号密码自动登录一次（不重试），失败返回 False"""
    from zhs.exceptions import LoginFailed
    from zhs.login import LoginManager, SecretPassword
    from zhs.utils.display import msg_done, msg_error, msg_info

    print(msg_info("登录状态失效，正在使用配置的账号密码自动登录"))
    try:
        result = LoginManager(session, config).login_with_password(
            config.login.account, SecretPassword(config.login.password)
        )
    except LoginFailed as exc:
        print(msg_error(f"自动登录失败：{exc}"))
        return False

    save_login_cookies(config, result.cookies)

    if verify_session(session) is not SessionStatus.OK:
        print(msg_error("自动登录后登录状态校验失败，请手动运行 zhs login"))
        return False

    print(msg_done("自动登录成功"))
    return True


def try_restore_cookies(session: ZhsSession, config: AppConfig) -> bool:
    """仅从本地文件恢复 cookies（不联网、不判定登录态）"""
    if not config.save_cookies:
        return False

    from zhs.utils.cookie import list_to_cookies, read_cookies_file
    from zhs.utils.path import get_data_dir

    raw = read_cookies_file(get_data_dir() / "cookies.json")
    if raw is None:
        return False

    try:
        session.cookies = list_to_cookies(raw)
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"Cookie 恢复失败: {e}")
        return False

    logger.info("Cookie 恢复成功")
    return True


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

    save_login_cookies(config, result.cookies)


def save_login_cookies(config: AppConfig, cookies: httpx.Cookies | None) -> None:
    """保存登录后 cookies 到数据目录（save_cookies=false 或 cookies 为空时跳过）"""
    if not config.save_cookies or not cookies:
        return

    from zhs.utils.cookie import cookies_to_list
    from zhs.utils.path import get_data_dir

    cookies_path = get_data_dir() / "cookies.json"
    with open(cookies_path, "w", encoding="utf-8") as f:
        json.dump(cookies_to_list(cookies), f, indent=2, ensure_ascii=False)
    logger.info(f"Cookie 已保存到 {cookies_path}")


def init_llm(config: AppConfig) -> Any:
    """初始化 LLM 提供者（知到作业/知到考试专用）

    智慧树内置 AI 仅用于 AI 智慧课程（由 LLMProviderFactory 创建 ZhidaoAIProvider），
    知到作业/考试没有内置 AI 可用，只能用自定义 API Key（与 use_builtin_ai 无关）。
    此处仅创建 OpenAI 兼容 provider；无 api_key 则返回 None。

    Returns:
        LLMProvider | None
    """
    from zhs.llm.openai import OpenAIProvider

    ai = config.ai
    if not ai.enabled:
        return None
    if not ai.api_key:
        logger.warning("API key 为空，LLM 不可用，将使用随机答题")
        return None
    return OpenAIProvider(
        api_key=ai.api_key,
        base_url=ai.base_url,
        model_name=ai.model,
        max_token=ai.max_token,
        timeout=ai.stream_timeout,
        idle_timeout=ai.stream_idle_timeout,
    )


def init_question_bank(config: AppConfig, scope: str, llm: Any = None) -> Any:
    """初始化题库查询客户端

    题库依赖 LLM：题库答案仅作为 LLM 答题的提示源，无 LLM 时题库无用。
    若 LLM 未初始化（llm is None）则禁用题库并告警。
    scope 决定当前场景是否在启用范围内（zhidao_homework/zhidao_exam/ai_homework/ai_exam）。

    Args:
        config: 应用配置
        scope: 题库启用范围
        llm: 已初始化的 LLM 实例（None=未初始化）

    Returns:
        QuestionBankClient | None
    """
    from zhs.question_bank.client import QuestionBankClient
    from zhs.utils.display import msg_warn

    qb = config.question_bank
    if not qb.enabled:
        return None
    if not qb.token:
        logger.warning("题库 token 为空，题库不可用")
        print(msg_warn("题库已启用但 token 为空，题库不可用（请在配置中设置 token 或关闭题库功能）"))
        return None
    if llm is None:
        logger.warning("题库功能依赖 LLM，但 LLM 未初始化（请检查 ai.api_key 配置），已禁用题库查询")
        print(msg_warn("题库功能依赖 LLM，但 LLM 未初始化，已禁用题库查询"))
        return None
    if scope not in qb.scopes:
        return None
    return QuestionBankClient(
        token=qb.token,
        query_url=qb.query_url,
        info_url=qb.info_url,
    )


__all__ = [
    "do_login",
    "init_llm",
    "init_question_bank",
    "load_config_and_session",
    "check_captcha_config",
    "parse_proxy",
    "save_login_cookies",
    "setup_logger",
    "try_restore_cookies",
]

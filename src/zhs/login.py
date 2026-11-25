"""ZHS 登录管理模块

提供扫码登录（QR Code）、账户密码登录与 Cookie 持久化功能。
密码登录依赖验证码自动求解（[captcha] enabled=true 且 fp 有效），不重试。
"""

import json
import time
from base64 import b64decode
from collections.abc import Callable
from pathlib import Path

import httpx
from loguru import logger

from zhs.api.passport_login_api import AccountLoginStatus, PassportLoginApi
from zhs.captcha.fp import normalize_fp, validate_fp_format
from zhs.captcha.models import CaptchaSolution
from zhs.captcha.service import CaptchaTrigger
from zhs.config import AppConfig
from zhs.exceptions import LoginFailed
from zhs.session import ZhsSession
from zhs.utils.cookie import cookies_to_list, list_to_cookies, read_cookies_file

LOGIN_REFERER = "https://login.zhihuishu.com/"

STATUS_HINTS: dict[AccountLoginStatus, str] = {
    AccountLoginStatus.SCHOOL_UNVERIFIED: "学校认证未完成，续登失败，请先在网页端完成学校认证",
    AccountLoginStatus.NEED_SECOND_CAPTCHA: "登录需要二次验证码，请改用 zhs login --method qr 扫码登录",
    AccountLoginStatus.WEAK_PASSWORD: "密码过于简单，请先在网页端重置密码",
    AccountLoginStatus.ABNORMAL_LOGIN: "检测到异常登录，请先在网页端完成安全验证",
    AccountLoginStatus.DISABLED: "账号已被禁用",
}


class SecretPassword(str):
    """密码包装：str 子类，repr/str 一律脱敏，避免日志或异常打印明文"""

    def __repr__(self) -> str:
        return "***"

    def __str__(self) -> str:
        return "***"


class LoginResult:
    """登录结果"""

    def __init__(self, success: bool, uuid: str | None = None, cookies: httpx.Cookies | None = None) -> None:
        self.success = success
        self.uuid = uuid
        self.cookies = cookies


def ensure_password_login_ready(config: AppConfig) -> None:
    """密码登录的硬性前置：验证码必须启用且 fp 有效，不满足直接报错"""
    cap = config.captcha
    if not cap.enabled:
        raise LoginFailed(
            "密码登录需要启用验证码自动求解：请设置 [captcha] enabled = true 并配置 fp；"
            "或改用 zhs login --method qr 扫码登录"
        )
    problems = validate_fp_format(normalize_fp(cap.fp))
    if problems:
        raise LoginFailed("密码登录需要有效的验证码设备指纹 fp：" + "；".join(problems))


class LoginManager:
    """登录管理器：扫码登录 + 账户密码登录 + Cookie 持久化"""

    def __init__(self, session: ZhsSession, config: AppConfig) -> None:
        self._session = session
        self._config = config
        self._api = PassportLoginApi(session._http, config.crypto)

    def login_with_qr(
        self,
        qr_callback: Callable[[bytes], None],
        on_scanned: Callable[[], None] | None = None,
        image_path: str = "",
        _max_retries: int = 5,
    ) -> LoginResult:
        """扫码登录

        Args:
            qr_callback: 二维码图片回调（接收 base64 解码后的 bytes）
            on_scanned: 已扫描通知回调（仅调用一次）
            image_path: 二维码图片保存路径，空则保存到默认位置
            _max_retries: 二维码过期最大重试次数

        Returns:
            LoginResult 包含 success/uuid/cookies
        """
        qr_page = f"{self._config.urls.user}/zhsuser/qrCodeLogin/getLoginQrImg"
        query_page = f"{self._config.urls.user}/zhsuser/qrCodeLogin/getLoginQrInfo"
        login_page = f"{self._config.urls.passport}/login"
        gologin_url = f"{self._config.urls.base}/login/gologin"

        try:
            # 先访问登录页获取初始 cookies（服务端需要 session）
            client = self._session._get_client()
            client.get(f"{login_page}?service={gologin_url}")

            # 获取二维码
            resp = self._session.api_query(qr_page, method="GET")
            qr_token: str = resp["qrToken"]
            img_data: str = resp["img"]
            img_bytes = b64decode(img_data)

            # 保存图片
            if image_path:
                Path(image_path).write_bytes(img_bytes)
                logger.info(f"二维码已保存至 {image_path}")

            # 回调显示二维码
            qr_callback(img_bytes)
            logger.debug(f"QR login received, token={qr_token}")

            # 轮询扫码状态
            scanned_notified = False
            poll_count = 0
            while True:
                time.sleep(0.5)
                poll_count += 1
                try:
                    msg = self._session.api_query(query_page, data={"qrToken": qr_token}, method="GET")
                except Exception as exc:
                    logger.warning(f"Poll error (count={poll_count}): {exc}")
                    if poll_count > 300:  # 150 秒超时
                        raise LoginFailed(f"轮询超时: {exc}") from exc
                    continue
                status = msg.get("status", -1)
                logger.debug(f"Poll #{poll_count}: status={status}")

                if status == -1:
                    # 未扫描，继续轮询
                    pass
                elif status == 0:
                    # 已扫描，仅提示一次
                    if not scanned_notified:
                        scanned_notified = True
                        logger.info(f"QR Scanned: {msg.get('msg', '')}")
                        if on_scanned:
                            on_scanned()
                elif status == 1:
                    # 已确认，获取一次性密码完成登录
                    once_password = msg.get("oncePassword", "")
                    logger.info("One-time code received")
                    return self._complete_login_with_once_password(once_password)
                elif status == 2:
                    # 二维码过期，重试
                    if _max_retries <= 0:
                        raise LoginFailed("二维码过期重试次数已达上限")
                    logger.warning(f"QR code expired, retrying... ({_max_retries} retries left)")
                    return self.login_with_qr(qr_callback, on_scanned, image_path, _max_retries - 1)
                elif status == 3:
                    # 用户取消
                    raise LoginFailed("用户取消登录")
                else:
                    raise LoginFailed(f"未知扫码状态: {status}, msg={msg.get('msg', '')}")

        except LoginFailed:
            raise
        except Exception as e:
            raise LoginFailed(f"扫码登录失败: {e}") from e

    def login_with_password(self, account: str, password: SecretPassword) -> LoginResult:
        """账户密码登录（一次命令只提交一次，失败即退出）

        ``status=2`` 仅表示未完成学校认证，用 cacheId 续登后与成功等价，不提示用户。

        Raises:
            LoginFailed: 验证码不可用/求解失败、账号密码错误、账号禁用等
        """
        ensure_password_login_ready(self._config)
        validate = self._solve_login_captcha()

        result = self._api.login_by_password(account, password, validate)

        if result.status is AccountLoginStatus.SCHOOL_UNVERIFIED:
            if not result.cache_id:
                raise LoginFailed("学校认证续登失败：服务端未返回 cacheId")
            result = self._api.skip_set(result.cache_id)

        if result.status is AccountLoginStatus.OK and not result.pwd:
            if not result.uuid:
                raise LoginFailed("登录成功但未返回一次性密码")
            result = self._api.skip_set(result.uuid)

        if result.status is not AccountLoginStatus.OK:
            raise LoginFailed(STATUS_HINTS.get(result.status, f"登录失败：{result.msg or result.status}"))
        if not result.pwd:
            raise LoginFailed("登录成功但未返回一次性密码")

        logger.info("账户密码验证通过，正在换取登录态")
        return self._complete_login_with_once_password(result.pwd)

    def _solve_login_captcha(self) -> str:
        """求解登录页滑块验证码（与视频滑块同协议），失败直接终止"""
        logger.info("正在求解登录验证码")
        solution: CaptchaSolution | None = self._session.captcha.solve(
            CaptchaTrigger(kind="slide", referer=LOGIN_REFERER)
        )
        if solution is None:
            raise LoginFailed("登录验证码求解失败，请重试或改用 zhs login --method qr 扫码登录")
        return solution.validate

    def _complete_login_with_once_password(self, once_password: str) -> LoginResult:
        """用一次性密码换票并落 cookies（扫码与密码登录共用）"""
        login_page = f"{self._config.urls.passport}/login"
        gologin_url = f"{self._config.urls.base}/login/gologin"

        # 用 oncePassword 完成登录（gologin 返回 HTML，不解析 JSON）
        client = self._session._get_client()
        client.get(f"{login_page}?service={gologin_url}", params={"pwd": once_password})
        self._session.cookies = client.cookies
        if not self._session.cookies:
            raise LoginFailed("登录后未获取到 cookies")

        logger.info("Login successful")
        return LoginResult(success=True, uuid=self._session.uuid, cookies=self._session.cookies)

    def try_restore_cookies(self, cookies_path: Path) -> bool:
        """仅从文件恢复 cookies（不联网、不判定登录态）

        Args:
            cookies_path: cookies JSON 文件路径

        Returns:
            True 恢复成功，False 恢复失败（文件不存在/内容无效）
        """
        cookies_data = read_cookies_file(cookies_path)
        if cookies_data is None:
            return False

        try:
            self._session.cookies = list_to_cookies(cookies_data)
        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to restore cookies from file")
            return False

        logger.info("Successfully restored cookies from file")
        return True

    def save_cookies(self, cookies_path: Path) -> None:
        """保存 cookies 到文件

        Args:
            cookies_path: cookies JSON 文件路径
        """
        cookies_data = cookies_to_list(self._session.cookies)
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        cookies_path.write_text(
            json.dumps(cookies_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Cookies saved to {cookies_path}")

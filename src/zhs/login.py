"""ZHS 登录管理模块

提供扫码登录（QR Code）和 Cookie 持久化功能。
账号密码登录已移除（需要验证码，体验差）。
"""

import json
import time
from base64 import b64decode
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from zhs.config import AppConfig
from zhs.exceptions import LoginFailed
from zhs.session import ZhsSession
from zhs.utils.cookie import cookies_to_list, list_to_cookies


class LoginResult:
    """登录结果"""

    def __init__(self, success: bool, uuid: str | None = None, cookies: httpx.Cookies | None = None) -> None:
        self.success = success
        self.uuid = uuid
        self.cookies = cookies


class LoginManager:
    """登录管理器：扫码登录 + Cookie 持久化"""

    def __init__(self, session: ZhsSession, config: AppConfig) -> None:
        self._session = session
        self._config = config

    @property
    def session(self) -> ZhsSession:
        """获取关联的 ZhsSession"""
        return self._session

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
        qr_page = f"{self._config.urls.passport}/qrCodeLogin/getLoginQrImg"
        query_page = f"{self._config.urls.passport}/qrCodeLogin/getLoginQrInfo"
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
                    # 用 oncePassword 完成登录（gologin 返回 HTML，不解析 JSON）
                    client = self._session._get_client()
                    client.get(f"{login_page}?service={gologin_url}", params={"pwd": once_password})
                    self._session.cookies = client.cookies
                    if not self._session.cookies:
                        raise LoginFailed("登录后未获取到 cookies")

                    logger.info("Login successful")
                    return LoginResult(
                        success=True,
                        uuid=self._session.uuid,
                        cookies=self._session.cookies,
                    )
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

    def try_restore_cookies(self, cookies_path: Path) -> bool:
        """尝试从文件恢复 cookies

        Args:
            cookies_path: cookies JSON 文件路径

        Returns:
            True 恢复成功，False 恢复失败（文件不存在/内容无效）
        """
        if not cookies_path.exists():
            return False

        try:
            raw = cookies_path.read_text(encoding="utf-8")
            if not raw.strip():
                return False
            cookies_data: list[dict[str, Any]] = json.loads(raw)
            if not cookies_data:
                return False

            cookies = list_to_cookies(cookies_data)
            self._session.cookies = cookies
            logger.info("Successfully restored cookies from file")
            return True
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Failed to restore cookies from file")
            return False

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

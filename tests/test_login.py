"""Task 2.1 — login.py 测试"""

import json
from base64 import b64decode
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.exceptions import LoginFailed
from zhs.login import LoginManager, LoginResult
from zhs.session import ZhsSession


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def session(config: AppConfig) -> ZhsSession:
    """测试用 session"""
    return ZhsSession(config)


@pytest.fixture
def login_manager(session: ZhsSession, config: AppConfig) -> LoginManager:
    """测试用 LoginManager"""
    return LoginManager(session, config)


@pytest.fixture
def mock_http() -> Any:
    """Mock HTTP 请求"""
    with respx.mock:
        yield


# ---------------------------------------------------------------------------
# 1. 扫码登录完整流程：获取二维码 → 轮询 → 确认 → 登录
# ---------------------------------------------------------------------------


class TestQrLoginFullFlow:
    def test_qr_login_success(self, login_manager: LoginManager, mock_http: Any) -> None:
        """扫码登录完整流程：获取二维码 → -1 → 0 → 1 → 登录成功"""
        # Mock 初始登录页 + gologin（catch-all /login 请求，均返回 Set-Cookie）
        respx.get("https://passport.zhihuishu.com/login").mock(
            return_value=httpx.Response(
                200,
                text="<html>ok</html>",
                headers={
                    "Set-Cookie": (
                        'CASLOGC={"uuid":"test-uuid"}; Domain=zhihuishu.com; sessionid=abc123; Domain=zhihuishu.com'
                    )
                },
            )
        )

        # Mock getLoginQrImg
        fake_qr_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrImg").mock(
            return_value=httpx.Response(200, json={"qrToken": "test-token-123", "img": fake_qr_img})
        )

        # Mock getLoginQrInfo: -1 → 0 → 1
        call_count = 0

        def qr_info_side_effect(_request: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"status": -1, "msg": "未扫描"})
            elif call_count == 2:
                return httpx.Response(200, json={"status": 0, "msg": "已扫描"})
            else:
                return httpx.Response(200, json={"status": 1, "msg": "已确认", "oncePassword": "otp-abc"})

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrInfo").mock(side_effect=qr_info_side_effect)

        # 收集 callback 调用
        received_images: list[bytes] = []

        def qr_callback(img: bytes) -> None:
            received_images.append(img)

        result = login_manager.login_with_qr(qr_callback)

        assert isinstance(result, LoginResult)
        assert result.success is True
        assert len(received_images) == 1
        # 验证 callback 收到的是解码后的图片数据
        assert received_images[0] == b64decode(fake_qr_img)


# ---------------------------------------------------------------------------
# 2. 扫码 status=2 过期 → 递归重试
# ---------------------------------------------------------------------------


class TestQrExpiredRetry:
    def test_expired_then_success(self, login_manager: LoginManager, mock_http: Any) -> None:
        """二维码过期后自动重试，第二次成功"""
        # Mock 初始登录页 + gologin（catch-all /login 请求，均返回 Set-Cookie）
        respx.get("https://passport.zhihuishu.com/login").mock(
            return_value=httpx.Response(
                200,
                text="<html>ok</html>",
                headers={"Set-Cookie": 'CASLOGC={"uuid":"retry-uuid"}; Domain=zhihuishu.com'},
            )
        )

        # Mock getLoginQrImg: 两次调用（第一次过期后重新获取）
        qr_call_count = 0

        def qr_img_side_effect(_request: object) -> httpx.Response:
            nonlocal qr_call_count
            qr_call_count += 1
            return httpx.Response(200, json={"qrToken": f"token-{qr_call_count}", "img": "aW1n"})

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrImg").mock(side_effect=qr_img_side_effect)

        # Mock getLoginQrInfo: 第一次过期 → 第二次成功
        info_call_count = 0

        def qr_info_side_effect(_request: object) -> httpx.Response:
            nonlocal info_call_count
            info_call_count += 1
            if info_call_count == 1:
                return httpx.Response(200, json={"status": 2, "msg": "二维码已过期"})
            return httpx.Response(200, json={"status": 1, "msg": "已确认", "oncePassword": "otp-retry"})

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrInfo").mock(side_effect=qr_info_side_effect)

        callback_count = 0

        def qr_callback(_data: bytes) -> None:
            nonlocal callback_count
            callback_count += 1

        result = login_manager.login_with_qr(qr_callback)

        assert result.success is True
        # callback 被调用两次（第一次过期后重新获取二维码）
        assert callback_count == 2


# ---------------------------------------------------------------------------
# 3. 扫码 status=3 取消 → 抛异常
# ---------------------------------------------------------------------------


class TestQrCancelled:
    def test_cancel_raises_login_failed(self, login_manager: LoginManager, mock_http: Any) -> None:
        """用户取消扫码 → 抛 LoginFailed"""
        # Mock 初始登录页
        respx.get(
            "https://passport.zhihuishu.com/login",
            params={"service": "https://onlineservice-api.zhihuishu.com/login/gologin"},
        ).mock(return_value=httpx.Response(200, text="<html>ok</html>"))

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrImg").mock(
            return_value=httpx.Response(200, json={"qrToken": "cancel-token", "img": "aW1n"})
        )

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrInfo").mock(
            return_value=httpx.Response(200, json={"status": 3, "msg": "用户取消登录"})
        )

        with pytest.raises(LoginFailed, match="取消"):
            login_manager.login_with_qr(lambda img: None)


# ---------------------------------------------------------------------------
# 4. 扫码 status=0 仅提示一次"已扫描"
# ---------------------------------------------------------------------------


class TestQrScannedDedup:
    def test_scanned_notification_once(self, login_manager: LoginManager, mock_http: Any) -> None:
        """status=0 仅提示一次'已扫描'，多次 status=0 不重复提示"""
        # Mock 初始登录页 + gologin（catch-all /login 请求，均返回 Set-Cookie）
        respx.get("https://passport.zhihuishu.com/login").mock(
            return_value=httpx.Response(
                200,
                text="<html>ok</html>",
                headers={"Set-Cookie": 'CASLOGC={"uuid":"dedup-uuid"}; Domain=zhihuishu.com'},
            )
        )

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrImg").mock(
            return_value=httpx.Response(200, json={"qrToken": "dedup-token", "img": "aW1n"})
        )

        # Mock: -1 → 0 → 0 → 0 → 1
        call_count = 0

        def qr_info_side_effect(_request: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"status": -1, "msg": "未扫描"})
            elif call_count <= 4:
                return httpx.Response(200, json={"status": 0, "msg": "已扫描"})
            else:
                return httpx.Response(200, json={"status": 1, "msg": "已确认", "oncePassword": "otp-dedup"})

        respx.get("https://passport.zhihuishu.com/qrCodeLogin/getLoginQrInfo").mock(side_effect=qr_info_side_effect)

        scanned_count = 0

        class ScanTracker:
            """追踪 on_scanned 回调调用次数"""

            def __call__(self) -> None:
                nonlocal scanned_count
                scanned_count += 1

        result = login_manager.login_with_qr(lambda img: None, on_scanned=ScanTracker())

        assert result.success is True
        # on_scanned 只被调用一次（3 次 status=0 但只提示一次）
        assert scanned_count == 1


# ---------------------------------------------------------------------------
# 5. Cookie 恢复登录成功
# ---------------------------------------------------------------------------


class TestCookieRestore:
    def test_restore_valid_cookies(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """从文件恢复有效 cookies"""
        cookies_data = [
            {"name": "CASLOGC", "value": '{"uuid":"test-uuid-123"}', "domain": "zhihuishu.com"},
            {"name": "sessionid", "value": "abc123", "domain": "zhihuishu.com"},
        ]
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(cookies_data), encoding="utf-8")

        result = login_manager.try_restore_cookies(cookies_file)

        assert result is True
        assert login_manager.session.uuid == "test-uuid-123"

    def test_restore_missing_file(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """cookies 文件不存在 → 返回 False"""
        result = login_manager.try_restore_cookies(tmp_path / "nonexistent.json")
        assert result is False

    def test_restore_invalid_json(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """cookies 文件内容无效 → 返回 False"""
        cookies_file = tmp_path / "bad.json"
        cookies_file.write_text("not valid json{{{", encoding="utf-8")

        result = login_manager.try_restore_cookies(cookies_file)
        assert result is False

    def test_restore_empty_file(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """cookies 文件为空 → 返回 False"""
        cookies_file = tmp_path / "empty.json"
        cookies_file.write_text("", encoding="utf-8")

        result = login_manager.try_restore_cookies(cookies_file)
        assert result is False


# ---------------------------------------------------------------------------
# 6. Cookie 过期 → 重新登录
# ---------------------------------------------------------------------------


class TestCookieExpired:
    def test_save_cookies(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """save_cookies 正确保存 cookies 到文件"""
        # 先设置一些 cookies
        c = httpx.Cookies()
        c.set("sessionid", "test-session", domain="zhihuishu.com")
        c.set("CASLOGC", '{"uuid":"save-test"}', domain="zhihuishu.com")
        login_manager.session.cookies = c

        cookies_file = tmp_path / "cookies.json"
        login_manager.save_cookies(cookies_file)

        assert cookies_file.exists()
        data = json.loads(cookies_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_save_and_restore_roundtrip(self, login_manager: LoginManager, tmp_path: Path) -> None:
        """保存后恢复 cookies 保持一致"""
        c = httpx.Cookies()
        c.set("sessionid", "roundtrip-session", domain="zhihuishu.com")
        c.set("CASLOGC", '{"uuid":"roundtrip-uuid"}', domain="zhihuishu.com")
        login_manager.session.cookies = c

        cookies_file = tmp_path / "cookies.json"
        login_manager.save_cookies(cookies_file)

        # 新建 manager 恢复
        new_config = AppConfig()
        new_session = ZhsSession(new_config)
        new_manager = LoginManager(new_session, new_config)

        result = new_manager.try_restore_cookies(cookies_file)
        assert result is True
        assert new_session.uuid == "roundtrip-uuid"

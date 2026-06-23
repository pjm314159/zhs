"""登录集成测试 — 扫码登录、Cookie 恢复与持久化"""

import json
from pathlib import Path

import pytest

from zhs.config import AppConfig
from zhs.login import LoginManager
from zhs.session import ZhsSession
from zhs.utils.cookie import cookies_to_list, list_to_cookies
from zhs.utils.path import get_data_dir

pytestmark = pytest.mark.integration


class TestCookieRestore:
    """Cookie 恢复与持久化"""

    def test_cookie_restore_valid(self, logged_in_session: ZhsSession) -> None:
        """L-04: 从文件恢复 Cookie 后可正常调用 API"""
        assert logged_in_session.uuid is not None
        assert len(logged_in_session.uuid) > 0

    def test_cookie_uuid_format(self, logged_in_session: ZhsSession) -> None:
        """L-05: uuid 格式正确（非空字符串）"""
        uuid = logged_in_session.uuid
        assert uuid is not None
        assert isinstance(uuid, str)
        assert len(uuid) > 0

    def test_cookie_exit_record_set(self, logged_in_session: ZhsSession) -> None:
        """L-06: exitRecod_{uuid} 自动设置"""
        uuid = logged_in_session.uuid
        assert uuid is not None
        cookie_name = f"exitRecod_{uuid}"
        assert cookie_name in logged_in_session.cookies

    def test_cookie_save_and_reload(self, logged_in_session: ZhsSession, app_config: AppConfig, tmp_path: Path) -> None:
        """L-06: Cookie 保存与恢复一致性"""
        # 保存
        cookies_file = tmp_path / "test_cookies.json"
        cookie_list = cookies_to_list(logged_in_session.cookies)
        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump(cookie_list, f, indent=2, ensure_ascii=False)

        # 恢复到新 session
        new_session = ZhsSession(app_config)
        with open(cookies_file, encoding="utf-8") as f:
            raw = json.load(f)
        new_session.cookies = list_to_cookies(raw)

        assert new_session.uuid == logged_in_session.uuid
        new_session.close()

    def test_cookie_file_exists(self, cookies_path: Path) -> None:
        """Cookie 文件已保存"""
        assert cookies_path.exists()
        with open(cookies_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0


class TestQRLogin:
    """扫码登录（需要手动操作）"""

    @pytest.mark.manual_login
    def test_qr_login_full_flow(self, app_config: AppConfig) -> None:
        """L-01: 扫码登录完整流程"""
        session = ZhsSession(app_config)
        login_mgr = LoginManager(session, app_config)
        qr_path = str(get_data_dir() / "qrcode_test.png")
        result = login_mgr.login_with_qr(
            qr_callback=lambda img_bytes: None,
            image_path=qr_path,
        )

        assert result.success is True
        assert result.uuid is not None
        assert result.cookies is not None
        session.close()

    @pytest.mark.manual_login
    def test_qr_image_saved(self, app_config: AppConfig, tmp_path: Path) -> None:
        """L-02: 二维码图片保存"""
        session = ZhsSession(app_config)
        login_mgr = LoginManager(session, app_config)
        qr_path = str(tmp_path / "qr_test.png")
        login_mgr.login_with_qr(
            qr_callback=lambda img_bytes: None,
            image_path=qr_path,
        )

        assert Path(qr_path).exists()
        assert Path(qr_path).stat().st_size > 0
        session.close()

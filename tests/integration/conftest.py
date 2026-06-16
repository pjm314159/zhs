"""集成测试 conftest — 提供真实 ZhsSession 和登录状态

集成测试使用真实 API，需要扫码登录。
Cookie 保存后可复用，无需重复扫码。

运行方式：
    pytest tests/integration/ -m integration -v          # 运行所有集成测试
    pytest tests/integration/ -m "integration and not manual_login"  # 跳过需要扫码的测试
    pytest tests/integration/ -m "integration and not openai"        # 跳过需要 OpenAI Key 的测试
"""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from zhs.config import AppConfig, ConfigManager
from zhs.session import ZhsSession
from zhs.utils.cookie import cookies_to_list, list_to_cookies
from zhs.utils.path import get_data_dir


def pytest_configure(config: pytest.Config) -> None:
    """注册自定义标记"""
    config.addinivalue_line("markers", "integration: 需要真实 API 的集成测试")
    config.addinivalue_line("markers", "manual_login: 需要手动扫码登录")
    config.addinivalue_line("markers", "openai: 需要 OpenAI API Key")
    config.addinivalue_line("markers", "moonshot: 需要 MoonShot API Key")


@pytest.fixture(scope="session")
def app_config() -> AppConfig:
    """加载真实配置"""
    return ConfigManager().load()


@pytest.fixture(scope="session")
def cookies_path() -> Path:
    """集成测试 Cookie 文件路径"""
    return get_data_dir() / "cookies.json"


@pytest.fixture(scope="session")
def logged_in_session(app_config: AppConfig, cookies_path: Path) -> Generator[ZhsSession, None, None]:
    """已登录的 ZhsSession

    优先从 .zhs/cookies.json 恢复 Cookie；
    如果 Cookie 无效或不存在，则触发扫码登录。
    """
    session = ZhsSession(app_config)

    # 尝试恢复已有 Cookie
    if cookies_path.exists():
        with open(cookies_path, encoding="utf-8") as f:
            raw = json.load(f)
        session.cookies = list_to_cookies(raw)

        # 验证有效性：尝试获取课程列表
        from zhs.zhidao.course import ZhidaoCourseManager

        try:
            mgr = ZhidaoCourseManager(session)
            courses = mgr.get_course_list()
            if courses:
                print(f"\n[集成测试] Cookie 有效，uuid={session.uuid}")
                yield session
                session.close()
                return
        except Exception as e:
            print(f"\n[集成测试] Cookie 无效: {e}")

    # Cookie 无效，需要扫码登录
    from zhs.login import LoginManager

    login_mgr = LoginManager(session, app_config)
    qr_path = str(get_data_dir() / "qrcode_integration.png")
    print(f"\n[集成测试] 请扫描二维码登录，图片保存于: {qr_path}")
    result = login_mgr.login_with_qr(
        qr_callback=lambda img_bytes: None,
        image_path=qr_path,
    )
    if not result.success:
        pytest.skip("扫码登录失败或超时")

    # 保存 Cookie 供后续测试使用
    if result.cookies:
        with open(cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies_to_list(result.cookies), f, indent=2, ensure_ascii=False)

    print(f"[集成测试] 登录成功，uuid={session.uuid}")
    yield session
    session.close()


@pytest.fixture(scope="session")
def zhidao_course(logged_in_session: ZhsSession) -> dict[str, Any]:
    """获取第一门知到课程信息（用于后续测试）"""
    from zhs.zhidao.course import ZhidaoCourseManager

    mgr = ZhidaoCourseManager(logged_in_session)
    courses = mgr.get_course_list()
    if not courses:
        pytest.skip("没有知到课程可供测试")
    c = courses[0]
    return {"name": c.course_name, "secret": c.secret}


@pytest.fixture(scope="session")
def ai_course(logged_in_session: ZhsSession) -> dict[str, Any]:
    """获取第一门 AI 课程信息（用于后续测试）"""
    from zhs.ai.course import AiCourseManager

    mgr = AiCourseManager(logged_in_session)
    courses = mgr.get_ai_course_list()
    if not courses:
        pytest.skip("没有 AI 课程可供测试")
    c = courses[0]
    return {
        "name": c.get("courseName", ""),
        "courseId": c.get("courseId"),
        "classId": c.get("classId"),
    }

"""api/sso.py SsoAuthenticator 测试

验证 CAS SSO 认证流程：
- 访问 passport/cas/login?service=xxx
- 302 带 ticket → ticket 验证设置 session cookie
- 失败抛 ZhsError
"""

import httpx
import pytest
import respx

from zhs.api.http_client import HttpClient
from zhs.api.sso import SsoAuthenticator
from zhs.config import AppConfig
from zhs.exceptions import ZhsError


@pytest.fixture
def config() -> AppConfig:
    """测试用配置"""
    return AppConfig()


@pytest.fixture
def http_client(config: AppConfig) -> HttpClient:
    """测试用 HttpClient"""
    return HttpClient(config)


@pytest.fixture
def sso(http_client: HttpClient) -> SsoAuthenticator:
    """测试用 SsoAuthenticator"""
    return SsoAuthenticator(http_client)


class TestSsoLogin:
    """CAS SSO 认证"""

    def test_success_with_ticket(self, sso: SsoAuthenticator) -> None:
        """302 带 ticket → 认证成功"""
        with respx.mock:
            # CAS login 返回 302 带 ticket
            respx.get(
                "https://passport.zhihuishu.com/cas/login",
                params={
                    "service": "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework"
                },
            ).mock(
                return_value=httpx.Response(
                    302,
                    headers={
                        "location": "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework?ticket=ST-abc"
                    },
                )
            )
            # ticket 验证
            respx.get("https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework").mock(
                return_value=httpx.Response(200)
            )
            sso.login()  # 不抛异常即成功

    def test_302_no_ticket_raises_zhs_error(self, sso: SsoAuthenticator) -> None:
        """302 但无 ticket → 抛 ZhsError"""
        with respx.mock:
            respx.get(
                "https://passport.zhihuishu.com/cas/login",
                params={
                    "service": "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework"
                },
            ).mock(
                return_value=httpx.Response(
                    302,
                    headers={"location": "https://passport.zhihuishu.com/login"},
                )
            )
            with pytest.raises(ZhsError, match="CAS SSO"):
                sso.login()

    def test_200_raises_zhs_error(self, sso: SsoAuthenticator) -> None:
        """200（重定向到登录页）→ 抛 ZhsError"""
        with respx.mock:
            respx.get(
                "https://passport.zhihuishu.com/cas/login",
                params={
                    "service": "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework"
                },
            ).mock(return_value=httpx.Response(200, text="login page"))
            with pytest.raises(ZhsError, match="CAS SSO"):
                sso.login()

    def test_other_status_raises_zhs_error(self, sso: SsoAuthenticator) -> None:
        """其他状态码 → 抛 ZhsError"""
        with respx.mock:
            respx.get(
                "https://passport.zhihuishu.com/cas/login",
                params={
                    "service": "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework"
                },
            ).mock(return_value=httpx.Response(500))
            with pytest.raises(ZhsError, match="CAS SSO"):
                sso.login()

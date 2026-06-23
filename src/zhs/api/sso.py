"""CAS SSO 认证

从原 ZhsSession.exam_sso_login 迁移。
studentexam-api 不像 studyservice-api 有 /login/gologin，
需要通过 passport CAS SSO 获取认证。

流程：
1. 访问 passport/cas/login?service=xxx
2. 302 带 ticket → ticket 验证设置 session cookie
3. 失败抛 ZhsError
"""

from loguru import logger

from zhs.api.http_client import HttpClient
from zhs.exceptions import ZhsError


class SsoAuthenticator:
    """CAS SSO 认证器"""

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client

    def login(self) -> None:
        """通过 CAS SSO 认证 studentexam-api 域名

        Raises:
            ZhsError: CAS 认证失败（CASTGC 过期，需要重新登录）
        """
        service_url = f"{self._http.urls.homework}/studentExam/gateway/t/v1/student/getStudentHomework"
        cas_login_url = f"{self._http.urls.passport}/cas/login?service={service_url}"

        resp = self._http.get_no_redirect(cas_login_url)

        if resp.status_code == 302:
            ticket_url = resp.headers.get("location", "")
            if "ticket=" in ticket_url:
                self._http.get(ticket_url, follow_redirects=True)
                logger.debug("CAS SSO 认证成功")
                return
            # 302 但无 ticket，可能是重定向到登录页
            logger.warning(f"CAS SSO 302 但无 ticket: {ticket_url[:100]}")
        elif resp.status_code == 200:
            logger.warning("CAS SSO 返回 200，CASTGC 可能已过期")

        raise ZhsError(
            "CAS SSO 认证失败，请重新登录: zhs login\n  原因: CASTGC cookie 已过期，studentexam-api 无法认证"
        )

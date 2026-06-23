"""ZHS HTTP 会话门面（Facade）

委托给 api/ 子包的具体类：
- HttpClient：HTTP 客户端生命周期、Cookie/UUID 管理、通用查询
- EncryptedQuery：6 套加密查询策略
- ZhidaoHomeworkApi：知到作业业务 API
- AiAnalysisApi：AI 解析 SSE 流式
- SsoAuthenticator：CAS SSO 认证

保留 ZhsSession 旧 API 作为门面，老代码无需改动；
新代码优先使用 api/ 子包的具体类。
"""

from typing import Any

import httpx

from zhs.api.ai_analysis_api import AiAnalysisApi
from zhs.api.encrypted_query import EncryptedQuery
from zhs.api.http_client import HttpClient
from zhs.api.sso import SsoAuthenticator
from zhs.api.zhidao_homework_api import ZhidaoHomeworkApi
from zhs.config import AppConfig, CryptoConfig, UrlConfig


class ZhsSession:
    """智慧树 HTTP 会话门面

    内部委托给 api/ 子包的具体类，对外保持旧 API 不变。
    """

    def __init__(self, config: AppConfig, max_retries: int = 5) -> None:
        self._http = HttpClient(config, max_retries=max_retries)
        self._query = EncryptedQuery(self._http)
        self._homework_api = ZhidaoHomeworkApi(self._query)
        self._ai_analysis_api = AiAnalysisApi(self._http)
        self._sso = SsoAuthenticator(self._http)

    # --- 配置与状态（委托给 HttpClient）---

    @property
    def urls(self) -> UrlConfig:
        """URL 配置"""
        return self._http.urls

    @property
    def crypto(self) -> CryptoConfig:
        """密钥配置"""
        return self._http.crypto

    @property
    def cookies(self) -> httpx.Cookies:
        """获取 cookies"""
        return self._http.cookies

    @cookies.setter
    def cookies(self, value: httpx.Cookies | list[dict[str, Any]] | dict[str, str]) -> None:
        """设置 cookies，自动解析 uuid 并添加 exitRecod"""
        self._http.cookies = value

    @property
    def uuid(self) -> str | None:
        """从 CASLOGC cookie 中解析的 uuid"""
        return self._http.uuid

    def _parse_uuid(self) -> None:
        """从 CASLOGC cookie 中解析 uuid（向后兼容入口）"""
        self._http.parse_uuid()

    @property
    def _cookies(self) -> httpx.Cookies:
        """向后兼容：直接访问内部 cookies"""
        return self._http._cookies

    @_cookies.setter
    def _cookies(self, value: httpx.Cookies) -> None:
        """向后兼容：直接设置内部 cookies"""
        self._http._cookies = value

    def _get_client(self) -> httpx.Client:
        """获取或创建同步 HTTP 客户端（委托给 HttpClient）"""
        return self._http._get_client()

    # --- 通用查询（委托给 HttpClient）---

    def api_query(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """通用 API 查询"""
        return self._http.api_query(url, data=data, method=method, content_type=content_type)

    # --- 6 套加密查询（委托给 EncryptedQuery）---

    def zhidao_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
        content_type: str = "form",
        set_timestamp: bool = True,
    ) -> dict[str, Any]:
        """知到 API 查询（video_key 加密 + dateFormate，检查 code，-12 抛 CaptchaRequired）

        注意：key / ok_code / content_type / set_timestamp 参数为兼容旧 API 保留。
        - key: 覆盖默认 video_key（如 home_key / ai_key）
        - ok_code: 覆盖默认期望码 0（如 200）
        - content_type: 覆盖默认 "form"（如 "json"）
        - set_timestamp=False: 不发送 dateFormate（实际项目未使用）
        """
        if not set_timestamp:
            return self._zhidao_query_no_ts(
                url, data, key=key, ok_code=ok_code, method=method, content_type=content_type
            )
        # content_type 仅在非默认值时传 override（避免策略表查找开销）
        ct_override = content_type if content_type != "form" else None
        return self._query.query(
            "zhidao",
            url,
            data,
            method=method,
            key_bytes_override=key,
            ok_value_override=ok_code,
            content_type_override=ct_override,
        )

    def _zhidao_query_no_ts(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """zhidao_query(set_timestamp=False) 兼容实现：不发 dateFormate"""
        import json

        from zhs.crypto import Cipher
        from zhs.exceptions import ApiError, CaptchaRequired

        if key is None:
            key = self.crypto.key_bytes("video_key")
        iv = self.crypto.key_bytes("iv")
        cipher = Cipher(key, iv)
        encrypted_data = cipher.encrypt(json.dumps(data))
        form_data: dict[str, Any] = {"secretStr": encrypted_data}
        result = self.api_query(url, data=form_data, method=method, content_type=content_type)
        code = result.get("code", 0)
        if code == -12:
            raise CaptchaRequired("服务端要求验证码")
        if code != ok_code:
            raise ApiError(code=code, message=result.get("message", ""))
        return result

    def hike_query(
        self,
        url: str,
        data: dict[str, Any],
        sig: bool = False,
        ok_code: int = 200,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Hike API 查询（无加密，时间戳 + 可选签名，检查 status=200）

        注意：ok_code 参数为兼容旧 API 保留，策略表固定为 200。
        """
        return self._query.query("hike", url, data, method=method, sig=sig)

    def ai_exam_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
    ) -> dict[str, Any]:
        """AI 考试 API 查询（exam_key 加密 + dateFormate，检查 code=0）"""
        return self._query.query("ai_exam", url, data, method=method)

    def ai_exam_submit(self, url: str, data: dict[str, Any]) -> bool:
        """AI 考试提交（exam_key 加密，无返回体，HTTP 200=成功）"""
        self._query.query("ai_exam_submit", url, data)
        return True

    def ai_task_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 200,
        method: str = "POST",
    ) -> dict[str, Any]:
        """AI 任务列表 API 查询（ai_key 加密 + dateFormate，检查 code=200，json）"""
        return self._query.query("ai_task", url, data, method=method)

    def homework_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_status: str = "200",
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """知到作业 API 查询（exam_key 加密，无 dateFormate，检查 status='200'）"""
        return self._query.query("homework", url, data, method=method)

    # --- 知到作业业务 API（委托给 ZhidaoHomeworkApi）---

    def homework_redo(
        self,
        recruit_id: str,
        exam_id: str,
        course_id: int,
    ) -> dict[str, Any]:
        """重做作业（saveCourseTran）"""
        return self._homework_api.homework_redo(recruit_id, exam_id, course_id)

    def homework_do(
        self,
        recruit_id: str,
        exam_id: str,
        student_exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """开始做作业（doHomework）"""
        return self._homework_api.homework_do(recruit_id, exam_id, student_exam_id, school_id, course_id)

    def homework_save_answer(
        self,
        answer_item: dict[str, Any],
        recruit_id: str,
    ) -> dict[str, Any]:
        """保存单题答案（saveStudentAnswer）"""
        return self._homework_api.homework_save_answer(answer_item, recruit_id)

    def homework_submit(
        self,
        recruit_id: str,
        exam_id: str,
        stu_exam_id: str,
        achieve_count: int,
    ) -> dict[str, Any]:
        """提交作业（submit）"""
        return self._homework_api.homework_submit(recruit_id, exam_id, stu_exam_id, achieve_count)

    def homework_look(
        self,
        recruit_id: str,
        student_exam_id: str,
        exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """查看已提交作业（lookHomework）"""
        return self._homework_api.homework_look(recruit_id, student_exam_id, exam_id, school_id, course_id)

    def homework_get_answer(
        self,
        recruit_id: str,
        stu_exam_id: str,
        exam_id: str,
        school_id: str,
        course_id: str,
        question_ids: list[int],
    ) -> dict[str, Any]:
        """获取学生答案信息（getStuAnswerInfo）"""
        return self._homework_api.homework_get_answer(
            recruit_id, stu_exam_id, exam_id, school_id, course_id, question_ids
        )

    # --- AI 解析 SSE（委托给 AiAnalysisApi）---

    def ai_analysis_run(
        self,
        course_id: int,
        recruit_id: str,
        question_id: int,
        thread_id: str = "",
        run_id: str | None = None,
        regenerate: bool = False,
        timeout: float = 60.0,
    ) -> str:
        """调用 AI 解析 run API（SSE 流式），返回完整解析内容"""
        return self._ai_analysis_api.run(
            course_id,
            recruit_id,
            question_id,
            thread_id=thread_id,
            run_id=run_id,
            regenerate=regenerate,
            timeout=timeout,
        )

    # --- CAS SSO（委托给 SsoAuthenticator）---

    def exam_sso_login(self) -> None:
        """通过 CAS SSO 认证 studentexam-api 域名"""
        self._sso.login()

    # --- 生命周期 ---

    def close(self) -> None:
        """关闭客户端"""
        self._http.close()

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
from zhs.api.zhidao_exam_api import ZhidaoExamApi
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
        self._exam_api = ZhidaoExamApi(self._query)
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

    def zhidao_exam_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_status: str = "200",
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """知到考试 API 查询（exam_key 加密，无 dateFormate，检查 status='200'）

        与 homework_query 加密策略相同，仅 base_url 不同（taurusexam vs homework）。
        """
        return self._query.query("zhidao_exam", url, data, method=method)

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

    # --- 知到考试业务 API（委托给 ZhidaoExamApi）---

    def exam_list(
        self,
        course_id: int,
        recruit_id: str,
        flag: int,
    ) -> list[dict[str, Any]]:
        """获取考试列表（getStudentFinalExam）

        Args:
            course_id: 课程 ID
            recruit_id: 招募 ID
            flag: 1=未完成考试, 0=已完成考试
        """
        return self._exam_api.get_student_final_exam(course_id, recruit_id, flag)

    def exam_get_save_answer_lock_result(
        self,
        exam_id: str,
        recruit_id: str,
    ) -> int:
        """查询答案是否锁死（getSaveAnswerLockResult）

        Returns:
            rt.state: 0=未锁死（可以答题），1=锁死（跳过该考试）
        """
        return self._exam_api.get_save_answer_lock_result(exam_id, recruit_id)

    def exam_get_login_school_info(self) -> str:
        """获取当前登录用户学校 ID（getLoginSchoolInfo）

        用于 doExam / saveStudentAnswer 的 schoolId 参数。

        部分用户未绑定学校，此时返回空字符串。

        Returns:
            学校 ID 字符串（如 "625"），未绑定时返回 ""
        """
        return self._exam_api.get_login_school_info()

    def exam_do(
        self,
        recruit_id: str,
        exam_id: str,
        student_exam_id: str,
        school_id: str,
        course_id: str,
        device_id: str = "",
    ) -> dict[str, Any]:
        """开始考试（doExam），获取题目详情（含 eid）

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            student_exam_id: 学生考试记录 ID
            school_id: 学校 ID
            course_id: 课程 ID
            device_id: 设备 ID（通常为空字符串）

        Returns:
            rt 对象（含 examBase.workExamParts 题目列表）
        """
        return self._exam_api.do_exam(
            recruit_id=recruit_id,
            exam_id=exam_id,
            student_exam_id=student_exam_id,
            school_id=school_id,
            course_id=course_id,
            device_id=device_id,
        )

    def exam_save_answer(
        self,
        answer_item: dict[str, Any],
        recruit_id: str,
    ) -> dict[str, Any]:
        """保存单题答案（saveStudentAnswer）

        考试特有：额外发送 source=1 明文字段（作业不发送）。
        answer_item 中 examType=1（整数），作业为 ""（空字符串）。

        Args:
            answer_item: 答案项字典（含 examId/eid/answer/questionType/examType 等）
            recruit_id: 招募 ID

        Returns:
            rt 对象（含 statu 字段，注意 API 字段名拼写为 "statu" 非 "status"）
        """
        return self._exam_api.save_student_answer(answer_item, recruit_id)

    def exam_submit(
        self,
        recruit_id: str,
        exam_id: str,
        stu_exam_id: str,
        achieve_count: str,
    ) -> dict[str, Any]:
        """提交考试（submit）

        默认不提交，仅当用户指定 ``--submit`` 时调用。
        使用 zhidao_exam 策略（taurusexam-api 域名）。

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            stu_exam_id: 学生考试记录 ID
            achieve_count: 已答题数量（字符串型，如 "80"）

        Returns:
            rt 对象（含 msg 和 statu 字段，statu="1" 表示提交成功）
        """
        return self._exam_api.submit_exam(recruit_id, exam_id, stu_exam_id, achieve_count)

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

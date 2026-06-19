"""ZHS HTTP 会话管理模块

封装 httpx 同步客户端，提供知到/Hike/AI 考试 API 查询方法。
所有密钥和 URL 从 AppConfig 获取，不硬编码。
"""

import json
import time
from typing import Any

import httpx
from loguru import logger

from zhs.config import AppConfig, CryptoConfig, UrlConfig
from zhs.crypto import Cipher, sign_hike
from zhs.exceptions import ApiError, CaptchaRequired, ZhsError


class ZhsSession:
    """智慧树 HTTP 会话封装"""

    def __init__(self, config: AppConfig, max_retries: int = 5) -> None:
        self._config = config
        self._max_retries = max_retries
        self._client: httpx.Client | None = None
        self._uuid: str | None = None

        # Cookie jar
        self._cookies = httpx.Cookies()

    @property
    def urls(self) -> UrlConfig:
        """获取 URL 配置"""
        return self._config.urls

    @property
    def crypto(self) -> CryptoConfig:
        """获取密钥配置"""
        return self._config.crypto

    @property
    def cookies(self) -> httpx.Cookies:
        """获取 cookies"""
        return self._cookies

    @cookies.setter
    def cookies(self, value: httpx.Cookies | list[dict[str, Any]] | dict[str, str]) -> None:
        """设置 cookies，自动解析 uuid 并添加 exitRecod"""
        if isinstance(value, httpx.Cookies):
            self._cookies = value
        elif isinstance(value, list):
            # 从 list[dict] 反序列化
            from zhs.utils.cookie import list_to_cookies

            self._cookies = list_to_cookies(value)
        elif isinstance(value, dict):
            new_cookies = httpx.Cookies()
            for k, v in value.items():
                new_cookies.set(k, str(v))
            self._cookies = new_cookies

        # 解析 uuid from CASLOGC
        self._parse_uuid()

        # 同步到已有 client
        if self._client is not None:
            self._client.cookies = self._cookies

    def _parse_uuid(self) -> None:
        """从 CASLOGC cookie 中解析 uuid"""
        from urllib.parse import unquote

        caslogc = self._cookies.get("CASLOGC")
        if caslogc:
            try:
                decoded = unquote(caslogc)
                data = json.loads(decoded)
                self._uuid = data.get("uuid")
            except (json.JSONDecodeError, TypeError):
                self._uuid = None
        else:
            self._uuid = None

        # 设置 exitRecod_{uuid}=2
        if self._uuid:
            self._cookies.set(f"exitRecod_{self._uuid}", "2", domain="zhihuishu.com")

    @property
    def uuid(self) -> str | None:
        """从 CASLOGC cookie 中解析的 uuid"""
        return self._uuid

    def _get_client(self) -> httpx.Client:
        """获取或创建同步 HTTP 客户端"""
        if self._client is None:
            transport = httpx.HTTPTransport(retries=self._max_retries)
            proxy_dict = self._config.proxies.to_dict()
            # httpx 使用 proxy 参数（单个代理字符串）或 mounts 参数
            proxy = proxy_dict.get("http") or proxy_dict.get("https") or None
            self._client = httpx.Client(
                transport=transport,
                proxy=proxy,
                cookies=self._cookies,
                timeout=30.0,
                headers={
                    "Accept": "*/*",
                    "sec-ch-ua": ('" Not A;Brand";v="99", "Chromium";v="101", "Google Chrome";v="101"'),
                    "sec-ch-ua-mobile": "?0",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        " AppleWebKit/537.36 (KHTML, like Gecko)"
                        " Chrome/101.0.4951.64 Safari/537.36"
                    ),
                    "sec-ch-ua-platform": '"Windows"',
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Origin": "https://studyh5.zhihuishu.com",
                    "Referer": "https://studyh5.zhihuishu.com/",
                },
            )
        return self._client

    def api_query(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """通用 API 查询"""
        client = self._get_client()
        headers: dict[str, str] = dict(client.headers)

        if method.upper() == "POST":
            if content_type == "json":
                headers["Content-Type"] = "application/json;charset=UTF-8"
            elif content_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"

            if content_type == "json" and isinstance(data, dict):
                resp = client.post(url, content=json.dumps(data), headers=headers)
            else:
                resp = client.post(url, data=data, headers=headers)
        else:
            resp = client.get(url, params=data, headers=headers)

        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

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
        """知到 API 查询（自动加密 + 时间戳）

        密钥从 config.crypto 获取，默认使用 video_key。
        返回码 -12 抛 CaptchaRequired。
        """
        if key is None:
            key = self.crypto.key_bytes("video_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)

        # 时间戳加入 data 后一起加密
        if set_timestamp:
            data = dict(data)  # 浅拷贝，不修改原始 data
            data["dateFormate"] = int(time.time()) * 1000

        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data: dict[str, Any] = {
            "secretStr": encrypted_data,
        }

        # dateFormate 同时作为独立表单字段
        if set_timestamp:
            form_data["dateFormate"] = data["dateFormate"]

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
        """Hike API 查询（自动时间戳 + 可选签名）"""
        data = dict(data)  # 浅拷贝
        data["_"] = str(int(time.time()) * 1000)

        if sig:
            # 签名前将所有值转为字符串（与旧版一致）
            for k in data:
                data[k] = str(data[k])
            sign = sign_hike(data, self.crypto.hike_salt)
            data["signature"] = sign

        result = self.api_query(url, data=data, method=method)

        status = result.get("status", 0)
        if status != ok_code:
            raise ApiError(code=status, message=result.get("message", ""))

        return result

    def ai_exam_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_code: int = 0,
        method: str = "POST",
    ) -> dict[str, Any]:
        """AI 考试 API 同步查询，密钥从 config.crypto 获取

        使用 exam_key 加密，发送 dateFormate 字段，检查 code 字段。
        与 homework_query 的区别：
        - 发送 dateFormate 字段
        - 检查 code 字段（0）而非 status 字段（"200"）
        """
        if key is None:
            key = self.crypto.key_bytes("exam_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)
        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data = {
            "secretStr": encrypted_data,
            "dateFormate": str(int(time.time()) * 1000),
        }

        result = self.api_query(url, data=form_data, method=method)

        code = result.get("code", 0)
        if code != ok_code:
            raise ApiError(code=code, message=result.get("message", ""))

        return result

    def homework_query(
        self,
        url: str,
        data: dict[str, Any],
        key: bytes | None = None,
        ok_status: str = "200",
        method: str = "POST",
        content_type: str = "form",
    ) -> dict[str, Any]:
        """知到作业 API 查询（AES-128-CBC + exam_key，无 dateFormate）

        与 zhidao_query 的区别：
        - 不发送 dateFormate 字段
        - 使用 exam_key 加密
        - 检查 status 字段（"200"）而非 code 字段
        """
        if key is None:
            key = self.crypto.key_bytes("exam_key")
        iv = self.crypto.key_bytes("iv")

        cipher = Cipher(key, iv)
        encrypted_data = cipher.encrypt(json.dumps(data))

        form_data: dict[str, Any] = {
            "secretStr": encrypted_data,
        }

        result = self.api_query(url, data=form_data, method=method, content_type=content_type)

        status = result.get("status", "")
        if status != ok_status:
            raise ApiError(code=int(status) if status.isdigit() else -1, message=result.get("msg", ""))

        return result

    def homework_redo(
        self,
        recruit_id: str,
        exam_id: str,
        course_id: int,
    ) -> dict[str, Any]:
        """重做作业（saveCourseTran），重置已提交作业的状态

        已提交的作业（state=4）直接调用 doHomework 会返回"试卷已提交"，
        需要先调用此接口重置状态，然后才能重新答题。

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            course_id: 课程 ID
        """
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/student/saveCourseTran"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "description": "",
            "courseId": course_id,
        }
        return self.homework_query(url, data)

    def homework_do(
        self,
        recruit_id: str,
        exam_id: str,
        student_exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """开始做作业（doHomework），获取题目详情（含 eid）"""
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/student/doHomework"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "studentExamId": student_exam_id,
            "schoolId": school_id,
            "courseId": course_id,
        }
        return self.homework_query(url, data)

    def homework_save_answer(
        self,
        answer_item: dict[str, Any],
        recruit_id: str,
    ) -> dict[str, Any]:
        """保存单题答案（saveStudentAnswer）

        Args:
            answer_item: 答案项字典（含 examId/eid/answer/questionType 等）
            recruit_id: 招募 ID
        """
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/answer/saveStudentAnswer"
        data = {
            "stuExamAnswer": json.dumps([answer_item]),
            "recruitId": recruit_id,
        }
        return self.homework_query(url, data)

    def homework_submit(
        self,
        recruit_id: str,
        exam_id: str,
        stu_exam_id: str,
        achieve_count: int,
    ) -> dict[str, Any]:
        """提交作业（submit）

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            stu_exam_id: 作业 ID
            achieve_count: 已答题数目

        Returns:
            含 rt.score（得分）的响应
        """
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/answer/submit"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "stuExamId": stu_exam_id,
            "achieveCount": str(achieve_count),
        }
        return self.homework_query(url, data)

    def homework_look(
        self,
        recruit_id: str,
        student_exam_id: str,
        exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """查看已提交作业（lookHomework），获取题目详情（数字型 id）"""
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/student/lookHomework"
        data = {
            "recruitId": recruit_id,
            "studentExamId": student_exam_id,
            "examId": exam_id,
            "schoolId": school_id,
            "courseId": course_id,
        }
        return self.homework_query(url, data)

    def homework_get_answer(
        self,
        recruit_id: str,
        stu_exam_id: str,
        exam_id: str,
        school_id: str,
        course_id: str,
        question_ids: list[int],
    ) -> dict[str, Any]:
        """获取学生答案信息（getStuAnswerInfo，数字型 id 为键）

        用于查看已提交作业时获取每题对错信息。
        """
        url = f"{self.urls.homework}/studentExam/gateway/t/v1/answer/getStuAnswerInfo"
        data = {
            "recruitId": recruit_id,
            "stuExamId": stu_exam_id,
            "examId": exam_id,
            "schoolId": school_id,
            "courseId": course_id,
            "questionIds": ",".join(str(qid) for qid in question_ids),
        }
        return self.homework_query(url, data)

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
        """调用 AI 解析 run API（SSE 流式），返回完整解析内容

        使用 ai-course-assistant-api 域名，明文 JSON POST，SSE 流式响应。
        与作业 API 不同：不加密、不同域名、流式响应。

        Args:
            course_id: 课程 ID
            recruit_id: 招募 ID
            question_id: 题目数字型 ID（来自 lookHomework 的 id 字段）
            thread_id: 会话线程 ID（首次为空字符串）
            run_id: 运行 ID（首次为 None）
            regenerate: 是否重新生成
            timeout: 请求超时时间（秒）

        Returns:
            AI 解析完整文本内容
        """
        client = self._get_client()

        # 先获取 userId
        user_id = 0
        try:
            info_url = f"{self.urls.ai_analysis}/api/v1/user/info"
            info_resp = client.get(
                info_url,
                params={
                    "userId": "0",
                    "courseId": str(course_id),
                    "recruitId": recruit_id,
                },
            )
            info_data = info_resp.json()
            user_id = int(info_data.get("data", {}).get("userId", 0))
        except Exception as e:
            logger.warning(f"获取 AI 解析 userId 失败: {e}")

        if not user_id:
            logger.warning("无法获取 AI 解析 userId，跳过 AI 解析")
            return ""

        run_url = f"{self.urls.ai_analysis}/api/v1/question/analysis/thread/run"
        run_data = {
            "courseId": str(course_id),
            "recruitId": recruit_id,
            "userRole": "STUDENT",
            "userId": user_id,
            "threadId": thread_id,
            "questionId": question_id,
            "regenerate": regenerate,
            "runId": run_id,
        }

        full_content: list[str] = []

        try:
            with client.stream("POST", run_url, json=run_data, timeout=timeout) as resp:
                if resp.status_code != 200:
                    logger.warning(f"AI 解析 API 返回状态码 {resp.status_code}")
                    return ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            data = json.loads(data_str)
                            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                            is_stop = data.get("stop", False)
                            if content:
                                full_content.append(content)
                            if is_stop:
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"AI 解析请求失败: {e}")
            return ""

        return "".join(full_content)

    def exam_sso_login(self) -> None:
        """通过 CAS SSO 认证 studentexam-api 域名

        studentexam-api 不像 studyservice-api 有 /login/gologin，
        需要通过 passport CAS SSO 获取认证。
        流程: 访问 passport/cas/login?service=xxx → 302 带 ticket → ticket 验证设置 session cookie

        Raises:
            ZhsError: CAS 认证失败（CASTGC 过期，需要重新登录）
        """
        client = self._get_client()
        service_url = f"{self.urls.homework}/studentExam/gateway/t/v1/student/getStudentHomework"
        cas_login_url = f"{self.urls.passport}/cas/login?service={service_url}"

        resp = client.get(cas_login_url, follow_redirects=False)
        if resp.status_code == 302:
            ticket_url = resp.headers.get("location", "")
            if "ticket=" in ticket_url:
                client.get(ticket_url, follow_redirects=True)
                logger.debug("CAS SSO 认证成功")
                return
            # 302 但无 ticket，可能是重定向到登录页
            logger.warning(f"CAS SSO 302 但无 ticket: {ticket_url[:100]}")
        elif resp.status_code == 200:
            logger.warning("CAS SSO 返回 200，CASTGC 可能已过期")

        raise ZhsError(
            "CAS SSO 认证失败，请重新登录: zhs login\n  原因: CASTGC cookie 已过期，studentexam-api 无法认证"
        )

    def close(self) -> None:
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None

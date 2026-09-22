"""知到考试业务 API

提供知到考试相关的 API 方法：
- get_student_final_exam: 获取考试列表（getStudentFinalExam）
- get_save_answer_lock_result: 查询答案是否锁死（getSaveAnswerLockResult）
- get_login_school_info: 获取当前登录用户学校 ID（getLoginSchoolInfo）
- do_exam: 开始考试（doExam），获取题目详情
- save_student_answer: 保存单题答案（saveStudentAnswer）
- submit_exam: 提交考试（submit）

加密策略：
- getStudentFinalExam / doExam / submit_exam 使用 zhidao_exam 策略（taurusexam-api 域名）
- getSaveAnswerLockResult / getLoginSchoolInfo / saveStudentAnswer 使用 homework 策略
  （studentexam-api 域名，与作业同域）
两者加密参数相同（exam_key, 无 dateFormate, status="200"），仅 base_url 不同。

注意：位置验证（queryIsOpenLocation/createEncodeImage/queryEncodeImageIsPass）
因验证码无法自动化，已移除。仅保留锁状态判断 + getLoginSchoolInfo（获取 schoolId），
锁死则跳过该考试。考试无心跳机制（已抓包确认）。

关键差异（考试 vs 作业 saveStudentAnswer）：
- 考试额外发送 ``source=1`` 明文字段（作业不发送）
- 考试 ``examType=1``（整数），作业 ``examType=""``（空字符串）
"""

import json
from typing import Any

from zhs.api.encrypted_query import EncryptedQuery


class ZhidaoExamApi:
    """知到考试业务 API

    通过 EncryptedQuery 调用知到考试相关接口。
    - 考试列表/做题接口基于 config.urls.taurusexam
    - 答案锁检查/学校信息/保存答案接口基于 config.urls.homework（与作业同域）
    """

    def __init__(self, query: EncryptedQuery) -> None:
        self._query = query
        self._base = query._http.urls.taurusexam
        self._hw_base = query._http.urls.homework

    def get_student_final_exam(
        self,
        course_id: int,
        recruit_id: str,
        flag: int,
    ) -> list[dict[str, Any]]:
        """获取考试列表（getStudentFinalExam）

        Args:
            course_id: 课程 ID
            recruit_id: 招募 ID（课程注册 ID）
            flag: 1=未完成考试, 0=已完成考试

        Returns:
            rt 数组（考试列表），每个元素为考试信息字典
        """
        url = f"{self._base}/taurusExam/gateway/t/v1/student/getStudentFinalExam"
        data = {
            "courseId": course_id,
            "recruitId": recruit_id,
            "flag": flag,
        }
        result = self._query.query("zhidao_exam", url, data)
        rt: list[dict[str, Any]] = result["rt"]
        return rt

    def get_save_answer_lock_result(
        self,
        exam_id: str,
        recruit_id: str,
    ) -> int:
        """查询答案是否锁死（getSaveAnswerLockResult）

        Args:
            exam_id: 考试 ID
            recruit_id: 招募 ID

        Returns:
            rt.state: 0=未锁死（可以答题），1=锁死（跳过该考试）
        """
        url = f"{self._hw_base}/studentExam/gateway/t/v1/answer/getSaveAnswerLockResult"
        data = {"examId": exam_id, "recruitId": recruit_id}
        result = self._query.query("homework", url, data)
        rt: dict[str, Any] = result["rt"]
        state: int = rt["state"]
        return state

    def get_login_school_info(self) -> str:
        """获取当前登录用户学校 ID（getLoginSchoolInfo）

        无需任何参数，服务端根据登录态返回用户所在学校信息。
        用于 doExam / saveStudentAnswer 的 schoolId 参数。

        部分用户未绑定学校，API 返回 rt=null 或 schoolId=null，
        此时返回空字符串（doExam/saveStudentAnswer 允许 schoolId 为空）。

        Returns:
            学校 ID 字符串（如 "625"），未绑定时返回 ""
        """
        url = f"{self._hw_base}/studentExam/gateway/t/v1/exam/getLoginSchoolInfo"
        result = self._query.query("homework", url, {})
        rt: Any = result.get("rt")
        if not rt:
            return ""
        school_id: Any = rt.get("schoolId")
        if school_id is None:
            return ""
        return str(school_id)

    def do_exam(
        self,
        recruit_id: str,
        exam_id: str,
        student_exam_id: str,
        school_id: str,
        course_id: str,
        device_id: str = "",
    ) -> dict[str, Any]:
        """开始考试（doExam），获取题目详情（含 eid）

        使用 zhidao_exam 策略（taurusexam-api 域名）。
        响应结构与知到作业 doHomework 一致（rt.examBase.workExamParts[].questionDtos[]）。

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID（来自 getStudentFinalExam 的 examId）
            student_exam_id: 学生考试记录 ID（来自 getStudentFinalExam 的 id）
            school_id: 学校 ID（来自 getLoginSchoolInfo）
            course_id: 课程 ID
            device_id: 设备 ID（通常为空字符串）

        Returns:
            rt 对象（含 examBase.workExamParts 题目列表）
        """
        url = f"{self._base}/taurusExam/gateway/t/v1/student/doExam"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "studentExamId": student_exam_id,
            "schoolId": school_id,
            "courseId": course_id,
            "deviceId": device_id,
        }
        result = self._query.query("zhidao_exam", url, data)
        rt: dict[str, Any] = result["rt"]
        return rt

    def save_student_answer(
        self,
        answer_item: dict[str, Any],
        recruit_id: str,
    ) -> dict[str, Any]:
        """保存单题答案（saveStudentAnswer）

        使用 homework 策略（studentexam-api 域名）。
        与知到作业 saveStudentAnswer 的关键差异：
        - 额外发送 ``source=1`` 明文字段（与 secretStr 一起发送，不加密）
        - answer_item 中 ``examType=1``（整数），作业为 ``""``（空字符串）

        Args:
            answer_item: 答案项字典（含 examId/eid/answer/questionType/examType 等）
            recruit_id: 招募 ID

        Returns:
            rt 对象（含 ``statu`` 字段，注意 API 字段名拼写为 "statu" 非 "status"）
        """
        url = f"{self._hw_base}/studentExam/gateway/t/v1/answer/saveStudentAnswer"
        data = {
            "stuExamAnswer": json.dumps([answer_item]),
            "recruitId": recruit_id,
        }
        # source=1 作为明文字段发送（考试特有，作业不发送）
        result = self._query.query("homework", url, data, extra_fields={"source": "1"})
        rt: dict[str, Any] = result["rt"]
        return rt

    def submit_exam(
        self,
        recruit_id: str,
        exam_id: str,
        stu_exam_id: str,
        achieve_count: str,
    ) -> dict[str, Any]:
        """提交考试（submit）

        使用 zhidao_exam 策略（taurusexam-api 域名）。
        默认不提交，仅当用户指定 ``--submit`` 时调用。

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            stu_exam_id: 学生考试记录 ID
            achieve_count: 已答题数量（字符串型，如 "80"）

        Returns:
            rt 对象（含 ``msg`` 和 ``statu`` 字段，statu="1" 表示提交成功）

        响应示例::

            {"rt": {"msg": "提交成功", "statu": "1"}, "status": "200"}
        """
        url = f"{self._base}/taurusExam/gateway/t/v1/answer/submit"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "stuExamId": stu_exam_id,
            "achieveCount": achieve_count,
        }
        result = self._query.query("zhidao_exam", url, data)
        rt: dict[str, Any] = result["rt"]
        return rt

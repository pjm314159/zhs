"""知到作业业务 API

从原 ZhsSession 迁移的 6 个知到作业业务方法：
- homework_redo: 重做作业（saveCourseTran）
- homework_do: 开始做作业（doHomework）
- homework_save_answer: 保存单题答案（saveStudentAnswer）
- homework_submit: 提交作业（submit）
- homework_look: 查看已提交作业（lookHomework）
- homework_get_answer: 获取学生答案信息（getStuAnswerInfo）

所有方法使用 homework 加密策略（exam_key, 无 dateFormate, status="200"）。
"""

import json
from typing import Any

from zhs.api.encrypted_query import EncryptedQuery


class ZhidaoHomeworkApi:
    """知到作业业务 API

    通过 EncryptedQuery 调用知到作业相关接口。
    所有 URL 基于 config.urls.homework。
    """

    def __init__(self, query: EncryptedQuery) -> None:
        self._query = query
        self._base = query._http.urls.homework

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
        url = f"{self._base}/studentExam/gateway/t/v1/student/saveCourseTran"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "description": "",
            "courseId": course_id,
        }
        return self._query.query("homework", url, data)

    def homework_do(
        self,
        recruit_id: str,
        exam_id: str,
        student_exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """开始做作业（doHomework），获取题目详情（含 eid）"""
        url = f"{self._base}/studentExam/gateway/t/v1/student/doHomework"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "studentExamId": student_exam_id,
            "schoolId": school_id,
            "courseId": course_id,
        }
        return self._query.query("homework", url, data)

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
        url = f"{self._base}/studentExam/gateway/t/v1/answer/saveStudentAnswer"
        data = {
            "stuExamAnswer": json.dumps([answer_item]),
            "recruitId": recruit_id,
        }
        return self._query.query("homework", url, data)

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
        url = f"{self._base}/studentExam/gateway/t/v1/answer/submit"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "stuExamId": stu_exam_id,
            "achieveCount": str(achieve_count),
        }
        return self._query.query("homework", url, data)

    def homework_look(
        self,
        recruit_id: str,
        student_exam_id: str,
        exam_id: str,
        school_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """查看已提交作业（lookHomework），获取题目详情（数字型 id）"""
        url = f"{self._base}/studentExam/gateway/t/v1/student/lookHomework"
        data = {
            "recruitId": recruit_id,
            "studentExamId": student_exam_id,
            "examId": exam_id,
            "schoolId": school_id,
            "courseId": course_id,
        }
        return self._query.query("homework", url, data)

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
        url = f"{self._base}/studentExam/gateway/t/v1/answer/getStuAnswerInfo"
        data = {
            "recruitId": recruit_id,
            "stuExamId": stu_exam_id,
            "examId": exam_id,
            "schoolId": school_id,
            "courseId": course_id,
            "questionIds": ",".join(str(qid) for qid in question_ids),
        }
        return self._query.query("homework", url, data)

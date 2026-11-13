"""知识图谱课章节测验 API

提供知识图谱课章节测验（知识点掌握度）相关的 API 方法：
- start_exam: 开始答题，获取题目列表
- submit_exam: 提交答案
- get_mastery_info: 获取掌握度信息（正确率、提升率）

这些接口挂在知识点（knowledgeId）下，与图谱课学习接口同域 aistudy.zhihuishu.com，
但路径前缀为 /gateway/t/v1/exam/（而非学习接口的 /gateway/t/v1/learning/）。

加密策略：
- start_exam / get_mastery_info 使用 aistudy 策略（GET + secretStr 加密）
- submit_exam 使用 map_json 策略（POST 明文 JSON）

与现有实现的差异：
- zhidao/exam/: 知到共享课期末考试（getStudentFinalExam），课程级别
- ai/homework.py: AI 课程知识点作业（query_homework），不支持知识图谱课
- 本模块: 知识图谱课知识点章节测验，节点级别
"""

import time
from typing import Any

from zhs.api.encrypted_query import EncryptedQuery


class ZhidaoKgExamApi:
    """知识图谱课章节测验 API

    通过 EncryptedQuery 调用知识图谱课章节测验相关接口。
    所有接口基于 config.urls.aistudy（与图谱课学习接口同域）。
    """

    def __init__(self, query: EncryptedQuery) -> None:
        self._query = query
        self._base = query._http.urls.aistudy

    def start_exam(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
    ) -> dict[str, Any]:
        """开始章节测验，获取题目列表

        Args:
            recruit_id: 招募 ID（课程注册 ID）
            exam_id: 考试 ID（来自章节树节点的 examId 字段）
            knowledge_id: 知识点 ID（章节树节点的 idHash）

        Returns:
            data 对象，包含：
            - examId: 考试 ID
            - knowledgeId: 知识点 ID
            - kgSecretStr: 知识图谱专用加密串（用途待确认）
            - questions: 题目列表
              - questionId: 题目 ID
              - questionName: 题目内容（HTML）
              - questionType: 题型（1=单选，2=多选，14=判断）
              - optionVos: 选项列表
                - id: 选项 ID
                - name: 选项内容（HTML）
                - isCorrect: 是否正确（答题前为 null）
              - analysis: 题目解析（HTML）
        """
        url = f"{self._base}/gateway/t/v1/exam/start"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "knowledgeId": knowledge_id,
        }
        result = self._query.query("aistudy", url, data)
        return result["data"]

    def submit_exam(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
        answers: list[dict[str, Any]],
    ) -> bool:
        """提交章节测验答案

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            knowledge_id: 知识点 ID
            answers: 答案列表，每个元素为：
                - questionId: 题目 ID
                - answer: 答案
                  - 单选/判断：选项 ID（整数）
                  - 多选：逗号分隔的选项 ID（字符串，如 "id1,id2,id3"）

        Returns:
            提交是否成功（data 为 true 表示成功）
        """
        url = f"{self._base}/gateway/t/v1/exam/submit"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "knowledgeId": knowledge_id,
            "answerVos": answers,
            "dateFormate": int(time.time() * 1000),
        }
        # 使用 map_json 策略（POST 明文 JSON）
        result = self._query.query("map_json", url, data)
        return result.get("data") is True

    def get_mastery_info(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
    ) -> dict[str, Any]:
        """获取掌握度信息

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            knowledge_id: 知识点 ID

        Returns:
            data 对象，包含：
            - questionNum: 题目总数
            - correctNum: 答对题数
            - rate: 正确率（字符串，如 "100"）
            - upgradedRate: 提升率（字符串，如 "100"）
        """
        url = f"{self._base}/gateway/t/v1/exam/getAnswerMasteryInfo"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "knowledgeId": knowledge_id,
        }
        result = self._query.query("aistudy", url, data)
        return result["data"]

    def get_error_question_recommend(
        self,
        recruit_id: str,
        exam_id: int,
        knowledge_id: str,
    ) -> Any:
        """获取错题推荐（可选）

        全部答对时返回 null。

        Args:
            recruit_id: 招募 ID
            exam_id: 考试 ID
            knowledge_id: 知识点 ID

        Returns:
            data 对象（全对时为 null）
        """
        url = f"{self._base}/gateway/t/v1/exam/getErrorQuestionRecommend"
        data = {
            "recruitId": recruit_id,
            "examId": exam_id,
            "knowledgeId": knowledge_id,
        }
        result = self._query.query("aistudy", url, data)
        return result.get("data")

"""知到弹窗答题器

ZhidaoQuizzer 提供弹窗题目获取、自动答题、答案提交功能。
所有 URL 从 UrlConfig 获取。
"""

from loguru import logger

from zhs.session import ZhsSession
from zhs.zhidao.models import PopupQuestion, QuestionOption, QuestionPoint


class ZhidaoQuizzer:
    """知到弹窗答题器"""

    def __init__(self, session: ZhsSession) -> None:
        self._session = session

    def answer_question(self, question: PopupQuestion) -> str:
        """自动选择正确答案（result == '1' 的选项 ID，逗号分隔）"""
        correct_ids = [str(opt.id) for opt in question.question_options if opt.result == "1"]
        return ",".join(correct_ids)

    def load_video_pointer_info(
        self,
        rac_id: str,
        video_id: int,
        lesson_id: int = 0,
        lesson_video_id: int = 0,
        recruit_id: int = 0,
        course_id: int = 0,
    ) -> list[QuestionPoint]:
        """获取弹窗题目时间点列表"""
        url = f"{self._session.urls.study}/gateway/t/v1/popupAnswer/loadVideoPointerInfo"
        data = {
            "lessonId": lesson_id,
            "lessonVideoId": lesson_video_id,
            "recruitId": recruit_id,
            "courseId": course_id,
        }
        result = self._session.zhidao_query(url, data)
        points_data = result.get("data", {}).get("questionPoint") or []
        return [QuestionPoint.model_validate(p) for p in points_data]

    def get_popup_exam(
        self,
        rac_id: str,
        video_id: int,
        question_ids: list[int] | str,
        lesson_id: int = 0,
        lesson_video_id: int = 0,
    ) -> PopupQuestion:
        """获取弹窗题目详情"""
        # question_ids 可能是字符串（逗号分隔），转为列表
        if isinstance(question_ids, str):
            question_ids = [int(x) for x in question_ids.split(",") if x.strip()]
        url = f"{self._session.urls.study}/gateway/t/v1/popupAnswer/lessonPopupExam"
        data = {
            "lessonId": lesson_id,
            "lessonVideoId": lesson_video_id,
            "questionIds": question_ids,
        }
        result = self._session.zhidao_query(url, data)
        dtos = result.get("data", {}).get("lessonTestQuestionUseInterfaceDtos", [])
        if not dtos:
            return PopupQuestion(question_id=0, question_options=[])
        q_data = dtos[0].get("testQuestion", {})
        options_data = q_data.get("questionOptions", [])
        options = [QuestionOption.model_validate(o) for o in options_data]
        return PopupQuestion(
            question_id=q_data.get("questionId", 0),
            question_options=options,
        )

    def save_answer(
        self,
        rac_id: str,
        video_id: int,
        question_id: int,
        answer: str,
        lesson_id: int = 0,
        lesson_video_id: int = 0,
        recruit_id: int = 0,
        course_id: int = 0,
    ) -> None:
        """提交弹题答案"""
        url = f"{self._session.urls.study}/gateway/t/v1/popupAnswer/saveLessonPopupExamSaveAnswer"
        data = {
            "courseId": course_id,
            "recruitId": recruit_id,
            "testQuestionId": question_id,
            "isCurrent": "1",
            "lessonId": lesson_id,
            "lessonVideoId": lesson_video_id,
            "answer": answer,
            "testType": 0,
        }
        self._session.zhidao_query(url, data)
        logger.debug(f"Saved answer for question {question_id}: {answer}")

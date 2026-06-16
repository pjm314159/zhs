"""AI 课程数据模型"""

from pydantic import BaseModel, Field


class KnowledgePoint(BaseModel):
    """知识点"""

    model_config = {"populate_by_name": True}

    knowledge_id: int = Field(alias="knowledgeId")
    knowledge_name: str = Field(alias="knowledgeName")
    study_progress: int = Field(default=0, alias="studyProgress")


class Theme(BaseModel):
    """主题"""

    model_config = {"populate_by_name": True}

    theme_name: str = Field(alias="themeName")
    knowledge_list: list[KnowledgePoint] = Field(default=[], alias="knowledgeList")


class AiCourseInfo(BaseModel):
    """AI 课程信息"""

    model_config = {"populate_by_name": True}

    course_name: str = Field(alias="courseName")
    cake_theme_list: list[Theme] = Field(default=[], alias="cakeThemeList")


class ResourceDetail(BaseModel):
    """资源详情"""

    model_config = {"populate_by_name": True}

    resources_uid: int = Field(alias="resourcesUid")
    resources_name: str = Field(alias="resourcesName")
    resources_type: int = Field(alias="resourcesType")
    resources_distribute_type: int = Field(alias="resourcesDistributeType")
    resources_url: str = Field(default="", alias="resourcesUrl")
    resources_file_id: int = Field(default=0, alias="resourcesFileId")


class Resource(BaseModel):
    """资源"""

    model_config = {"populate_by_name": True}

    study_status: int = Field(default=0, alias="studyStatus")
    resources_detail: ResourceDetail = Field(alias="resourcesDetail")


class ExamInfo(BaseModel):
    """考试信息"""

    model_config = {"populate_by_name": True}

    exam_test_id: int = Field(alias="examTestId")
    paper_id: int = Field(alias="paperId")
    mastery_score: int = Field(default=0, alias="masteryScore")


class QuestionSheet(BaseModel):
    """试卷题目"""

    model_config = {"populate_by_name": True}

    question_id: int = Field(alias="questionId")
    version: int = Field(default=1, alias="version")


class OptionVo(BaseModel):
    """选项"""

    model_config = {"populate_by_name": True}

    id: int
    content: str = ""
    is_correct: int = Field(default=0, alias="isCorrect")


class UserAnswerVo(BaseModel):
    """用户答案"""

    model_config = {"populate_by_name": True}

    is_correct: int = Field(default=0, alias="isCorrect")
    answer: str = Field(default="", alias="answer")


class QuestionContent(BaseModel):
    """题目内容"""

    model_config = {"populate_by_name": True}

    id: int
    content: str
    question_type: int = Field(alias="questionType")
    option_vos: list[OptionVo] = Field(default=[], alias="optionVos")
    user_answer_vos: list[UserAnswerVo] = Field(default=[], alias="userAnswerVo")
    version: int = Field(default=1, alias="version")


class AnswerCache(BaseModel):
    """答案缓存"""

    version: int = 1
    question: str = ""
    answer: str = ""
    answer_content: str = ""
    question_dict: dict[str, object] = {}

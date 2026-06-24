"""知到作业数据模型

定义知到作业相关的 pydantic 模型：
- HomeworkItem: 作业列表项（getStudentHomework 返回）
- HomeworkQuestionType: 题型枚举
- HomeworkQuestionOption: 题目选项
- HomeworkQuestion: 题目详情
- HomeworkExamPart: 题目分组
- HomeworkExamBase: 试卷基础信息
- HomeworkDetail: doHomework/lookHomework 返回
- HomeworkAnswerInfo: getStuAnswerInfo 返回的单题信息
- HomeworkCacheEntry: 本地缓存条目
"""

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# 错误选项类型：选择题为 list[int]（一次完整选择），填空题为 list[str]（每空一个元素）
WrongOption = list[int] | list[str]


class HomeworkQuestionType(IntEnum):
    """题型枚举"""

    SINGLE = 1  # 单选题
    MULTI = 2  # 多选题
    FILL = 3  # 填空题
    JUDGE = 14  # 判断题


class HomeworkItem(BaseModel):
    """作业列表项（getStudentHomework 返回）"""

    id: str = Field(description="作业 ID（即 stuExamId）")
    exam_id: str = Field(alias="examId", description="考试 ID")
    state: int = Field(description="状态：1=未提交，4=已提交(需重置)，5=已重置(可做题)")
    score: str | None = Field(default=None, description="得分（未提交时为 null）")
    achieve_count: int | None = Field(default=None, alias="achieveCount", description="已答次数")
    is_marking: int = Field(default=0, alias="isMarking", description="已重做次数")
    achieve: int = Field(default=0, description="达标分数")
    back_num: int = Field(default=3, alias="backNum", description="总计重做次数")
    is_check_answer: int = Field(default=0, alias="isCheckAnswer", description="是否可查看答案(1=可以)")
    course_id: int = Field(alias="courseId", description="课程 ID")
    course_name: str = Field(default="", alias="courseName", description="课程名")
    exam_name: str = Field(default="", alias="examName", description="作业名称")
    cp_order_number: str = Field(default="", alias="cpOrderNumber", description="对应章节")
    chapter_id: int = Field(default=0, alias="chapterId", description="章节 ID")
    chapter_rank: int = Field(default=0, alias="chapterRank", description="章节排序")
    total_score: str = Field(default="0", alias="totalScore", description="总分")
    problem_num: int = Field(default=0, alias="problemNum", description="题目数量")
    is_object: int = Field(default=1, alias="isObject", description="是否客观题")
    start_time: str = Field(default="", alias="startTime", description="开始时间")
    end_date: str = Field(default="", alias="endDate", description="截止时间")

    model_config = {"populate_by_name": True}

    @property
    def remaining_redo(self) -> int:
        """剩余重做次数 = 总计重做次数 - 已重做次数"""
        return max(0, self.back_num - self.is_marking)


class HomeworkQuestionOption(BaseModel):
    """题目选项"""

    id: int = Field(description="选项 ID（保存答案时使用此 ID）")
    content: str = Field(default="", description="选项内容（HTML 格式）")


class HomeworkQuestion(BaseModel):
    """题目详情（doHomework/lookHomework 返回）"""

    eid: str | None = Field(default=None, description="题目加密 ID（doHomework 返回，用于 saveStudentAnswer）")
    id: int | None = Field(
        default=None,
        description="题目数字型 ID（lookHomework 返回，用于 getStuAnswerInfo 和 AI 解析）",
    )
    name: str = Field(default="", description="题目内容（HTML 格式）")
    question_type_id: int = Field(default=0, alias="questionType", description="题型 ID")
    question_options: list[HomeworkQuestionOption] = Field(default=[], alias="questionOptions", description="选项列表")
    question_score: str = Field(default="0", alias="questionScore", description="题目分值")
    result: str | None = Field(default=None, description="正确答案标识")

    model_config = {"populate_by_name": True}

    @field_validator("question_type_id", mode="before")
    @classmethod
    def _parse_question_type(cls, v: Any) -> int:
        """API 返回 questionType: {"id": 1, "name": "单选题"}，需提取 id"""
        if isinstance(v, dict):
            return int(v.get("id", 0))
        return int(v) if v is not None else 0

    @property
    def question_type(self) -> HomeworkQuestionType | None:
        """获取题型枚举值"""
        try:
            return HomeworkQuestionType(self.question_type_id)
        except ValueError:
            return None


class HomeworkExamPart(BaseModel):
    """题目分组"""

    start_sort: int = Field(default=1, alias="startSort", description="起始序号")
    question_count: int = Field(default=0, alias="questionCount", description="题目数量")
    question_dtos: list[HomeworkQuestion] = Field(default=[], alias="questionDtos", description="题目列表")

    model_config = {"populate_by_name": True}


class HomeworkExamBase(BaseModel):
    """试卷基础信息"""

    id: str = Field(description="考试 ID")
    name: str = Field(default="", description="考试名称")
    course_name: str = Field(default="", alias="courseName", description="课程名")
    to_chapter: str = Field(default="", alias="toChapter", description="对应章节")
    problem_num: int = Field(default=0, alias="problemNum", description="题目数量")
    total_score: str = Field(default="0", alias="totalScore", description="总分")
    pont_type: str = Field(default="", alias="pontType", description="成绩类型")
    chapter_id: int = Field(default=0, alias="chapterId", description="章节 ID")
    work_exam_parts: list[HomeworkExamPart] = Field(default=[], alias="workExamParts", description="题目分组列表")

    model_config = {"populate_by_name": True}


class HomeworkDetail(BaseModel):
    """doHomework/lookHomework 返回"""

    exam_base: HomeworkExamBase = Field(alias="examBase", description="试卷基础信息")
    score: str | None = Field(default=None, description="得分")
    state: int | None = Field(default=None, description="状态")

    model_config = {"populate_by_name": True}


class HomeworkAnswerInfo(BaseModel):
    """getStuAnswerInfo/getStuAnswerInfoNew 返回的单题信息"""

    question_id: str = Field(alias="questionId", description="题目 ID（eid 或数字型 id）")
    answer: str = Field(default="", description="已保存的选项 ID（空字符串=未答）")
    is_current: str = Field(default="", alias="isCurrent", description="是否正确：0=错误，1=正确，空=未答")
    score: str = Field(default="", description="得分（未答为空字符串，答错为 0）")
    stu_exam_id: str = Field(default="", alias="stuExamId", description="学生考试记录 ID")

    model_config = {"populate_by_name": True}

    @property
    def is_correct(self) -> bool:
        """是否答对"""
        return self.is_current == "1"

    @property
    def is_wrong(self) -> bool:
        """是否答错"""
        return self.is_current == "0"

    @property
    def is_unanswered(self) -> bool:
        """是否未答"""
        return self.is_current == ""


class HomeworkCacheOption(BaseModel):
    """缓存中的选项信息"""

    id: int = Field(description="选项 ID")
    content: str = Field(default="", description="选项内容")


class HomeworkCacheEntry(BaseModel):
    """本地缓存条目"""

    question_type: int = Field(default=0, alias="questionType", description="题型 ID")
    content: str = Field(default="", description="题目纯文本内容（用于无选项题目的 key 桥接）")
    options: list[HomeworkCacheOption] = Field(default=[], description="选项列表")
    correct_options: list[int] = Field(default=[], alias="correctOptions", description="确认正确的选项 ID 列表")
    wrong_options: list[WrongOption] = Field(
        default=[], alias="wrongOptions", description="错误选择方式列表：选择题为 list[int]，填空题为 list[str]"
    )
    ai_analysis: str | None = Field(default=None, alias="aiAnalysis", description="AI 解析内容")
    last_updated: str = Field(default="", alias="lastUpdated", description="最后更新时间")

    model_config = {"populate_by_name": True}

    @field_validator("wrong_options", mode="before")
    @classmethod
    def _migrate_wrong_options(cls, v: Any) -> Any:
        """迁移旧格式到 list[list[int] | list[str]]

        - 旧扁平 list[int] → list[list[int]]（每个 int 包裹为 [int]）
        - 旧 list[str]（填空题用 / 分隔） → list[list[str]]（按 / 拆分）
        """
        if isinstance(v, list):
            migrated: list[Any] = []
            for item in v:
                if isinstance(item, int):
                    migrated.append([item])
                elif isinstance(item, str):
                    migrated.append(item.split("/"))
                else:
                    migrated.append(item)
            return migrated
        return v

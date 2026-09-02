"""知到考试数据模型

定义知到考试相关的 pydantic 模型：
- ExamInfo: 考试列表项（getStudentFinalExam 返回的 rt 数组元素）
- ExamListResult: 考试列表查询结果（未完成 + 已完成）

与知到作业 HomeworkItem 的主要区别：
- flag 含义不同：考试 flag=1=未完成/0=已完成，作业 flag=1=未提交/2=已提交
- 考试有时限 limitTime（分钟），作业无时限
- 考试有剩余次数 faStudentExamRemainCount，作业用 backNum（重做次数）
- 考试有学生开考/结束时间 studentStartTime/EndTime，作业无
- rt 结构不同：考试为数组，作业为 {result, next, studentHomeworkList}
"""

from typing import Any

from pydantic import BaseModel, Field


class ExamInfo(BaseModel):
    """知到考试信息（来自 getStudentFinalExam 的 rt 数组元素）

    对应 API 字段（驼峰命名）：
    - id → id（学生考试记录 ID，即 stuExamId）
    - examId → exam_id
    - courseId → course_id
    - faStudentExamRemainCount → fa_student_exam_remain_count（剩余考试次数）
    - limitTime → limit_time（考试时限，分钟）
    """

    id: str = Field(description="学生考试记录 ID（即 stuExamId）")
    state: int = Field(description="考试状态：1=未开考，2=已开考未提交，4=已提交")
    score: str | None = Field(default=None, description="得分（未提交时为 None）")
    achieve_count: int = Field(default=0, description="已答次数")
    achieve: int = Field(default=0, description="达标分数")
    fa_student_exam_remain_count: int = Field(default=0, description="剩余考试次数（考试特有，作业无此字段）")
    course_id: int = Field(description="课程 ID")
    course_name: str = Field(description="课程名称")
    exam_id: str = Field(description="考试 ID")
    exam_name: str = Field(description="考试名称")
    problem_num: int = Field(description="题目数量")
    total_score: str = Field(description="总分")
    limit_time: int = Field(description="考试时限（分钟）（考试特有，作业无此字段）")
    start_time: str = Field(description="考试开放开始时间")
    end_date: str = Field(description="考试截止时间")
    student_start_time: str | None = Field(default=None, description="学生开考时间（None=尚未开考）")
    student_end_time: str | None = Field(default=None, description="学生结束时间（None=尚未结束）")
    submit_time: str | None = Field(default=None, description="提交时间（None=尚未提交）")
    progress_type: int = Field(default=0, description="进度类型：0=未开考，2=已开考未提交")

    model_config = {"populate_by_name": True}

    @property
    def is_in_progress(self) -> bool:
        """是否已开考但未提交（state=2 或 progressType=2 或 studentStartTime 非空）"""
        return self.state == 2 or self.progress_type == 2 or self.student_start_time is not None

    @property
    def is_started(self) -> bool:
        """考试是否已开启（studentStartTime 不为空或 progressType=2 或 state=2）"""
        return self.student_start_time is not None or self.state == 2

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ExamInfo":
        """从 API 响应数据构造（驼峰转蛇形）

        Args:
            data: getStudentFinalExam 响应的 rt 数组元素

        Note:
            API 可能返回 achieveCount=null（未答题时），需转换为 0。
        """
        return cls(
            id=data["id"],
            state=data["state"],
            score=data.get("score"),
            achieve_count=data.get("achieveCount") or 0,
            achieve=data.get("achieve") or 0,
            fa_student_exam_remain_count=data.get("faStudentExamRemainCount") or 0,
            course_id=data["courseId"],
            course_name=data["courseName"],
            exam_id=data["examId"],
            exam_name=data["examName"],
            problem_num=data["problemNum"],
            total_score=data["totalScore"],
            limit_time=data["limitTime"],
            start_time=data["startTime"],
            end_date=data["endDate"],
            student_start_time=data.get("studentStartTime"),
            student_end_time=data.get("studentEndTime"),
            submit_time=data.get("submitTime"),
            progress_type=data.get("progressType") or 0,
        )


class ExamListResult(BaseModel):
    """考试列表查询结果

    封装 getStudentFinalExam 两次调用（flag=1 未完成 + flag=0 已完成）的结果。
    """

    uncompleted: list[ExamInfo] = Field(default=[], description="未完成考试列表（flag=1）")
    completed: list[ExamInfo] = Field(default=[], description="已完成考试列表（flag=0）")

    model_config = {"populate_by_name": True}

    @property
    def all(self) -> list[ExamInfo]:
        """所有考试（未完成 + 已完成）"""
        return self.uncompleted + self.completed

    @property
    def pending(self) -> list[ExamInfo]:
        """待处理考试：未开考(state=1)或已开考未提交(state=2)，且考试未结束(studentEndTime为空)"""
        return [e for e in self.uncompleted if e.state in (1, 2) and e.student_end_time is None]

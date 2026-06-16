"""知到课程数据模型

定义知到共享课程相关的 pydantic 模型：
- CourseInfo: 课程基本信息
- ZhidaoCourse: 知到课程（含 recruitAndCourseId alias）
- VideoChapter / VideoLesson / VideoSmallLesson: 章节树
- QuestionPoint / PopupQuestion / QuestionOption: 弹窗题目
- ZhidaoContext: 课程上下文（不含 cookies/headers）
"""

from pydantic import BaseModel, Field


class CourseInfo(BaseModel):
    """课程基本信息"""

    course_id: int = Field(alias="courseId")
    name: str
    en_name: str | None = Field(default=None, alias="enName")

    model_config = {"populate_by_name": True}


class ZhidaoCourse(BaseModel):
    """知到课程"""

    secret: str = Field(alias="recruitAndCourseId")
    course_name: str = Field(alias="courseName")
    course_info: CourseInfo | None = Field(default=None, alias="courseInfo")
    recruit_id: int | None = Field(default=None, alias="recruitId")

    model_config = {"populate_by_name": True}


class VideoSmallLesson(BaseModel):
    """子视频"""

    video_id: int = Field(alias="videoId")
    id: int = 0
    name: str = ""
    lesson_id: int = Field(default=0, alias="lessonId")
    chapter_id: int = Field(default=0, alias="chapterId")
    video_sec: int = Field(default=0, alias="videoSec")
    watch_state: int = Field(default=0, alias="watchState")
    study_total_time: int = Field(default=0, alias="studyTotalTime")

    model_config = {"populate_by_name": True}


class VideoLesson(BaseModel):
    """课时"""

    id: int
    name: str
    lesson_id: int = Field(default=0, alias="lessonId")
    video_id: int = Field(default=0, alias="videoId")
    chapter_id: int = Field(default=0, alias="chapterId")
    video_sec: int = Field(default=0, alias="videoSec")
    video_small_lessons: list[VideoSmallLesson] = Field(default=[], alias="videoSmallLessons")
    watch_state: int = Field(default=0, alias="watchState")
    study_total_time: int = Field(default=0, alias="studyTotalTime")

    model_config = {"populate_by_name": True}


class VideoChapter(BaseModel):
    """章节"""

    id: int
    name: str
    video_lessons: list[VideoLesson] = Field(default=[], alias="videoLessons")

    model_config = {"populate_by_name": True}


class QuestionPoint(BaseModel):
    """弹窗题目时间点"""

    time_sec: int = Field(alias="timeSec")
    question_ids: list[int] | str = Field(alias="questionIds")

    model_config = {"populate_by_name": True}


class QuestionOption(BaseModel):
    """题目选项"""

    id: int
    content: str = ""
    result: str = ""


class PopupQuestion(BaseModel):
    """弹窗题目详情"""

    question_id: int = Field(alias="questionId")
    question_options: list[QuestionOption] = Field(default=[], alias="questionOptions")

    model_config = {"populate_by_name": True}


class ZhidaoContext(BaseModel):
    """知到课程上下文（缓存）

    cookies 和 headers 不放入模型，由 session 管理。
    """

    course: ZhidaoCourse
    chapters: list[VideoChapter]
    videos: dict[int, VideoSmallLesson]
    course_id: int = 0
    fucked_time: int = 0

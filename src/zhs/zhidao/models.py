"""知到课程数据模型

定义知到共享课程相关的 pydantic 模型：
- CourseInfo: 课程基本信息
- ZhidaoCourse: 知到课程（含 recruitAndCourseId alias）
- VideoChapter / VideoLesson / VideoSmallLesson: 章节树
- QuestionPoint / PopupQuestion / QuestionOption: 弹窗题目
- ZhidaoContext: 课程上下文（不含 cookies/headers）
"""

from typing import Literal

from pydantic import BaseModel, Field

# queryCourse.courseInfo.courseMode 的取值：2 为新版知识图谱课
MAP_COURSE_MODE = 2


class CourseInfo(BaseModel):
    """课程基本信息

    course_mode 是新旧两套共享课的版本标识（抓包确认）：
    2 = 新版知识图谱课（aistudy / share-course-map），其余 = 旧版 videolist 课。
    注意不能用 queryCourseMapInfo 是否返回 mapStr 判断：旧版课也会返回 mapStr。
    """

    course_id: int = Field(alias="courseId")
    name: str
    course_mode: int | None = Field(default=None, alias="courseMode")

    model_config = {"populate_by_name": True}

    @property
    def is_map_course(self) -> bool:
        """是否为新版知识图谱课"""
        return self.course_mode == MAP_COURSE_MODE


class ZhidaoCourse(BaseModel):
    """知到课程"""

    secret: str = Field(alias="recruitAndCourseId")
    course_name: str = Field(alias="courseName")
    course_info: CourseInfo | None = Field(default=None, alias="courseInfo")
    recruit_id: int | None = Field(default=None, alias="recruitId")
    course_id: int = Field(default=0, alias="courseId")
    # 课程学习截止时间（毫秒时间戳，来自 queryShareCourseInfo；超过后学习不记进度）
    course_end_time: int | None = Field(default=None, alias="courseEndTime")
    # 是否有学习习惯分（来自 queryCourse；True 表示需要分天学，False 可以一次刷完）
    has_habbit_score: bool | None = Field(default=None, alias="hasHabbitScore")

    model_config = {"populate_by_name": True}


def extract_course_id(course: ZhidaoCourse) -> int:
    """提取知到课程的数字 courseId

    课程列表接口中 courseId 可能出现在两处：顶层 `courseId` 与 `courseInfo.courseId`。
    部分课程顶层为 0，真实 ID 只在 `courseInfo` 中。

    Returns:
        第一个大于 0 的 courseId；都取不到时返回 0
    """
    if course.course_id > 0:
        return course.course_id
    if course.course_info is not None and course.course_info.course_id > 0:
        return course.course_info.course_id
    return 0


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

    mode="map" 表示新版共享课（知识图谱）：章节树来自 aistudy 的
    kgCourseTreeInfoList，视频资源来自 share-course-map 的
    queryNodeDescription，进度上报走 saveUserStudyProcess。
    """

    course: ZhidaoCourse
    chapters: list[VideoChapter]
    videos: dict[int, VideoSmallLesson]
    course_id: int = 0
    fucked_time: int = 0
    mode: Literal["classic", "map"] = "classic"
    map_chapters: list["MapChapter"] = Field(default_factory=list)
    map_str: str = ""
    map_hash: str = ""


class MapLesson(BaseModel):
    """知识图谱节点（课时或子课时）

    叶子节点才挂视频资源；父节点 sourceNum/finishNum 可能为 null。
    """

    id_hash: str = Field(alias="idHash")
    id_str: str = Field(alias="idStr")
    name: str = ""
    source_num: int | None = Field(default=None, alias="sourceNum")
    finish_num: int | None = Field(default=None, alias="finishNum")
    # freeExam=2 且 haveDone=1 表示该节点可以免考；章节树上这两个字段常为 null
    free_exam: int | None = Field(default=None, alias="freeExam")
    have_done: int | None = Field(default=None, alias="haveDone")
    small_lessons: list["MapLesson"] = Field(default_factory=list, alias="smallLessons")
    chapter_hash: str = ""
    chapter_name: str = ""

    model_config = {"populate_by_name": True}

    def leaves(self) -> list["MapLesson"]:
        """展开为叶子节点列表（没有子课时时返回自身）"""
        if not self.small_lessons:
            return [self]
        result: list[MapLesson] = []
        for child in self.small_lessons:
            result.extend(child.leaves())
        return result


class MapChapter(BaseModel):
    """知识图谱章节"""

    id_hash: str = Field(alias="idHash")
    id_str: str = Field(alias="idStr")
    name: str = ""
    lessons: list[MapLesson] = Field(default_factory=list, alias="lessons")

    model_config = {"populate_by_name": True}

    def leaf_nodes(self) -> list[MapLesson]:
        """展开本章所有叶子节点，并回填章节信息"""
        result: list[MapLesson] = []
        for lesson in self.lessons:
            for leaf in lesson.leaves():
                leaf.chapter_hash = self.id_hash
                leaf.chapter_name = self.name
                result.append(leaf)
        return result


class MapResource(BaseModel):
    """知识图谱节点下的资源（视频/课件）"""

    id_hash: str = Field(default="", alias="idHash")
    id_str: str = Field(default="", alias="idStr")
    file_id: str = Field(default="", alias="resourcesFileId")
    name: str = Field(default="", alias="resourcesName")
    suffix: str = Field(default="", alias="resourcesSuffix")
    resources_time: str = Field(default="", alias="resourcesTime")
    url: str = Field(default="", alias="resourcesUrl")
    # 0=选学资源。上报进度会被服务端以 2025「禁止选学资源提交进度」拒绝
    sync_type: int | None = Field(default=None, alias="resourcesSyncType")
    data_type: int | None = Field(default=None, alias="resourcesDataType")

    model_config = {"populate_by_name": True}

    @property
    def duration(self) -> int:
        """视频时长（秒），非视频资源返回 0"""
        try:
            return int(self.resources_time)
        except (TypeError, ValueError):
            return 0

    @property
    def is_video(self) -> bool:
        return self.duration > 0

    @property
    def is_elective(self) -> bool:
        """是否为选学资源（不计入课程进度，上报会被拒绝）"""
        return self.sync_type == 0

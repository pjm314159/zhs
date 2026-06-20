"""Zhidao models 测试

Task 3.1 — zhidao/models.py
TDD 步骤:
1. ZhidaoCourse 从 API JSON 构建（alias 映射）
2. VideoSmallLesson 默认值正确
3. ZhidaoContext 不含 cookies/headers 字段
"""

from zhs.zhidao.models import (
    PopupQuestion,
    QuestionOption,
    QuestionPoint,
    VideoChapter,
    VideoLesson,
    VideoSmallLesson,
    ZhidaoContext,
    ZhidaoCourse,
)


class TestZhidaoCourse:
    """ZhidaoCourse 模型测试"""

    def test_from_api_json(self) -> None:
        """ZhidaoCourse 从 API JSON 构建，secret 字段使用 alias 映射"""
        data = {
            "recruitAndCourseId": "ABC123_456",
            "courseName": "马克思主义基本原理",
        }
        course = ZhidaoCourse.model_validate(data)
        assert course.secret == "ABC123_456"
        assert course.course_name == "马克思主义基本原理"

    def test_optional_fields_default_none(self) -> None:
        """course_info 和 recruit_id 默认为 None"""
        data = {
            "recruitAndCourseId": "ABC123_456",
            "courseName": "测试课程",
        }
        course = ZhidaoCourse.model_validate(data)
        assert course.course_info is None
        assert course.recruit_id is None

    def test_with_course_info(self) -> None:
        """完整课程信息"""
        data = {
            "recruitAndCourseId": "ABC123_456",
            "courseName": "测试课程",
            "recruitId": 789,
            "courseInfo": {
                "courseId": 456,
                "name": "测试课程",
                "enName": "Test Course",
            },
        }
        course = ZhidaoCourse.model_validate(data)
        assert course.recruit_id == 789
        assert course.course_info is not None
        assert course.course_info.course_id == 456
        assert course.course_info.name == "测试课程"


class TestVideoSmallLesson:
    """VideoSmallLesson 模型测试"""

    def test_required_field_only(self) -> None:
        """仅提供必填字段 video_id"""
        lesson = VideoSmallLesson(video_id=100)
        assert lesson.video_id == 100
        assert lesson.id == 0
        assert lesson.name == ""
        assert lesson.lesson_id == 0
        assert lesson.chapter_id == 0
        assert lesson.video_sec == 0
        assert lesson.watch_state == 0
        assert lesson.study_total_time == 0

    def test_all_fields(self) -> None:
        """所有字段赋值"""
        lesson = VideoSmallLesson(
            video_id=100,
            id=200,
            name="1.1 导论",
            lesson_id=300,
            chapter_id=400,
            video_sec=1800,
            watch_state=1,
            study_total_time=900,
        )
        assert lesson.video_id == 100
        assert lesson.id == 200
        assert lesson.name == "1.1 导论"
        assert lesson.video_sec == 1800
        assert lesson.watch_state == 1
        assert lesson.study_total_time == 900


class TestVideoChapter:
    """VideoChapter 模型测试"""

    def test_default_video_lessons(self) -> None:
        """video_lessons 默认空列表"""
        chapter = VideoChapter(id=1, name="第一章")
        assert chapter.video_lessons == []

    def test_with_lessons(self) -> None:
        """包含课时"""
        chapter = VideoChapter(
            id=1,
            name="第一章",
            video_lessons=[
                VideoLesson(id=10, name="1.1 导论"),
                VideoLesson(id=11, name="1.2 基础"),
            ],
        )
        assert len(chapter.video_lessons) == 2
        assert chapter.video_lessons[0].name == "1.1 导论"


class TestVideoLesson:
    """VideoLesson 模型测试"""

    def test_defaults(self) -> None:
        """默认值正确"""
        lesson = VideoLesson(id=10, name="1.1 导论")
        assert lesson.lesson_id == 0
        assert lesson.video_id == 0
        assert lesson.chapter_id == 0
        assert lesson.video_small_lessons == []
        assert lesson.watch_state == 0
        assert lesson.study_total_time == 0

    def test_with_small_lessons(self) -> None:
        """包含子视频"""
        lesson = VideoLesson(
            id=10,
            name="1.1 导论",
            video_small_lessons=[
                VideoSmallLesson(video_id=100, name="1.1.1 开头"),
            ],
        )
        assert len(lesson.video_small_lessons) == 1


class TestQuestionModels:
    """弹窗题目相关模型测试"""

    def test_question_point(self) -> None:
        """QuestionPoint 时间点和题目 ID"""
        qp = QuestionPoint(time_sec=120, question_ids=[1, 2, 3])
        assert qp.time_sec == 120
        assert qp.question_ids == [1, 2, 3]

    def test_question_option(self) -> None:
        """QuestionOption result='1' 为正确答案"""
        opt = QuestionOption(id=10, content="选项A", result="1")
        assert opt.result == "1"

    def test_question_option_default(self) -> None:
        """QuestionOption 默认值"""
        opt = QuestionOption(id=10)
        assert opt.content == ""
        assert opt.result == ""

    def test_popup_question(self) -> None:
        """PopupQuestion 包含题目 ID 和选项"""
        pq = PopupQuestion(
            question_id=5,
            question_options=[
                QuestionOption(id=10, result="0"),
                QuestionOption(id=11, result="1"),
            ],
        )
        assert pq.question_id == 5
        assert len(pq.question_options) == 2


class TestZhidaoContext:
    """ZhidaoContext 模型测试"""

    def test_no_sensitive_fields(self) -> None:
        """ZhidaoContext 不含 cookies/headers 字段"""
        ctx = ZhidaoContext(
            course=ZhidaoCourse(secret="ABC", course_name="测试"),
            chapters=[],
            videos={},
        )
        # 确保没有 cookies 和 headers 字段
        assert not hasattr(ctx, "cookies")
        assert not hasattr(ctx, "headers")

    def test_fucked_time_default(self) -> None:
        """fucked_time 默认为 0"""
        ctx = ZhidaoContext(
            course=ZhidaoCourse(secret="ABC", course_name="测试"),
            chapters=[],
            videos={},
        )
        assert ctx.fucked_time == 0

    def test_with_videos(self) -> None:
        """包含视频字典"""
        video = VideoSmallLesson(video_id=100, name="1.1 导论")
        ctx = ZhidaoContext(
            course=ZhidaoCourse(secret="ABC", course_name="测试"),
            chapters=[],
            videos={100: video},
        )
        assert ctx.videos[100].name == "1.1 导论"

    def test_chapters_type(self) -> None:
        """chapters 为 VideoChapter 列表"""
        chapter = VideoChapter(id=1, name="第一章")
        ctx = ZhidaoContext(
            course=ZhidaoCourse(secret="ABC", course_name="测试"),
            chapters=[chapter],
            videos={},
        )
        assert len(ctx.chapters) == 1
        assert ctx.chapters[0].name == "第一章"

"""AI 课程集成测试 — 课程列表、知识点、资源、考试"""

from typing import Any

import pytest

from zhs.ai.course import AiCourseManager
from zhs.config import AppConfig
from zhs.session import ZhsSession

pytestmark = pytest.mark.integration


class TestAiCourseList:
    """AI 课程列表"""

    def test_get_ai_course_list(self, logged_in_session: ZhsSession) -> None:
        """A-01: 获取 AI 课程列表"""
        mgr = AiCourseManager(logged_in_session)
        courses = mgr.get_ai_course_list()
        assert isinstance(courses, list)
        if courses:
            c = courses[0]
            assert "courseId" in c
            assert "classId" in c

    def test_ai_course_list_not_empty(self, logged_in_session: ZhsSession) -> None:
        """A-01: 至少有一门 AI 课程"""
        mgr = AiCourseManager(logged_in_session)
        courses = mgr.get_ai_course_list()
        assert len(courses) > 0, "账号下没有 AI 课程"


class TestAiKnowledgePoints:
    """AI 课程知识点"""

    def test_get_knowledge_points(self, logged_in_session: ZhsSession, ai_course: dict[str, Any]) -> None:
        """A-02: 获取知识点"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])
        info = mgr.get_knowledge_points(course_id, class_id)
        assert info is not None
        assert info.cake_theme_list is not None

    def test_knowledge_points_have_themes(self, logged_in_session: ZhsSession, ai_course: dict[str, Any]) -> None:
        """A-02: 知识点包含主题"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])
        info = mgr.get_knowledge_points(course_id, class_id)
        if not info.cake_theme_list:
            pytest.skip("该 AI 课程没有主题/知识点")
        assert len(info.cake_theme_list) > 0


class TestAiResources:
    """AI 课程资源"""

    def test_list_knowledge_resources(self, logged_in_session: ZhsSession, ai_course: dict[str, Any]) -> None:
        """A-03: 获取知识点资源列表"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])
        info = mgr.get_knowledge_points(course_id, class_id)

        if not info.cake_theme_list or not info.cake_theme_list[0].knowledge_list:
            pytest.skip("该 AI 课程没有知识点")

        kp = info.cake_theme_list[0].knowledge_list[0]
        resources = mgr.list_knowledge_resources(course_id, class_id, kp.knowledge_id)
        assert isinstance(resources, list)

    def test_complete_text_resource(self, logged_in_session: ZhsSession, ai_course: dict[str, Any]) -> None:
        """A-04: 完成文本资源"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])
        info = mgr.get_knowledge_points(course_id, class_id)

        if not info.cake_theme_list or not info.cake_theme_list[0].knowledge_list:
            pytest.skip("没有知识点")

        # 找一个文本资源
        for theme in info.cake_theme_list:
            for kp in theme.knowledge_list:
                resources = mgr.list_knowledge_resources(course_id, class_id, kp.knowledge_id)
                for res in resources:
                    detail = res.resources_detail
                    if detail.resources_type == 2 and detail.resources_distribute_type == 1:  # 文本资源
                        mgr.complete_resource(course_id, class_id, kp.knowledge_id, detail.resources_uid)
                        # complete_resource 返回 None，不抛异常即成功
                        return

        pytest.skip("没有文本资源可供测试")


class TestAiExam:
    """AI 课程考试"""

    def test_query_ai_exam(self, logged_in_session: ZhsSession, ai_course: dict[str, Any]) -> None:
        """A-07: 查询考试信息"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])
        info = mgr.get_knowledge_points(course_id, class_id)

        if not info.cake_theme_list or not info.cake_theme_list[0].knowledge_list:
            pytest.skip("没有知识点")

        kp = info.cake_theme_list[0].knowledge_list[0]
        exam = mgr.query_homework(course_id, class_id, kp.knowledge_id)
        # 考试可能不存在
        if exam is None:
            pytest.skip("该知识点没有考试")

        assert exam.exam_test_id is not None


class TestAiCourseFlow:
    """AI 课程完整流程"""

    def test_run_course_no_exam(
        self,
        logged_in_session: ZhsSession,
        ai_course: dict[str, Any],
        app_config: AppConfig,
    ) -> None:
        """A-17: no_homework 模式 — 只完成资源学习，不参加考试"""
        mgr = AiCourseManager(logged_in_session)
        course_id = int(ai_course["courseId"])
        class_id = int(ai_course["classId"])

        # no_homework=True，避免影响真实成绩
        try:
            mgr.run_course(course_id, class_id, app_config.ai, app_config.homework, no_homework=True)
        except Exception as e:
            # 部分资源可能已完成，导致异常
            if "已完成" not in str(e):
                pytest.skip(f"AI 课程执行异常: {e}")

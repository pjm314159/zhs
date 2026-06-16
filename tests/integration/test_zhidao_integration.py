"""知到课程集成测试 — 课程列表、上下文、视频播放"""

from typing import Any

import pytest

from zhs.config import AppConfig
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.models import ZhidaoContext

pytestmark = pytest.mark.integration


class TestZhidaoCourseList:
    """知到课程列表"""

    def test_get_course_list(self, logged_in_session: ZhsSession) -> None:
        """Z-01: 获取课程列表"""
        mgr = ZhidaoCourseManager(logged_in_session)
        courses = mgr.get_course_list()
        assert isinstance(courses, list)
        if courses:
            c = courses[0]
            assert c.course_name is not None
            assert c.secret is not None
            assert len(c.secret) > 0

    def test_course_list_not_empty(self, logged_in_session: ZhsSession) -> None:
        """Z-01: 至少有一门课程"""
        mgr = ZhidaoCourseManager(logged_in_session)
        courses = mgr.get_course_list()
        assert len(courses) > 0, "账号下没有知到课程"

    def test_course_list_fields(self, logged_in_session: ZhsSession) -> None:
        """Z-01: 课程字段完整性"""
        mgr = ZhidaoCourseManager(logged_in_session)
        courses = mgr.get_course_list()
        if not courses:
            pytest.skip("没有知到课程")
        c = courses[0]
        assert hasattr(c, "course_name")
        assert hasattr(c, "secret")


class TestZhidaoContext:
    """知到课程上下文"""

    def test_get_context(self, logged_in_session: ZhsSession, zhidao_course: dict[str, Any]) -> None:
        """Z-03: 获取课程上下文"""
        mgr = ZhidaoCourseManager(logged_in_session)
        ctx = mgr.get_context(zhidao_course["secret"])
        assert isinstance(ctx, ZhidaoContext)
        assert ctx.course.recruit_id is not None

    def test_context_has_chapters(self, logged_in_session: ZhsSession, zhidao_course: dict[str, Any]) -> None:
        """Z-06: 上下文包含章节/视频信息"""
        mgr = ZhidaoCourseManager(logged_in_session)
        ctx = mgr.get_context(zhidao_course["secret"])
        assert ctx.chapters is not None
        assert len(ctx.chapters) > 0

    def test_gologin_returns_html(self, logged_in_session: ZhsSession, zhidao_course: dict[str, Any]) -> None:
        """Z-04: 跨站登录 gologin 返回 HTML"""
        mgr = ZhidaoCourseManager(logged_in_session)
        mgr.gologin(zhidao_course["secret"])
        # gologin 无返回值（返回 HTML 不解析），不抛异常即成功

    def test_query_course(self, logged_in_session: ZhsSession, zhidao_course: dict[str, Any]) -> None:
        """Z-05: 查询课程信息"""
        mgr = ZhidaoCourseManager(logged_in_session)
        result = mgr.query_course(zhidao_course["secret"])
        assert isinstance(result, dict)

    def test_video_list(self, logged_in_session: ZhsSession, zhidao_course: dict[str, Any]) -> None:
        """Z-06: 获取视频列表"""
        mgr = ZhidaoCourseManager(logged_in_session)
        result = mgr.video_list(zhidao_course["secret"])
        assert isinstance(result, dict)


class TestZhidaoVideo:
    """知到视频播放"""

    def test_video_player_init(
        self,
        logged_in_session: ZhsSession,
        zhidao_course: dict[str, Any],
        app_config: AppConfig,
    ) -> None:
        """Z-08: 视频播放器初始化成功"""
        from zhs.zhidao.video import ZhidaoVideoPlayer

        mgr = ZhidaoCourseManager(logged_in_session)
        ctx = mgr.get_context(zhidao_course["secret"])

        # 找到第一个未完成的视频
        video_id = None
        for chapter in ctx.chapters:
            for lesson in chapter.video_lessons:
                for small in lesson.video_small_lessons:
                    if small.watch_state != 1:
                        video_id = small.video_id
                        break
                if video_id:
                    break
            if video_id:
                break

        if video_id is None:
            pytest.skip("没有未完成的视频可供测试")

        # 仅验证播放器能初始化，不实际播放
        player = ZhidaoVideoPlayer(
            logged_in_session,
            speed=app_config.zhidao_speed,
            end_threshold=app_config.threshold,
            time_limit=5,
            progressbar_view=False,
            tree_view=False,
        )
        assert player is not None

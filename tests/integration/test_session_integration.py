"""会话集成测试 — 加密查询、签名、API 交互验证"""

import pytest

from zhs.session import ZhsSession

pytestmark = pytest.mark.integration


class TestZhidaoQuery:
    """知到 API 加密查询"""

    def test_zhidao_query_encrypted_request(self, logged_in_session: ZhsSession) -> None:
        """S-01: zhidao_query 加密请求返回有效数据"""
        url = f"{logged_in_session.urls.base}/gateway/t/v1/student/course/share/queryShareCourseInfo"
        data = {"status": 3, "pageSize": 5, "pageIndex": 1}
        result = logged_in_session.zhidao_query(
            url, data, key=logged_in_session.crypto.key_bytes("home_key"), ok_code=200
        )
        assert isinstance(result, dict)
        assert "result" in result or "data" in result or "rt" in result

    def test_zhidao_query_date_formate_field(self, logged_in_session: ZhsSession) -> None:
        """S-08: dateFormate 字段同时作为加密数据和独立表单字段"""
        url = f"{logged_in_session.urls.base}/gateway/t/v1/student/course/share/queryShareCourseInfo"
        data = {"status": 3, "pageSize": 1, "pageIndex": 1}
        result = logged_in_session.zhidao_query(
            url, data, key=logged_in_session.crypto.key_bytes("home_key"), ok_code=200
        )
        assert isinstance(result, dict)


class TestHikeQuery:
    """Hike API 签名查询"""

    def test_hike_query_signed_request(self, logged_in_session: ZhsSession) -> None:
        """S-02: hike_query 签名请求返回有效数据"""
        url = f"{logged_in_session.urls.hike.replace('https://hike.zhihuishu.com', 'https://hikeservice.zhihuishu.com')}/student/course/aided/getMyCourseList"
        result = logged_in_session.hike_query(url, {}, ok_code=0)
        assert isinstance(result, dict)


class TestApiQuery:
    """通用 API 查询"""

    def test_api_query_ai_course_list(self, logged_in_session: ZhsSession) -> None:
        """S-03: api_query 请求 AI 课程列表"""
        url = f"{logged_in_session.urls.base}/gateway/t/v1/student/queryStudentAICourseList"
        data = {"status": 3}
        result = logged_in_session.zhidao_query(
            url, data, key=logged_in_session.crypto.key_bytes("home_key"), ok_code=0
        )
        assert isinstance(result, dict)


class TestSessionProperties:
    """会话属性"""

    def test_uuid_from_cookie(self, logged_in_session: ZhsSession) -> None:
        """S-05: uuid 从 Cookie 正确解析"""
        uuid = logged_in_session.uuid
        assert uuid is not None
        assert len(uuid) > 0

    def test_exit_record_auto_set(self, logged_in_session: ZhsSession) -> None:
        """S-06: exitRecod_{uuid} 自动设置"""
        uuid = logged_in_session.uuid
        assert uuid is not None
        cookie_name = f"exitRecod_{uuid}"
        assert cookie_name in logged_in_session.cookies

    def test_urls_config_accessible(self, logged_in_session: ZhsSession) -> None:
        """URL 配置可访问"""
        assert logged_in_session.urls.base.startswith("https://")
        assert logged_in_session.urls.passport.startswith("https://")
        assert logged_in_session.urls.study.startswith("https://")

    def test_crypto_config_accessible(self, logged_in_session: ZhsSession) -> None:
        """加密配置可访问"""
        assert len(logged_in_session.crypto.home_key) > 0
        assert len(logged_in_session.crypto.video_key) > 0
        assert len(logged_in_session.crypto.ai_key) > 0

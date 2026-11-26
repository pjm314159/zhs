"""从显式 CLI 到加密 HTTP 的离线契约测试。"""

import json
from unittest.mock import patch

import httpx
import pytest
import respx
from typer.testing import CliRunner

from zhs.__main__ import app
from zhs.config import AppConfig
from zhs.crypto import Cipher
from zhs.session import ZhsSession


@pytest.mark.parametrize(
    ("top", "nested", "expected", "code"),
    [(120, 456, 120, 200), (0, 456, 456, "200"), (-1, 0, None, 200), (None, None, None, 200)],
)
def test_start_from_course_list(top: int | None, nested: int | None, expected: int | None, code: int | str) -> None:
    config = AppConfig()
    session = ZhsSession(config)
    course = {"courseName": "KG", "recruitAndCourseId": "selected", "recruitId": 91}
    if top is not None:
        course["courseId"] = top
    if nested is not None:
        course["courseInfo"] = {"courseId": nested, "name": "KG"}
    other = dict(course, recruitAndCourseId="other", courseId=999)
    with (
        respx.mock(assert_all_called=False) as router,
        patch("zhs.__main__._load_config_and_session", return_value=(config, session)),
    ):
        listing = router.post(config.urls.base + "/gateway/t/v1/student/course/share/queryShareCourseInfo").mock(
            return_value=httpx.Response(200, json={"code": 200, "result": {"courseOpenDtos": [other, course]}})
        )
        start = router.get(config.urls.aistudy + "/gateway/t/v1/exam/start").mock(
            return_value=httpx.Response(200, json={"code": code, "data": {"examId": 42}})
        )
        result = CliRunner().invoke(app, ["kg-exam-start", "selected", "node"])
        assert listing.call_count == 1
        if expected is None:
            assert result.exit_code == 1
            assert "courseId" in result.output
            assert not start.called
            return
        assert result.exit_code == 0, result.exception
        assert json.loads(result.output) == {"examId": 42}
        assert start.call_count == 1
        params = start.calls[0].request.url.params
        cipher = Cipher(config.crypto.key_bytes("video_key"), config.crypto.key_bytes("iv"))
        assert json.loads(cipher.decrypt(params["secretStr"])) == {
            "courseId": expected,
            "recruitId": "91",
            "knowledeId": "node",
            "dateFormate": int(params["dateFormate"]),
        }

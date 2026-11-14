from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from zhs.api.zhidao_kg_exam_api import ZhidaoKgExamApi
from zhs.config import HomeworkConfig
from zhs.exceptions import ApiError
from zhs.zhidao.kg_exam import KgExamHandler


def lesson() -> Any:
    return SimpleNamespace(id_hash="k")


def test_captured_request_contract() -> None:
    query = Mock()
    query.query.return_value = {"data": {}}
    api = ZhidaoKgExamApi(query)
    api.start_exam("r", 123, "k")
    assert query.query.call_args.args[2] == {"recruitId": "r", "courseId": 123, "knowledeId": "k"}
    api.get_mastery_info("r", 456, "k")
    assert query.query.call_args.args[2] == {"recruitId": "r", "examId": 456, "knowledeId": "k"}
    api.get_error_question_recommend("r", "k")
    assert query.query.call_args.args[2] == {"recruitId": "r", "knowledeId": "k"}


def make_handler(**config: Any) -> tuple[KgExamHandler, Mock]:
    session = Mock()
    session.kg_exam_start.return_value = {
        "examId": 42,
        "questions": [
            {
                "questionId": 1,
                "questionType": 1,
                "questionName": "<p>Q</p>",
                "optionVos": [{"id": 7, "name": "<b>A</b>"}, {"id": 8, "name": "B"}],
            }
        ],
    }
    session.kg_exam_submit.return_value = True
    session.kg_exam_get_mastery_info.return_value = {"rate": "100"}
    handler = KgExamHandler(session, HomeworkConfig(**config))
    return handler, session


def test_disabled_has_no_calls() -> None:
    handler, session = make_handler(enable_kg_exam=False)
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    assert not session.mock_calls


@pytest.mark.parametrize("code", [2044, 404, 500])
def test_api_failure_is_not_completion(code: int) -> None:
    handler, session = make_handler()
    session.kg_exam_start.side_effect = ApiError(code, "failure")
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_no_solver_never_submits() -> None:
    handler, session = make_handler()
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_retry_fetches_new_exam_and_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zhs.zhidao.kg_exam.time.sleep", lambda _: None)
    handler, session = make_handler(kg_exam_max_retries=1)
    first = session.kg_exam_start.return_value
    second = {"examId": 43, "questions": [dict(first["questions"][0], questionId=2)]}
    session.kg_exam_start.side_effect = [first, second]
    session.kg_exam_get_mastery_info.side_effect = [{"rate": "0"}, {"rate": "100"}]
    handler._llm = Mock()
    handler._llm.single_choice.return_value = [8]
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    assert session.kg_exam_start.call_args.args == ("r", 123, "k")
    assert session.kg_exam_submit.call_args.args == ("r", 43, "k", [{"questionId": 2, "answer": 8}])


def test_invalid_llm_selection_never_submits() -> None:
    handler, session = make_handler()
    handler._llm = Mock()
    handler._llm.single_choice.return_value = [999]
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_question_bank_hint_uses_real_interface() -> None:
    from zhs.question_bank.models import QuestionBankResult

    handler, session = make_handler()
    handler._qb = Mock(spec=["query"])
    handler._qb.query.return_value = QuestionBankResult(answer="B", times=5)
    handler._llm = Mock()
    handler._llm.single_choice.return_value = [8]
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    handler._qb.query.assert_called_once_with("Q", "A\nB", "single")
    assert "B" in handler._llm.single_choice.call_args.kwargs["extra"]["题库参考"]
    assert session.kg_exam_submit.call_args.args[-1] == [{"questionId": 1, "answer": 8}]


@pytest.mark.parametrize("mastery", [{}, {"rate": "bad"}, {"rate": "nan"}, {"rate": "101"}])
def test_invalid_mastery_fails(mastery: dict[str, str]) -> None:
    handler, session = make_handler()
    handler._llm = Mock()
    handler._llm.single_choice.return_value = [8]
    session.kg_exam_get_mastery_info.return_value = mastery
    assert not handler.try_handle_exam("r", lesson(), course_id=123)


def test_multi_choice_maps_ids_without_fallback() -> None:
    handler, session = make_handler()
    session.kg_exam_start.return_value["questions"][0]["questionType"] = 2
    handler._llm = Mock()
    handler._llm.multiple_choice.return_value = [7, 8]
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    assert session.kg_exam_submit.call_args.args[-1] == [{"questionId": 1, "answer": "7,8"}]


def test_session_forwards_course_id() -> None:
    from zhs.session import ZhsSession

    session = object.__new__(ZhsSession)
    session._kg_exam_api = Mock()
    session.kg_exam_start("r", 123, "k")
    session._kg_exam_api.start_exam.assert_called_once_with("r", 123, "k")


@pytest.mark.parametrize("selected", [[7, 8], [7, 7], [True], ["7"], [], [999]])
def test_bad_single_selection_never_submits(selected: list[Any]) -> None:
    handler, session = make_handler()
    handler._llm = Mock()
    handler._llm.single_choice.return_value = selected
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_judgement_dispatch() -> None:
    handler, session = make_handler()
    session.kg_exam_start.return_value["questions"][0]["questionType"] = 14
    handler._llm = Mock()
    handler._llm.judgement.return_value = [7]
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    handler._llm.judgement.assert_called_once()
    handler._llm.single_choice.assert_not_called()
    assert session.kg_exam_submit.call_args.args[-1] == [{"questionId": 1, "answer": 7}]


def test_wrong_knowledge_never_submits() -> None:
    handler, session = make_handler()
    session.kg_exam_start.return_value["knowledgeId"] = "other"
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_judgement_uses_real_solver() -> None:
    handler, session = make_handler()
    session.kg_exam_start.return_value["questions"][0]["questionType"] = 14
    handler._llm = Mock()
    handler._llm.judgement.return_value = [8]
    assert handler.try_handle_exam("r", lesson(), course_id=123)
    handler._llm.judgement.assert_called_once()
    assert session.kg_exam_submit.call_args.args[-1] == [{"questionId": 1, "answer": 8}]


def test_partial_answers_never_submit() -> None:
    handler, session = make_handler()
    questions = session.kg_exam_start.return_value["questions"]
    questions.append(dict(questions[0], questionId=2))
    handler._llm = Mock()
    handler._llm.single_choice.side_effect = [[8], []]
    assert not handler.try_handle_exam("r", lesson(), course_id=123)
    session.kg_exam_submit.assert_not_called()


def test_daily_budget_exhausted_checks_only_exams(tmp_path: Any) -> None:
    from unittest.mock import patch

    from zhs.cli.services.play_service import play_zhidao_course
    from zhs.config import AppConfig
    from zhs.zhidao.models import CourseInfo, ZhidaoContext, ZhidaoCourse
    from zhs.zhidao.schedule import DailyPlan

    course = ZhidaoCourse(
        secret="r",
        course_name="KG",
        course_id=123,
        recruit_id=1,
        course_info=CourseInfo(course_id=123, name="KG"),
        has_habbit_score=True,
    )
    ctx = ZhidaoContext(course=course, chapters=[], videos={}, course_id=123, mode="map")
    with (
        patch("zhs.utils.path.get_data_dir", return_value=tmp_path),
        patch("zhs.zhidao.schedule.plan_today", return_value=DailyPlan(0, False, 2, 2400)),
        patch("zhs.zhidao.video.ZhidaoVideoPlayer") as player,
    ):
        play_zhidao_course(Mock(), AppConfig(), "r", ctx, None)
    player.return_value.check_map_exams.assert_called_once_with(ctx)
    player.return_value.play_course.assert_not_called()


def test_http_and_llm_contract_end_to_end() -> None:
    """走真实 session/加密/LLM 解析，HTTP 和模型补全均在本地模拟。"""
    import json

    import httpx
    import respx

    from zhs.config import AppConfig
    from zhs.crypto import Cipher
    from zhs.llm.base import LLMProvider
    from zhs.session import ZhsSession

    class Solver(LLMProvider):
        def completion(self, prompt: str, aim_start: str = "```answer", aim_end: str = "```") -> str:
            return '```answer\n[{"id": 8, "content": "B"}]\n```'

    config = AppConfig()
    session = ZhsSession(config)
    cipher = Cipher(config.crypto.key_bytes("video_key"), config.crypto.key_bytes("iv"))
    base = config.urls.aistudy + "/gateway/t/v1/exam"
    _, fixture = make_handler()
    paper = fixture.kg_exam_start.return_value
    with respx.mock as router:
        start = router.get(base + "/start").mock(return_value=httpx.Response(200, json={"code": 200, "data": paper}))
        submit = router.post(base + "/submit").mock(return_value=httpx.Response(200, json={"code": 200, "data": True}))
        router.get(base + "/getAnswerMasteryInfo").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {"rate": "100"}})
        )
        try:
            assert KgExamHandler(session, HomeworkConfig(), llm=Solver()).try_handle_exam("r", lesson(), course_id=123)
            payload = json.loads(cipher.decrypt(start.calls[0].request.url.params["secretStr"]))
            assert payload["courseId"] == 123 and payload["knowledeId"] == "k"
            assert "examId" not in payload and "knowledgeId" not in payload
            body = json.loads(submit.calls[0].request.content)
            assert body["knowledgeId"] == "k"
            assert body["answerVos"] == [{"questionId": 1, "answer": 8}]
        finally:
            session.close()


def test_output_shows_progress_and_result_without_debug_noise() -> None:
    handler, _ = make_handler()
    handler._llm = Mock()
    handler._llm.single_choice.return_value = [8]
    output = Mock()
    assert handler.try_handle_exam("r", lesson(), print_callback=output, course_id=123)
    messages = [call.args[0] for call in output.call_args_list]
    assert any("1 题 · AI · 目标 100%" in message for message in messages)
    assert any("答题 1/1 · 单选" in message for message in messages)
    assert any("掌握度达标: 100% / 目标 100%" in message for message in messages)
    assert all("[DEBUG]" not in message and "[KG]" not in message for message in messages)
    assert all(call.kwargs == {"depth": 3} for call in output.call_args_list)

"""题库 models 测试 — QuestionBankResult / QuestionBankInfo / map_question_type"""

import pytest

from zhs.question_bank.models import (
    QuestionBankInfo,
    QuestionBankResult,
    map_question_type,
)

# ---------------------------------------------------------------------------
# QuestionBankResult._parse_answer / format_hint
# ---------------------------------------------------------------------------


class TestQuestionBankResultParse:
    def test_single_answer_no_separator(self) -> None:
        r = QuestionBankResult(question="q", answer="正确答案")
        assert r._parse_answer() == ["正确答案"]

    def test_multi_answer_newline_separated(self) -> None:
        r = QuestionBankResult(
            question="q",
            answer="连续性#\n创新性#\n统一性#\n和平性#\n包容性",
        )
        assert r._parse_answer() == ["连续性", "创新性", "统一性", "和平性", "包容性"]

    def test_hash_pollution_stripped(self) -> None:
        # "#" 是题库污染字符，需清除（每行尾部的 #）
        r = QuestionBankResult(question="q", answer="A#\nB#\nC")
        assert r._parse_answer() == ["A", "B", "C"]

    def test_empty_answer(self) -> None:
        r = QuestionBankResult(question="q", answer="")
        assert r._parse_answer() == []

    def test_blank_lines_dropped(self) -> None:
        r = QuestionBankResult(question="q", answer="A\n\nB\n")
        assert r._parse_answer() == ["A", "B"]


class TestQuestionBankResultFormatHint:
    def test_single_answer_hint(self) -> None:
        r = QuestionBankResult(question="q", answer="正确答案", ai=False)
        hint = r.format_hint()
        assert "题库数据库" in hint
        assert "正确答案" in hint

    def test_multi_answer_hint(self) -> None:
        r = QuestionBankResult(
            question="q",
            answer="连续性#\n创新性#\n统一性#\n和平性#\n包容性",
            ai=False,
        )
        hint = r.format_hint()
        assert "题库数据库" in hint
        assert "连续性" in hint
        assert "包容性" in hint
        # 多答案以列表项展示
        assert "- 连续性" in hint
        assert "- 包容性" in hint

    def test_ai_source_label(self) -> None:
        r = QuestionBankResult(question="q", answer="答案", ai=True)
        hint = r.format_hint()
        assert "题库AI生成" in hint

    def test_empty_answer_returns_empty(self) -> None:
        r = QuestionBankResult(question="q", answer="")
        assert r.format_hint() == ""

    def test_hint_has_standard_answer_instruction(self) -> None:
        r = QuestionBankResult(question="q", answer="答案")
        hint = r.format_hint()
        assert "标准答案" in hint
        assert "分解并给出标准回答形式" in hint

    def test_hint_wraps_answer_in_code_block(self) -> None:
        r = QuestionBankResult(question="q", answer="正确答案")
        hint = r.format_hint()
        assert "```\n正确答案\n```" in hint

    def test_hint_ends_with_newline(self) -> None:
        r = QuestionBankResult(question="q", answer="答案")
        hint = r.format_hint()
        assert hint.endswith("\n")

    def test_multi_answer_wraps_in_code_block(self) -> None:
        r = QuestionBankResult(question="q", answer="A\nB")
        hint = r.format_hint()
        assert "```\n- A\n- B\n```" in hint


# ---------------------------------------------------------------------------
# QuestionBankInfo
# ---------------------------------------------------------------------------


class TestQuestionBankInfo:
    def test_default_values(self) -> None:
        info = QuestionBankInfo()
        assert info.times == 0
        assert info.user_times == 0
        assert info.success_times == 0

    def test_custom_values(self) -> None:
        info = QuestionBankInfo(times=96, user_times=100, success_times=80)
        assert info.times == 96
        assert info.user_times == 100
        assert info.success_times == 80

    def test_from_dict(self) -> None:
        info = QuestionBankInfo.model_validate({"times": 50, "user_times": 60, "success_times": 40})
        assert info.times == 50
        assert info.success_times == 40


# ---------------------------------------------------------------------------
# map_question_type
# ---------------------------------------------------------------------------


class TestMapQuestionType:
    @pytest.mark.parametrize(
        ("qtype_id", "expected"),
        [
            (1, "single"),
            (2, "multiple"),
            (3, "completion"),
            (14, "judgement"),
        ],
    )
    def test_known_types(self, qtype_id: int, expected: str) -> None:
        assert map_question_type(qtype_id) == expected

    def test_unknown_type(self) -> None:
        assert map_question_type(99) == "unknown"

    def test_zero_type(self) -> None:
        assert map_question_type(0) == "unknown"

    def test_negative_type(self) -> None:
        assert map_question_type(-1) == "unknown"

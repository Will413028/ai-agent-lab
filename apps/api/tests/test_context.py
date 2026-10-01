from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_lab_api.context import MAX_CONTEXT_CHARS, MAX_CONTEXT_TURNS, SYSTEM_PROMPT, build_context
from agent_lab_api.conversation_models import LoveReport, Turn


def turn(position: int, question: str, answer: str, status="completed") -> Turn:
    return Turn(
        id=uuid4(),
        conversation_id=uuid4(),
        position=position,
        question=question,
        answer=answer,
        status=status,
        error_code=None,
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def test_context_keeps_system_and_current_question_and_complete_pairs():
    history = [turn(n, f"問題{n}", f"回答{n}") for n in range(1, 10)]
    history += [turn(10, "取消的問題", "半段", "cancelled"), turn(11, "失敗問題", "", "failed")]
    messages = build_context(history, "本次問題")
    assert messages[0].content == SYSTEM_PROMPT
    assert messages[-1].content == "本次問題"
    assert len(messages) == 2 * MAX_CONTEXT_TURNS + 2
    assert [m.role for m in messages[1:-1]] == ["user", "assistant"] * MAX_CONTEXT_TURNS
    assert [m.content for m in messages if m.role == "user"] == [
        f"問題{n}" for n in range(4, 10)
    ] + ["本次問題"]


def test_context_character_budget_drops_older_pairs_without_cutting_current_question():
    history = [turn(n, f"問題{n}", "a" * 15000) for n in range(1, 5)]
    messages = build_context(history, "🙂" * 2000)
    assert sum(len(m.content) for m in messages) <= MAX_CONTEXT_CHARS
    assert [m.content for m in messages if m.role == "user"] == ["問題4", "🙂" * 2000]


def test_stored_turn_and_prompt_preserve_provider_whitespace():
    history = [turn(1, "問題", "  縮排內容\n")]
    assert history[0].answer == "  縮排內容\n"
    messages = build_context(history, "下一輪")
    assert messages[2].content == "  縮排內容\n"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "suggestions": ["ok"]},
        {"title": "ok", "suggestions": []},
        {"title": "ok", "suggestions": [""]},
        {"title": "ok", "suggestions": ["a" * 1201]},
        {"title": "ok", "suggestions": ["ok"] * 6},
        {"title": "ok", "suggestions": ["ok"], "extra": True},
    ],
)
def test_report_rejects_invalid_content(payload):
    with pytest.raises(ValidationError):
        LoveReport.model_validate(payload)

import pytest

from app.rag.exceptions import RagError
from app.rag.prompt_builder import (
    DOCUMENTS_PREFIX,
    DOCUMENTS_SUFFIX,
    RAG_SYSTEM_PROMPT,
    build_chat_messages,
    compute_available_context_chars,
    fit_messages_to_budget,
)


def test_build_chat_messages_places_context_before_history() -> None:
    max_chars = len(RAG_SYSTEM_PROMPT) + len(DOCUMENTS_PREFIX) + len("[1]\nContent:\nmatn") + len(DOCUMENTS_SUFFIX) + len("old") + len("savol")
    messages = build_chat_messages(
        user_message="savol",
        history=[{"role": "user", "content": "old"}],
        context_text="[1]\nContent:\nmatn",
        max_chars=max_chars,
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == RAG_SYSTEM_PROMPT
    assert messages[1]["content"].startswith("<documents>")
    assert messages[-1] == {"role": "user", "content": "savol"}


def test_fit_messages_to_budget_keeps_user_message() -> None:
    messages = fit_messages_to_budget(
        system_messages=[{"role": "system", "content": "s" * 10}],
        history=[{"role": "user", "content": "a" * 100}, {"role": "assistant", "content": "b" * 100}],
        user_message="final",
        max_chars=30,
    )
    assert messages[-1]["content"] == "final"


def test_fit_messages_to_budget_drops_oldest_history_first() -> None:
    messages = fit_messages_to_budget(
        system_messages=[{"role": "system", "content": "safe"}],
        history=[
            {"role": "user", "content": "old-1"},
            {"role": "assistant", "content": "old-2"},
            {"role": "user", "content": "new-1"},
            {"role": "assistant", "content": "new-2"},
        ],
        user_message="final",
        max_chars=len("safe") + len("new-1") + len("new-2") + len("final"),
    )
    assert messages[1:] == [
        {"role": "user", "content": "new-1"},
        {"role": "assistant", "content": "new-2"},
        {"role": "user", "content": "final"},
    ]


def test_compute_available_context_chars_includes_wrapper() -> None:
    available = compute_available_context_chars(
        system_prompt="safe",
        user_message="user",
        max_chars=100,
    )
    assert available == 100 - len("safe") - len("user") - len(DOCUMENTS_PREFIX) - len(DOCUMENTS_SUFFIX)


def test_compute_available_context_chars_raises_when_system_and_user_exceed_budget() -> None:
    with pytest.raises(RagError) as exc:
        compute_available_context_chars(system_prompt="s" * 20, user_message="u" * 20, max_chars=10)
    assert exc.value.code == "RAG_PROMPT_TOO_LARGE"


def test_build_chat_messages_respects_final_budget() -> None:
    context_text = "[1]\nContent:\nctx"
    max_chars = len(RAG_SYSTEM_PROMPT) + len(DOCUMENTS_PREFIX) + len(context_text) + len(DOCUMENTS_SUFFIX) + len("reply") + len("final")
    messages = build_chat_messages(
        user_message="final",
        history=[{"role": "user", "content": "old"}, {"role": "assistant", "content": "reply"}],
        context_text=context_text,
        max_chars=max_chars,
    )
    assert sum(len(message["content"]) for message in messages) <= max_chars
    assert messages[0]["content"] == RAG_SYSTEM_PROMPT
    assert messages[-1]["content"] == "final"

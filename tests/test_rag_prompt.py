import pytest

from app.rag.exceptions import RagError
from app.rag.prompt_builder import (
    DOCUMENTS_PREFIX,
    DOCUMENTS_SUFFIX,
    PromptBudget,
    RAG_SYSTEM_PROMPT,
    build_chat_messages,
    calculate_prompt_budget,
    fit_messages_to_budget,
)


def test_build_chat_messages_places_context_before_history() -> None:
    max_chars = len(RAG_SYSTEM_PROMPT) + len(DOCUMENTS_PREFIX) + len("[1]\nContent:\nmatn") + len(DOCUMENTS_SUFFIX) + len("old") + len("savol")
    messages = build_chat_messages(
        system_prompt=RAG_SYSTEM_PROMPT,
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


def test_calculate_prompt_budget_includes_wrapper_and_answer_reserve() -> None:
    budget = calculate_prompt_budget(
        system_prompt="safe",
        user_message="user",
        configured_prompt_max_chars=8000,
        ollama_num_ctx=2048,
        reserved_answer_tokens=512,
        chars_per_token_estimate=4,
        reserve_document_wrapper=True,
    )
    assert budget == PromptBudget(
        total_window_chars=8000,
        reserved_answer_chars=2048,
        max_input_chars=5952,
        available_context_chars=5952 - len("safe") - len("user") - len(DOCUMENTS_PREFIX) - len(DOCUMENTS_SUFFIX),
    )


def test_calculate_prompt_budget_raises_when_system_and_user_exceed_budget() -> None:
    with pytest.raises(RagError) as exc:
        calculate_prompt_budget(
            system_prompt="s" * 20,
            user_message="u" * 20,
            configured_prompt_max_chars=50,
            ollama_num_ctx=20,
            reserved_answer_tokens=10,
            chars_per_token_estimate=4,
        )
    assert exc.value.code == "RAG_PROMPT_TOO_LARGE"


def test_calculate_prompt_budget_caps_to_model_context() -> None:
    budget = calculate_prompt_budget(
        system_prompt="safe",
        user_message="user",
        configured_prompt_max_chars=20000,
        ollama_num_ctx=1024,
        reserved_answer_tokens=128,
        chars_per_token_estimate=4,
    )
    assert budget.total_window_chars == 4096


def test_calculate_prompt_budget_uses_config_cap_when_smaller() -> None:
    budget = calculate_prompt_budget(
        system_prompt="safe",
        user_message="user",
        configured_prompt_max_chars=3000,
        ollama_num_ctx=2048,
        reserved_answer_tokens=128,
        chars_per_token_estimate=4,
    )
    assert budget.total_window_chars == 3000


def test_calculate_prompt_budget_non_rag_does_not_reserve_wrapper() -> None:
    budget = calculate_prompt_budget(
        system_prompt="safe",
        user_message="user",
        configured_prompt_max_chars=3000,
        ollama_num_ctx=2048,
        reserved_answer_tokens=128,
        chars_per_token_estimate=4,
        reserve_document_wrapper=False,
    )
    assert budget.available_context_chars == budget.max_input_chars - len("safe") - len("user")


def test_calculate_prompt_budget_uses_larger_predict_reserve() -> None:
    budget = calculate_prompt_budget(
        system_prompt="safe",
        user_message="user",
        configured_prompt_max_chars=8000,
        ollama_num_ctx=2048,
        reserved_answer_tokens=700,
        chars_per_token_estimate=4,
    )
    assert budget.reserved_answer_chars == 2800


def test_build_chat_messages_respects_final_budget() -> None:
    context_text = "[1]\nContent:\nctx"
    max_chars = len(RAG_SYSTEM_PROMPT) + len(DOCUMENTS_PREFIX) + len(context_text) + len(DOCUMENTS_SUFFIX) + len("reply") + len("final")
    messages = build_chat_messages(
        system_prompt=RAG_SYSTEM_PROMPT,
        user_message="final",
        history=[{"role": "user", "content": "old"}, {"role": "assistant", "content": "reply"}],
        context_text=context_text,
        max_chars=max_chars,
    )
    assert sum(len(message["content"]) for message in messages) <= max_chars
    assert messages[0]["content"] == RAG_SYSTEM_PROMPT
    assert messages[-1]["content"] == "final"

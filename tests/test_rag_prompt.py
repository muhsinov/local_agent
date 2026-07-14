from app.rag.prompt_builder import RAG_SYSTEM_PROMPT, build_chat_messages, fit_messages_to_budget


def test_build_chat_messages_places_context_before_history() -> None:
    messages = build_chat_messages(
        user_message="savol",
        history=[{"role": "user", "content": "old"}],
        context_text="[1]\nContent:\nmatn",
        max_chars=500,
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

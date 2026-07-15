import json

from app.database import initialize_database
from app.services.conversation_service import save_exchange
from app.tools.conversation_tools import GetConversationMessagesTool, ListConversationsTool
from tests.conftest import build_settings


def test_list_conversations_returns_safe_summary(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    save_exchange(settings, None, "Savol", "Javob")
    payload = json.loads(ListConversationsTool(1).execute(type("Args", (), {"limit": 10, "offset": 0})(), settings))
    assert payload[0]["message_count"] == 2
    assert "content" not in payload[0]


def test_get_conversation_messages_returns_saved_exchange_only(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    conversation_id = save_exchange(settings, None, "Savol", "Javob")
    payload = json.loads(GetConversationMessagesTool(1).execute(type("Args", (), {"conversation_id": conversation_id, "limit": 10})(), settings))
    assert payload == [
        {"role": "user", "content": "Savol", "created_at": payload[0]["created_at"]},
        {"role": "assistant", "content": "Javob", "created_at": payload[1]["created_at"]},
    ]

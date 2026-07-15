import json
import sqlite3

from app.agent.errors import AgentError
from app.database import connection_scope
from app.schemas.tools import ConversationMessagesArgs, PaginationArgs, RenameConversationArgs
from app.services.conversation_service import rename_conversation
from app.tools.base import ApprovalRequiredTool, ReadOnlyTool


class ListConversationsTool(ReadOnlyTool):
    input_model = PaginationArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="list_conversations", description="List local conversation metadata without message text.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: PaginationArgs, settings) -> str:
        with connection_scope(settings) as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id AND m.role IN ('user', 'assistant')
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT ? OFFSET ?;
                """,
                (arguments.limit, arguments.offset),
            ).fetchall()
        return json.dumps(
            [
                {
                    "conversation_id": int(row["id"]),
                    "title": str(row["title"]),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                    "message_count": int(row["message_count"]),
                }
                for row in rows
            ],
            ensure_ascii=False,
        )


class GetConversationMessagesTool(ReadOnlyTool):
    input_model = ConversationMessagesArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="get_conversation_messages", description="Read stored user and assistant messages for a conversation.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: ConversationMessagesArgs, settings) -> str:
        with connection_scope(settings) as connection:
            exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?;", (arguments.conversation_id,)).fetchone()
            if exists is None:
                raise AgentError(404, "CONVERSATION_NOT_FOUND", "Conversation topilmadi.")
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = ? AND role IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT ?;
                """,
                (arguments.conversation_id, arguments.limit),
            ).fetchall()
        items = list(reversed(rows))
        return json.dumps(
            [
                {
                    "role": str(row["role"]),
                    "content": str(row["content"]),
                    "created_at": str(row["created_at"]),
                }
                for row in items
            ],
            ensure_ascii=False,
        )


class RenameConversationTool(ApprovalRequiredTool):
    input_model = RenameConversationArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(
            name="rename_conversation",
            description="Rename a conversation title after explicit human approval.",
            timeout_seconds=timeout_seconds,
        )

    def build_safe_summary(self, arguments: RenameConversationArgs) -> str:
        return f'Conversation #{arguments.conversation_id} nomini "{arguments.new_title}"ga o‘zgartirish'

    async def execute_with_approval(self, arguments: RenameConversationArgs, settings, **kwargs) -> str:
        with connection_scope(settings) as connection:
            connection.execute("BEGIN;")
            try:
                updated = rename_conversation(connection, arguments.conversation_id, arguments.new_title)
                if not updated:
                    raise AgentError(404, "CONVERSATION_NOT_FOUND", "Conversation topilmadi.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return json.dumps(
            {
                "conversation_id": arguments.conversation_id,
                "title": arguments.new_title,
                "status": "renamed",
            },
            ensure_ascii=False,
        )

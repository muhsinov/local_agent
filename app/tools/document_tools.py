import json
import sqlite3
from pathlib import Path

from app.agent.errors import AgentError
from app.api.errors import ApiError
from app.documents.storage import resolve_storage_path
from app.rag.exceptions import RagError
from app.rag.search_service import semantic_search
from app.schemas.tools import DocumentExcerptArgs, DocumentIdArgs, PaginationArgs, SearchDocumentsArgs
from app.services.document_service import get_document, list_documents
from app.tools.base import ReadOnlyTool


def _read_excerpt(path: Path, start_char: int, max_chars: int) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        if start_char:
            handle.read(start_char)
        return handle.read(max_chars)


class ListDocumentsTool(ReadOnlyTool):
    input_model = PaginationArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="list_documents", description="List safe local document metadata.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: PaginationArgs, settings) -> str:
        items = list_documents(settings, arguments.limit, arguments.offset)
        payload = [
            {
                "document_id": item.id,
                "file_name": item.file_name,
                "file_type": item.file_type,
                "status": item.status,
                "indexed": item.indexed,
                "char_count": item.char_count,
                "created_at": item.created_at,
            }
            for item in items
        ]
        return json.dumps(payload, ensure_ascii=False)


class GetDocumentMetadataTool(ReadOnlyTool):
    input_model = DocumentIdArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="get_document_metadata", description="Get safe metadata for a single document.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: DocumentIdArgs, settings) -> str:
        document = get_document(settings, arguments.document_id)
        if document is None:
            raise AgentError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
        return json.dumps(
            {
                "document_id": document.id,
                "file_name": document.file_name,
                "file_type": document.file_type,
                "status": document.status,
                "indexed": document.indexed,
                "char_count": document.char_count,
                "page_count": document.page_count,
                "warning_code": document.warning_code,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
            },
            ensure_ascii=False,
        )


class GetDocumentExcerptTool(ReadOnlyTool):
    input_model = DocumentExcerptArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="get_document_excerpt", description="Read a bounded excerpt from extracted document text.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: DocumentExcerptArgs, settings) -> str:
        document = get_document(settings, arguments.document_id)
        if document is None:
            raise AgentError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
        if not document.text_path:
            raise AgentError(422, "DOCUMENT_HAS_NO_TEXT", "Hujjatda extracted text yo'q.")
        try:
            path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path)
        except ApiError as exc:
            raise AgentError(exc.status_code, exc.code, exc.message) from exc
        excerpt = _read_excerpt(path, arguments.start_char, min(arguments.max_chars, settings.agent_max_single_tool_result_chars))
        return json.dumps(
            {
                "document_id": document.id,
                "file_name": document.file_name,
                "start_char": arguments.start_char,
                "returned_chars": len(excerpt),
                "excerpt": excerpt,
                "truncated": document.char_count > arguments.start_char + len(excerpt),
            },
            ensure_ascii=False,
        )


class SearchDocumentsTool(ReadOnlyTool):
    input_model = SearchDocumentsArgs

    def __init__(self, timeout_seconds: int, coordinator) -> None:
        super().__init__(name="search_documents", description="Run semantic search over indexed documents.", timeout_seconds=timeout_seconds)
        self._coordinator = coordinator

    async def execute_async(self, arguments: SearchDocumentsArgs, settings) -> str:
        try:
            found, generation_id, model_name, execution_time_ms = await self._coordinator.run(
                semantic_search,
                settings,
                query=arguments.query,
                top_k=arguments.top_k,
                document_ids=arguments.document_ids,
                acquire_timeout_seconds=settings.vector_index_busy_timeout_seconds,
            )
        except RagError as exc:
            raise AgentError(exc.status_code, exc.code, exc.message) from exc
        except TimeoutError as exc:
            raise AgentError(429, "VECTOR_INDEX_BUSY", "Vector index hozir band. Keyinroq qayta urinib ko'ring.") from exc
        payload = {
            "generation_id": generation_id,
            "embedding_model": model_name,
            "execution_time_ms": execution_time_ms,
            "results": [
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "file_name": item.file_name,
                    "chunk_index": item.chunk_index,
                    "score": item.score,
                    "start_char": item.start_char,
                    "end_char": item.end_char,
                    "text": item.text[: settings.agent_max_single_tool_result_chars],
                }
                for item in found
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

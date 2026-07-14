from app.services.audit_service import write_audit_log


def write_rag_chat_audit(
    settings,
    *,
    rag_enabled: bool,
    rag_used: bool,
    fallback: bool,
    source_count: int,
    context_chars: int,
    retrieval_ms: int,
    citation_count: int,
    invalid_citation_count: int,
    generation_id: str | None,
    status: str = "ok",
) -> None:
    write_audit_log(
        settings,
        action="rag_chat",
        status=status,
        arguments={
            "status": status,
            "generation_id": generation_id,
            "result_count": source_count,
            "context_chars": context_chars,
            "retrieval_ms": retrieval_ms,
            "citation_count": citation_count,
            "invalid_citation_count": invalid_citation_count,
        },
    )

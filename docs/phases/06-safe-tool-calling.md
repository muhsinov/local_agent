# Phase 6 - Safe Tool Calling

- Threat model: model faqat explicit read-only allowlist tool'larni ko'radi; shell, write, web va secret access yo'q.
- Read-only default: barcha registered tool `read_only=true`, write yoki process tool registry'ga kirmaydi.
- Tool allowlist: `list_documents`, `get_document_metadata`, `get_document_excerpt`, `search_documents`, `list_conversations`, `get_conversation_messages`, `get_local_system_info`.
- Path boundary: document excerpt faqat resolved extracted text path ichida o'qiladi.
- Argument validation: barcha tool argumentlari Pydantic `extra="forbid"` bilan validate qilinadi va global size limiti bor.
- Agent loop bounded: iteration, tool call va total timeout limitlari qat'iy.
- Per-tool timeout va umumiy token/input budget qo'llanadi.
- Tool result budget: single result va total result char limitlari bor, truncate metadata saqlanadi.
- Audit privacy: raw query, raw arguments, excerpt va internal path auditga yozilmaydi.
- Human approval keyingi phase'da qo'shiladi; bu bosqichda faqat read-only automatic execution bor.
- Write, shell, Python, web, browser va autonomous background tool'lar mavjud emas.

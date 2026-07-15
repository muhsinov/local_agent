# Phase 6 - Safe Tool Calling

- Threat model: model faqat explicit read-only allowlist tool'larni ko'radi; shell, write, web va secret access yo'q.
- Read-only default: barcha registered tool `read_only=true`, write yoki process tool registry'ga kirmaydi.
- Tool allowlist: `list_documents`, `get_document_metadata`, `get_document_excerpt`, `search_documents`, `list_conversations`, `get_conversation_messages`, `get_local_system_info`.
- Path boundary: document excerpt faqat resolved extracted text path ichida o'qiladi.
- Argument validation: barcha tool argumentlari Pydantic `extra="forbid"` bilan validate qilinadi va global size limiti bor.
- Agent loop bounded: iteration, tool call va total timeout limitlari qat'iy.
- Iteration semantics: har Ollama round bitta iteration hisoblanadi; oxirgi ruxsat etilgan round yana tool so'rasa loop `AGENT_ITERATION_LIMIT` bilan to'xtaydi.
- Per-tool timeout ownership: sync tool timeout bo'lsa caller tez natija oladi, lekin global tool slot background operation tugamaguncha band qoladi.
- Total deadline: Ollama call va tool execution qolgan umumiy deadline bilan cheklanadi; deadline tugasa `AGENT_TOTAL_TIMEOUT` qaytadi.
- Cancellation: async tool cancel qilinadi, sync `to_thread` kill qilinmaydi, slot faqat underlying operation tugaganda release bo'ladi.
- Tool result budget: single result va total result char limitlari bor, truncate metadata saqlanadi.
- Audit privacy: raw query, raw arguments, excerpt va internal path auditga yozilmaydi.
- Human approval keyingi phase'da qo'shiladi; bu bosqichda faqat read-only automatic execution bor.
- Write, shell, Python, web, browser va autonomous background tool'lar mavjud emas.

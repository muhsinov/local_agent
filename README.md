# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Hozir FastAPI backend, Ollama chat, SQLite conversation storage, xavfsiz document upload, isolated extraction, deterministic chunking, multilingual embeddings, FAISS indexing, semantic search va grounded RAG chat mavjud.

Primary specification: [TZ.md](TZ.md)

## Phase 7 imkoniyatlari

- document upload, preview va delete
- deterministic chunking
- multilingual embedding modeli: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- FAISS cosine search: `IndexIDMap2(IndexFlatIP)`
- manual index rebuild va status
- semantic search
- grounded RAG chat
- source citations
- fallback behavior va strict mode
- generation artifact lifecycle va startup recovery
- explicit read-only local tools
- approval-gated write actions: `rename_conversation`, `rebuild_vector_index`
- exact-action human approval, one-time nonce va idempotent lifecycle

`/chat` ixtiyoriy RAG context va tool calling ishlatadi. Write action approvalsiz bajarilmaydi.

## Dependency versiyalari

- `fastapi==0.116.1`
- `uvicorn==0.35.0`
- `pydantic==2.11.7`
- `pydantic-settings==2.10.1`
- `python-dotenv==1.1.1`
- `pytest==8.4.1`
- `httpx==0.28.1`
- `python-multipart==0.0.32`
- `pypdf==6.14.2`
- `python-docx==1.2.0`
- `psutil==6.1.1`
- `sentence-transformers==5.6.0`
- `faiss-cpu==1.14.3`

## Talablar

- Windows 10 yoki yangi
- Python 3.11+
- Ollama ixtiyoriy, lekin chat uchun kerak
- embedding model cache uchun disk joy
- 8 GB RAM tavsiya etiladi

## Setup

```powershell
.\scripts\setup.ps1
```

Execution policy muammosi bo'lsa:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Embedding model tayyorlash

```powershell
.\scripts\prepare_embeddings.ps1
```

Offline mode uchun:

```env
EMBEDDING_LOCAL_FILES_ONLY=true
```

Bu faqat model avval cache qilingan bo'lsa ishlaydi.

## Ollama

```powershell
.\scripts\prepare_ollama.ps1
```

## Start

```powershell
.\scripts\start.ps1
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Muhim config

- `CHUNK_SIZE_CHARS`
- `CHUNK_OVERLAP_CHARS`
- `CHUNK_MIN_CHARS`
- `MAX_CHUNKS_PER_DOCUMENT`
- `VECTOR_SEARCH_TOP_K`
- `VECTOR_SEARCH_MAX_K`
- `VECTOR_MIN_SCORE`
- `VECTOR_INDEX_DIRECTORY=data/vector_store`
- `VECTOR_INDEX_BUSY_TIMEOUT_SECONDS`
- `VECTOR_INDEX_GENERATION_RETENTION`
- `RAG_ENABLED`
- `RAG_TOP_K`
- `RAG_MAX_TOP_K`
- `RAG_MAX_CONTEXT_CHARS`
- `RAG_MAX_SOURCES`
- `RAG_REQUIRE_SOURCES`
- `RAG_ALLOW_FALLBACK_WITHOUT_INDEX`
- `RAG_PROMPT_MAX_CHARS`
- `RAG_RESERVED_ANSWER_TOKENS`
- `RAG_CHARS_PER_TOKEN_ESTIMATE`
- `TOOLS_ENABLED`
- `AGENT_MAX_ITERATIONS`
- `AGENT_TOTAL_TIMEOUT_SECONDS`
- `AGENT_TOOL_TIMEOUT_SECONDS`
- `AGENT_MAX_TOOL_CALLS`
- `AGENT_MAX_TOOL_RESULT_CHARS`
- `AGENT_MAX_SINGLE_TOOL_RESULT_CHARS`
- `AGENT_REQUIRE_EXPLICIT_TOOL_INTENT`
- `APPROVALS_ENABLED`
- `APPROVAL_EXPIRY_SECONDS`
- `APPROVAL_NONCE_BYTES`
- `APPROVAL_MAX_PENDING`
- `APPROVAL_EXECUTION_TIMEOUT_SECONDS`

## API

- `GET /health`
- `GET /model/status`
- `POST /chat`
- `GET /approvals/{id}`
- `POST /approvals/{id}/approve`
- `POST /approvals/{id}/reject`
- `POST /documents/upload`
- `GET /documents`
- `GET /documents/{id}`
- `GET /documents/{id}/text`
- `DELETE /documents/{id}?confirm=true`
- `POST /documents/{id}/index`
- `POST /vector-index/rebuild`
- `GET /vector-index/status`
- `POST /vector-search`
- `POST /chat` with `use_rag` and optional `document_ids`

## RAG chat

- frontenddagi `Use documents` checkbox retrievalni yoqadi yoki o'chiradi
- successful RAG javoblarda source citations va source cards qaytadi
- dirty yoki empty index holatida fallback allowed bo'lsa oddiy chat davom etadi
- strict mode (`RAG_REQUIRE_SOURCES=true`) fallback o'rniga error qaytaradi
- document content untrusted material hisoblanadi
- prompt injection himoyasi delimiters va system prompt qoidalari bilan bajariladi
- citation numbering deterministic `[1]`, `[2]`, ...
- prompt budget approximate character-based bo'lib, exact tokenizer emas
- default hisob `4 chars/token` estimate bilan qilinadi
- answer generation uchun alohida reserve joy ajratiladi
- actual tokenizer va tilga qarab uzunlik farq qiladi, ayniqsa Uzbek/Russian matnda estimate aniq bo'lmasligi mumkin
- konservativ xavfsizlik uchun budget configlarini kamaytirish mumkin
- budget priority: safety system prompt, current user message, document context, undan keyin newest history
- history budgetdan oshsa eng eski xabarlar tushiriladi
- context source blocklari budgetga sig'masa excerpt qisqartiriladi yoki block tashlab ketiladi
- markdown link va image label ichidagi `[1](...)`, `![1](...)` citation deb olinmaydi
- invalid citation normalization multiline formattingni imkon qadar saqlaydi, lekin har doim to'liq markdown parser emas

## Read-only tools

- `Use tools` yoqilganda agent faqat explicit read-only local tool allowlist'dan foydalanadi
- mavjud read-only tool'lar: documents list/metadata/excerpt/search, conversations list/messages, safe local system info
- write tool'lar faqat approval bilan: `rename_conversation`, `rebuild_vector_index`
- explicit intent kerak: umumiy savol tool loopni avtomatik boshlamaydi
- shell, delete, web request, browser automation, arbitrary filesystem write va secret/environment read yo'q
- tool output untrusted data hisoblanadi
- bounded loop: iteration, tool call va timeout limitlari bor
- audit faqat safe metadata yozadi; raw arguments va raw results saqlanmaydi
- approval lifecycle: `pending -> executing -> executed|failed` yoki `pending -> rejected|expired`
- approval execution lifecycle request'dan mustaqil coordinator task tomonidan boshqariladi; cancellation taskni bekor qilmaydi
- stale `executing` approval startup/request-time recovery'da `APPROVAL_EXECUTION_INTERRUPTED` bilan failed qilinadi
- rebuild caller timeout'da `202/executing` qaytarishi mumkin; real operation tugamaguncha approval failed qilinmaydi
- resume prompt `<documents>` va `<approved_action_result>` boundary'larida untrusted XML-safe data sifatida bounded qilinadi
- resume system, original user, action, RAG va newest history bitta unified prompt budgetda hisoblanadi
- final exchange va approval `executed` CAS bitta SQLite transactionda yoziladi
- approval o'chirilgan bo'lsa chat/approve/reject stable `403 APPROVALS_DISABLED` qaytaradi
- nonce faqat creation response'da qaytadi, localStorage/sessionStorage'da saqlanmaydi
- exact action binding canonical argument hash bilan tekshiriladi
- known limitation: write action bajarilib, keyingi final response generation yoki DB save yiqilishi mumkin; bunday approval `failed` bo'ladi

## Vector index lifecycle

- artifactlar `data/vector_store/generations/<generation-id>/` ichida saqlanadi
- generation ichida `index.faiss` va `manifest.json` bo'ladi
- rebuild vaqtida avval `.building` katalog ishlatiladi
- upload yoki delete'dan keyin index `dirty=1` bo'lishi mumkin
- dirty holatda semantic search ishlamaydi, rebuild kerak

## Storage

- raw upload fayllar: `data/uploads`
- extracted text fayllar: `data/extracted`
- vector artifactlar: `data/vector_store`
- Hugging Face cache repository ichiga kirmaydi

## Hozirgi cheklovlar

- background indexing yo'q
- reranker yo'q
- advanced vector DB yo'q
- scanned PDF uchun OCR yo'q

## Common errors

- `DOCUMENT_HAS_NO_TEXT`
- `DOCUMENT_CHUNK_LIMIT_EXCEEDED`
- `NO_INDEXABLE_DOCUMENTS`
- `VECTOR_INDEX_EMPTY`
- `VECTOR_INDEX_NOT_READY`
- `VECTOR_INDEX_CORRUPT`
- `VECTOR_INDEX_BUSY`
- `VECTOR_SEARCH_INVALID_QUERY`
- `EMBEDDING_MODEL_UNAVAILABLE`
- `EMBEDDING_MODEL_DIMENSION_MISMATCH`
- `EMBEDDING_INVALID_RESPONSE`

# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Hozir FastAPI backend, Ollama chat, SQLite conversation storage, xavfsiz document upload, isolated extraction, deterministic chunking, multilingual embeddings, FAISS indexing, semantic search va grounded RAG chat mavjud.

Primary specification: [TZ.md](TZ.md)

## Phase 8 local control-plane security

- loopback Host va Origin/Referer validation DNS rebinding va cross-site state-changing requestlarga qarshi ishlaydi
- browser session `POST /session/bootstrap` orqali bounded in-memory TTL bilan yaratiladi
- valid cookie reload paytida active session qayta ishlatiladi; bitta session parallel tablar uchun bounded `LOCAL_SESSION_MAX_CSRF_TOKENS` CSRF token saqlaydi
- bootstrap local Origin yoki Referer talab qiladi va CSRF secret response'i `no-store` bilan qaytariladi
- POST/PUT/PATCH/DELETE uchun session-bound `X-CSRF-Token` talab qilinadi; approval nonce CSRF token o'rnini bosmaydi
- CORS explicit configured loopback originlar bilan cheklangan, lekin CORS CSRF himoyasi hisoblanmaydi
- direct vector mutation va document delete default disabled; vector rebuild tavsiya etilgan approval-gated tool oqimi orqali bajariladi
- non-browser client default disabled; opt-in uchun kamida 32 character `LOCAL_API_TOKEN` kerak
- frontend tokenni faqat memory'da saqlaydi va state-changing requestlar uchun yagona `localFetch` wrapper ishlatadi
- frontend faqat `LOCAL_SESSION_REQUIRED`, `CSRF_TOKEN_REQUIRED` yoki `CSRF_TOKEN_INVALID` uchun bir marta bootstrap qilib original requestni retry qiladi
- Origin va Sec-Fetch headerlari OS-level local process authentication emas; himoya remote web-origin va tasodifiy unauthenticated client threat modeliga mo'ljallangan

## Phase 9 runtime resilience

- request flood uchun chat, upload, approval, bootstrap, read va direct mutation guruhlarida fixed-window rate limit mavjud
- valid session internal hash, non-browser client esa `local-api-client` identity bilan limitlanadi; raw token/session/IP ishlatilmaydi
- limit oshsa `429 RATE_LIMIT_EXCEEDED`, `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` va reset headerlari qaytadi
- har response server-generated `X-Request-ID` oladi; request body va sensitive content safe logga yozilmaydi
- rotating JSONL log `data/logs/local-agent.jsonl`da saqlanadi va repositoryga kirmaydi
- JSON mutation body `REQUEST_BODY_MAX_BYTES` bilan Content-Length guardga ega; multipart upload streaming file limitidan foydalanadi
- `/live` dependency-free liveness, `/ready` startup/database/vector/draining readiness beradi
- shutdown draining holatiga o‘tadi, yangi expensive requestlarni `503 SERVER_DRAINING` bilan to‘xtatadi va umumiy deadline bilan mavjud ishlarni kutadi
- approval polling one-shot scheduler va bounded `Retry-After` backoff bilan parallel status/result requestlarini cheklaydi
- limiter expired bucketlarni tozalaydi va max bucket bound ichida deterministik eviction qiladi
- direct-disabled policy CSRF/authdan keyin, rate limitdan oldin bajariladi
- shutdown dependency drain tartibi approval -> tool -> vector -> Ollama bo‘lib, bitta absolute deadline bilan ishlaydi
- generic 500 javoblari safe JSON va reusable security headers bilan qaytadi
- API va static frontend security headerlari, static HTML uchun strict CSP yoqilgan
- limiter va lifecycle single-process in-memory; multi-worker deployment uchun shared store kerak

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
- `LOCAL_CONTROL_PLANE_ENABLED`
- `LOCAL_SESSION_TTL_SECONDS`
- `LOCAL_SESSION_MAX_ACTIVE`
- `LOCAL_SESSION_TOKEN_BYTES`
- `LOCAL_CSRF_TOKEN_BYTES`
- `LOCAL_SESSION_MAX_CSRF_TOKENS`
- `LOCAL_REQUIRE_CSRF`
- `LOCAL_REQUIRE_LOOPBACK_HOST`
- `LOCAL_ALLOW_NON_BROWSER_CLIENTS`
- `LOCAL_API_TOKEN`
- `DIRECT_VECTOR_MUTATIONS_ENABLED`
- `DIRECT_DOCUMENT_DELETE_ENABLED`

## API

- `GET /health`
- `GET /model/status`
- `POST /chat`
- `POST /session/bootstrap`
- `GET /approvals/{id}`
- `POST /approvals/{id}/approve`
- `POST /approvals/{id}/result`
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

State-changing browser API requestlari avval local session bootstrap qiladi va `X-CSRF-Token` yuboradi. Direct index/rebuild/delete endpointlari default holatda yopiq; approval workflow mavjud `rebuild_vector_index` action uchun ishlaydi.

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
- approval schema v6 `execution_deadline_at` va `result_message_id` bilan eski v4/v5 database'larni transactional repair qiladi
- stale `executing` approval startup/request-time recovery'da `APPROVAL_EXECUTION_INTERRUPTED` bilan failed qilinadi
- rebuild caller timeout'da `202/executing` qaytarishi mumkin; real operation tugamaguncha approval failed qilinmaydi
- `POST /approvals/{id}/result` exact persisted assistant message'ni qaytaradi va write actionni qayta bajarmaydi
- Immediate/delayed approval result frontend'da bitta renderer orqali answer, source cards, RAG metadata va usage'ni yangilaydi
- Delayed `/result` transient xatolarda nonce va pollingni saqlab retry qiladi; faqat successful result'dan keyin yakunlanadi
- Delayed source metadata raw excerpt emas, prompt excerptni tiklash uchun safe numeric/reference qiymatlarni saqlaydi
- resume prompt `<documents>` va `<approved_action_result>` boundary'larida untrusted XML-safe data sifatida bounded qilinadi
- resume system, original user, action, RAG va newest history bitta unified prompt budgetda hisoblanadi
- final exchange va approval `executed` CAS bitta SQLite transactionda yoziladi
- approval o'chirilgan bo'lsa chat/approve/reject stable `403 APPROVALS_DISABLED` qaytaradi
- resume RAG citationlari source count bilan normalize qilinadi; RAG bo'lmagan resume citation markerlarini olib tashlaydi
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

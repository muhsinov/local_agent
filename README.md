# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Hozir FastAPI backend, Ollama chat, SQLite conversation storage, xavfsiz document upload, isolated extraction, deterministic chunking, multilingual embeddings, FAISS indexing, semantic search va grounded RAG chat mavjud.

Primary specification: [TZ.md](TZ.md)

## Phase 5 imkoniyatlari

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

`/chat` endi ixtiyoriy RAG context ishlatadi. Tool calling hali yo'q.

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

## API

- `GET /health`
- `GET /model/status`
- `POST /chat`
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
- mavjud tool'lar: documents list/metadata/excerpt/search, conversations list/messages, safe local system info
- explicit intent kerak: umumiy savol tool loopni avtomatik boshlamaydi
- shell, write access, web request, browser automation va secret/environment read yo'q
- tool output untrusted data hisoblanadi
- bounded loop: iteration, tool call va timeout limitlari bor
- audit faqat safe metadata yozadi; raw arguments va raw results saqlanmaydi
- known limitation: tool calling native OS execution emas, faqat lokal metadata va extracted text read-only access

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

- `/chat` RAG ishlatsa ham tool calling qilmaydi
- background indexing yo'q
- reranker yo'q
- tool calling yo'q
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

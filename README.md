# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Hozir FastAPI backend, Ollama chat, SQLite conversation storage, xavfsiz document upload, isolated extraction, deterministic chunking, multilingual embeddings, FAISS indexing va semantic search mavjud.

Primary specification: [TZ.md](TZ.md)

## Phase 4 imkoniyatlari

- document upload, preview va delete
- deterministic chunking
- multilingual embedding modeli: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- FAISS cosine search: `IndexIDMap2(IndexFlatIP)`
- manual index rebuild va status
- semantic search
- generation artifact lifecycle va startup recovery

`/chat` hali RAG context ishlatmaydi.

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

- `/chat` hali semantic search yoki document chunklarni promptga ulmaydi
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

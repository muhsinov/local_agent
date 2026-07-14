# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Hozir FastAPI backend, Ollama chat, SQLite conversation storage, xavfsiz document upload va isolated text extraction mavjud.

Primary specification: [TZ.md](TZ.md)

## Hozirgi imkoniyatlar

- `/health`
- `/model/status`
- `/chat`
- `/documents/upload`
- `/documents`
- `/documents/{id}`
- `/documents/{id}/text`
- `DELETE /documents/{id}?confirm=true`

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

## Talablar

- Windows 10 yoki yangi
- Python 3.11+
- Ollama ixtiyoriy, lekin chat uchun kerak
- Tavsiya etilgan model: `qwen3:1.7b`

## Setup

```powershell
.\scripts\setup.ps1
```

Execution policy muammosi bo'lsa:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Ollama

```powershell
.\scripts\prepare_ollama.ps1
```

Qo'lda:

```powershell
ollama pull qwen3:1.7b
```

## Start

```powershell
.\scripts\start.ps1
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Supported document formatlar

- `.pdf`
- `.docx`
- `.txt`
- `.md`

Qo'llab-quvvatlanmaydi: `.doc`, `.rtf`, `.odt`, `.html`, executable fayllar, noto'g'ri signature'li soxta fayllar.

## Document limitlar

- maksimal fayl hajmi: `MAX_FILE_SIZE_MB`
- upload chunk: `UPLOAD_CHUNK_SIZE_KB`
- PDF sahifa limiti: `MAX_PDF_PAGES`
- PDF page content limiti: `MAX_PDF_PAGE_CONTENT_MB`
- extracted text limiti: `MAX_EXTRACTED_CHARS`
- DOCX archive limitlari: zip entry count, uncompressed size, compression ratio
- extraction timeout: `DOCUMENT_EXTRACTION_TIMEOUT_SECONDS`
- extraction memory limiti: `DOCUMENT_EXTRACTION_MEMORY_MB`
- scanned PDF uchun OCR yo'q

## API

- App: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Model status: `http://127.0.0.1:8000/model/status`
- Chat: `http://127.0.0.1:8000/chat`
- Upload: `POST /documents/upload`
- List: `GET /documents?limit=50&offset=0`
- Metadata: `GET /documents/{id}`
- Preview: `GET /documents/{id}/text?limit=5000`
- Delete: `DELETE /documents/{id}?confirm=true`

Windows PowerShell 5.1 `Invoke-RestMethod -Form` qo'llamasa:

```powershell
curl.exe -F "file=@sample.txt" http://127.0.0.1:8000/documents/upload
```

## Hozirgi cheklovlar

- chat hali upload qilingan hujjatlarni ishlatmaydi
- RAG keyingi bosqich
- embeddings yo'q
- FAISS yo'q
- tool calling yo'q
- document extraction bir vaqtning o'zida faqat bitta request
- extraction spawned subprocess ichida bajariladi
- chat bir vaqtning o'zida faqat bitta request

## Storage

- raw upload fayllar: `data/uploads`
- extracted text fayllar: `data/extracted`
- bu fayllar Git'ga kirmaydi
- API response'larda internal path yoki absolute Windows path qaytarilmaydi

## Common errors

- `FILE_TOO_LARGE`
- `UNSUPPORTED_FILE_TYPE`
- `FILE_TYPE_MISMATCH`
- `INVALID_TEXT_ENCODING`
- `INVALID_PDF`
- `PDF_ENCRYPTED`
- `UNSAFE_DOCX_ARCHIVE`
- `DOCUMENT_DUPLICATE`
- `DOCUMENT_STORAGE_ERROR`
- `DOCUMENT_PROCESSOR_BUSY`
- `DOCUMENT_EXTRACTION_TIMEOUT`
- `DOCUMENT_EXTRACTION_MEMORY_LIMIT`
- `DOCUMENT_PROCESSING_ERROR`
- `CONFIRMATION_REQUIRED`

## Eslatma

Upload qilingan hujjatlar hozircha faqat saqlanadi, extract qilinadi, preview qilinadi va o'chiriladi. Ular `/chat` promptiga ulanmagan.

# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan lokal AI assistant poydevori. Bu bosqichda FastAPI backend, SQLite conversation storage, Ollama integratsiyasi va oddiy web chat UI mavjud.

Primary specification: [TZ.md](TZ.md)

## Hozirgi imkoniyatlar

- `/health` endpoint
- `/model/status` endpoint
- `/chat` endpoint orqali real lokal model chat
- SQLite'da conversation va messages tarixi
- frontend orqali chat yuborish
- PowerShell setup, start va Ollama tayyorlash scriptlari
- `pytest` bilan mock asosidagi testlar

## Talablar

- Windows 10 yoki yangi
- Python 3.11+
- Ollama o‘rnatilgan
- Tavsiya etilgan model: `qwen3:1.7b`

## Setup

```powershell
.\scripts\setup.ps1
```

Execution policy muammosi bo‘lsa:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Ollama tayyorlash

```powershell
.\scripts\prepare_ollama.ps1
```

Agar modelni qo‘lda yuklamoqchi bo‘lsangiz:

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

## Browser va API

- App: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Model status: `http://127.0.0.1:8000/model/status`
- Chat: `http://127.0.0.1:8000/chat`

## Chat request namunasi

```json
{
  "message": "Salom, o'zingni qisqa tanishtir",
  "conversation_id": null
}
```

## Chat response namunasi

```json
{
  "conversation_id": 1,
  "answer": "Salom, men sizning lokal AI assistentingizman.",
  "model": "qwen3:1.7b",
  "sources": [],
  "tool_calls": [],
  "execution_time_ms": 1840,
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 42
  }
}
```

## Model status namunasi

```json
{
  "ollama": "ok",
  "model": "qwen3:1.7b",
  "installed": true
}
```

## Ishlash cheklovlari

- 8 GB RAM uchun bir vaqtning o‘zida faqat bitta chat request bajariladi
- modelga faqat oxirgi 6 ta message yuboriladi
- hozircha RAG yo‘q
- hozircha tool calling yo‘q

## Keng tarqalgan xatolar

- Ollama topilmadi: `scripts/prepare_ollama.ps1` xato beradi, Ollama ilovasini o‘rnating
- Ollama server ishlamayapti: Ollama app yoki service’ni ishga tushiring
- Model o‘rnatilmagan: `ollama pull qwen3:1.7b`
- Timeout: katta prompt yoki sekin model javobi
- Port band: `8000` portni boshqa process ishlatmayotganini tekshiring

## Papka strukturasi

```text
local_agent/
|-- app/
|-- docs/
|-- data/
|-- scripts/
|-- tests/
|-- .env.example
|-- README.md
|-- requirements.txt
`-- TZ.md
```

## Hozircha yo‘q

- RAG
- tool calling
- embeddings
- FAISS
- document upload

# Local Agent Demo

`Local Agent Demo` Windows 10 va Python 3.11 uchun Docker'siz ishlaydigan minimal local agent poydevori. Ushbu bosqich FastAPI backend, SQLite init, oddiy chat UI va testlarni tayyorlaydi.

Primary specification: [TZ.md](D:/local_agent/TZ.md)

## Hozirgi bosqich imkoniyatlari

- FastAPI server va `/health` endpoint
- `/` da oddiy chat interfeysi
- `.env` orqali konfiguratsiya
- SQLite bazasini avtomatik yaratish
- `data/uploads` va `data/vector_store` kataloglarini tayyorlash
- PowerShell setup, start, va system-check scriptlari
- `pytest` bilan minimal test
- LLM hali ulanmagan demo chat placeholder

## Talablar

- Windows 10 yoki yangi versiya
- Python 3.11+
- PowerShell

## Setup

```powershell
.\scripts\setup.ps1
```

Agar execution policy scriptni bloklasa, xavfsiz vaqtinchalik yechim:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Keyin yana setup yoki start scriptni ishga tushiring.

## Start

```powershell
.\scripts\start.ps1
```

Bu bosqichda real LLM ulanmagan. UI xabar yuborganda placeholder javob qaytaradi.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Browser URL

- App: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`

## Database schema version

SQLite database `schema version 1` bilan yaratiladi. Ilova startup vaqtida schema tekshiriladi; eski va bo'sh development schema topilsa xavfsiz qayta yaratiladi, ma'lumotli database esa avtomatik destructive migration qilinmaydi.

## Papka strukturasi

```text
local_agent/
├── app/
├── data/
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── TZ.md
```

## Kelajakdagi bosqichlar

- Ollama chat integratsiyasi
- RAG va vector store ishlatish
- Hujjat yuklash oqimi
- Audit va conversation funksiyalarini kengaytirish
- Tool calling va agent orchestration

## Eslatma

Hozirgi bosqich faqat loyiha poydevori uchun. Ollama, chat backend, RAG, FAISS va document upload hali ulanmagan.

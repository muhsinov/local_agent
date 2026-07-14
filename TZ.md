`local_agent` papkasidagi `TZ.md` faylini to'liq o'qib chiq va loyiha talablarini asosiy manba sifatida qabul qil.

Hozir faqat **1-bosqich: loyiha poydevori va minimal ishlaydigan FastAPI ilovasi**ni implement qil.

## Maqsad

Windows 10, 8 GB RAM va Python 3.11 muhitida Docker'siz ishlaydigan minimal local agent backend va oddiy frontend tayyorlash.

Bu bosqich yakunida loyiha:

- virtual environment orqali o'rnatilishi;
- FastAPI server ishga tushishi;
- brauzerda oddiy chat interfeysi ochilishi;
- health endpoint ishlashi;
- konfiguratsiya `.env` orqali boshqarilishi;
- SQLite bazasi avtomatik yaratilishi;
- testlar ishlashi kerak.

## Hozir implement qilinadigan qismlar

Quyidagi papka va fayllarni yarat:

```text
local_agent/
|-- app/
|   |-- __init__.py
|   |-- main.py
|   |-- config.py
|   |-- database.py
|   |
|   |-- api/
|   |   |-- __init__.py
|   |   `-- health.py
|   |
|   `-- static/
|       |-- index.html
|       |-- app.js
|       `-- styles.css
|
|-- data/
|   |-- uploads/
|   `-- vector_store/
|
|-- scripts/
|   |-- setup.ps1
|   |-- start.ps1
|   `-- check_system.ps1
|
|-- tests/
|   |-- __init__.py
|   `-- test_health.py
|
|-- .env.example
|-- .gitignore
|-- requirements.txt
|-- README.md
`-- TZ.md
```

## FastAPI talablari

`app/main.py`:

- FastAPI application yaratsin.
- Application nomi `Local Agent Demo` bo'lsin.
- Static fayllarni `/static` orqali serve qilsin.
- `/` endpoint `app/static/index.html` faylini qaytarsin.
- Health router'ni ulasin.
- Startup vaqtida kerakli `data` papkalari va SQLite database yaratilishini ta'minlasin.
- Development uchun CORS faqat localhost manzillariga ruxsat bersin.

## Health endpoint

Quyidagi endpoint bo'lsin:

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "app": "local-agent-demo",
  "version": "0.1.0",
  "database": "ok"
}
```

Database mavjud bo'lmasa yoki ishga tushmasa, `database` qiymati `error` bo'lsin va endpoint mos HTTP status qaytarsin.

## Konfiguratsiya

`app/config.py` da Pydantic Settings ishlat.

Quyidagi sozlamalar `.env` orqali boshqarilsin:

```env
APP_NAME=Local Agent Demo
APP_VERSION=0.1.0
HOST=127.0.0.1
PORT=8000
DATABASE_PATH=data/local_agent.db
UPLOAD_DIRECTORY=data/uploads
VECTOR_STORE_DIRECTORY=data/vector_store
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:1.7b
REQUEST_TIMEOUT_SECONDS=90
MAX_AGENT_ITERATIONS=5
MAX_FILE_SIZE_MB=10
```

`.env.example` faylida barcha qiymatlar bo'lsin.

Haqiqiy `.env` Git'ga qo'shilmasin.

## SQLite

`app/database.py`:

- Standard `sqlite3` modulidan foydalan.
- SQLAlchemy hozircha kerak emas.
- Database va parent directory avtomatik yaratilsin.
- Kamida quyidagi jadvallar yaratilishi kerak:

```sql
conversations
messages
documents
audit_logs
```

`TZ.md` dagi ustunlarga mos schema ishlat.

Foreign key'lar yoqilsin.

Database initialization funksiyasi idempotent bo'lsin.

## Frontend

Oddiy HTML, CSS va JavaScript ishlat.

Interfeysda:

- loyiha nomi;
- backend health status;
- model status uchun placeholder;
- chat message maydoni;
- Send tugmasi;
- chat tarixini ko'rsatadigan panel;
- "RAG hali ulanmagan" degan tushunarli belgi bo'lsin.

Bu bosqichda Send tugmasi real LLM chaqirmasin.

Foydalanuvchi xabar yuborganda frontend vaqtincha quyidagi javobni ko'rsatsin:

```text
Local model hali ulanmagan. Keyingi bosqichda Ollama integratsiyasi qo'shiladi.
```

HTML inline CSS yoki katta inline JavaScript ishlatmasin.

## PowerShell scriptlar

### `scripts/setup.ps1`

Quyidagilarni bajarsin:

1. Python mavjudligini tekshirsin.
2. Python versiyasi kamida 3.11 ekanligini tekshirsin.
3. `.venv` yaratilsin.
4. Virtual environment ichida pip yangilansin.
5. `requirements.txt` o'rnatilsin.
6. `.env` mavjud bo'lmasa `.env.example` dan nusxa olinsin.
7. Kerakli data papkalari yaratilsin.
8. Yakunda keyingi ishga tushirish buyrug'i ko'rsatilsin.

Script xatolik yuz bersa darhol to'xtasin.

### `scripts/start.ps1`

- `.venv` mavjudligini tekshirsin.
- Virtual environment Python orqali Uvicorn ishga tushirsin.
- Host va port `.env` dan olinishi yoki default `127.0.0.1:8000` ishlatilishi kerak.
- Reload development rejimida yoqilsin.

### `scripts/check_system.ps1`

Quyidagilarni chiqarib bersin:

- Python versiyasi
- CPU nomi
- RAM hajmi
- GPU nomi
- C diskdagi bo'sh joy
- Ollama o'rnatilgan yoki o'rnatilmaganligi

Bu script hech qanday tizim sozlamasini o'zgartirmasin.

## Dependency'lar

`requirements.txt` minimal bo'lsin. Faqat zarur dependency'larni qo'sh:

- fastapi
- uvicorn
- pydantic
- pydantic-settings
- python-dotenv
- pytest
- httpx

Versiyalarni bir-biriga mos va barqaror qilib pin qil.

Hozircha quyidagilarni qo'shma:

- langchain
- llama-index
- faiss
- sentence-transformers
- torch
- ollama Python package
- sqlalchemy
- docker dependency

## Testlar

`tests/test_health.py`:

- `/health` endpoint `200` qaytarishini tekshirsin.
- JSON response kerakli field'larni saqlashini tekshirsin.
- Test vaqtida production database'ni ishlatmasin.
- Temporary database yoki test config ishlat.

Barcha testlar quyidagi buyruqda o'tishi kerak:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## README

README'da:

- loyiha maqsadi;
- hozirgi bosqich imkoniyatlari;
- talablar;
- setup;
- start;
- test;
- browser URL;
- papka strukturasi;
- kelajakdagi bosqichlar;
- Windows PowerShell execution policy muammosi bo'lsa xavfsiz yechim yozilsin.

## Kod sifati

- Type hint ishlat.
- Funksiyalar qisqa va aniq bo'lsin.
- Hardcoded absolute path ishlatma.
- Barcha path'lar project root'ga nisbatan xavfsiz resolve qilinsin.
- Import vaqtida server yoki database'da kutilmagan side effect bo'lmasin.
- Xatoliklar tushunarli qaytarilsin.
- Keraksiz abstraction yaratma.
- Hozircha agent framework yozma.
- `TZ.md` faylini o'zgartirma.

## Tekshirish

Implementatsiyadan keyin:

1. `setup.ps1` ni ishga tushir.
2. Testlarni ishga tushir.
3. Serverni ishga tushirib `/health` va `/` endpoint'larni tekshir.
4. Topilgan xatolarni tuzat.
5. `git status` bilan keraksiz fayllar commit qilinmayotganini tekshir.

## Git va GitHub

Agar papka hali Git repository bo'lmasa:

```bash
git init
```

Default branch:

```text
main
```

Commit message:

```text
feat: bootstrap local agent FastAPI project
```

GitHub'da private repository yarat:

```text
local-agent-demo
```

Agar shu nom band bo'lsa:

```text
local-agent-demo-windows
```

Remote'ni ulab `main` branch'ni push qil.

GitHub repository yaratish yoki push qilish uchun autentifikatsiya kerak bo'lsa, mavjud GitHub/Codex integratsiyasidan foydalan. Maxfiy token yoki credential'larni fayllarga yozma.

## Yakuniy hisobot

Ish tugagach quyidagilarni aniq ko'rsat:

- yaratilgan asosiy fayllar;
- o'rnatilgan dependency'lar;
- test natijasi;
- `/health` tekshiruvi;
- repository nomi;
- branch nomi;
- commit hash;
- push muvaffaqiyatli yoki yo'qligi;
- keyingi bosqich uchun qolgan ishlar.

Faqat ushbu bosqichni implement qil. Ollama chat, RAG, hujjat yuklash va tool calling'ni hozir qo'shma.

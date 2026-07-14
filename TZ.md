# Local Agent Technical Specification

## Scope

`Local Agent Demo` Windows 10 da Docker'siz ishlaydigan lokal AI assistant bo'lishi kerak. Asosiy texnologiyalar:

- Python 3.11+
- FastAPI backend
- SQLite
- Ollama
- oddiy HTML, CSS va JavaScript frontend

## Target Hardware

Loyiha quyidagi resurslarga mos ishlashi kerak:

- Intel i5-12450H
- 8 GB RAM
- NVIDIA GTX 1650 4 GB VRAM

Shu sababli model, context va parallel requestlar konservativ bo'lishi kerak.

## Core Requirements

- Lokal chat Ollama orqali ishlashi kerak.
- Default model `qwen3:1.7b` bo'lishi kerak.
- Backend FastAPI app factory asosida qurilishi kerak.
- Konfiguratsiya `.env` orqali boshqarilishi kerak.
- SQLite conversation, messages, documents va audit log ma'lumotlarini saqlashi kerak.
- Frontend browser ichida lokal chat uchun minimal UI berishi kerak.
- Testlar real production database yoki live external dependency'ga qaram bo'lmasligi kerak.
- PowerShell `setup` va `start` scriptlari mavjud bo'lishi kerak.

## LLM Constraints

- Default model: `qwen3:1.7b`
- `max_iterations=5`
- faqat bitta parallel LLM request
- timeout konfiguratsiya orqali boshqariladi
- read-only default permission yondashuvi
- tool calling kelajakda faqat allowlist asosida qo'shiladi

## Security and Safety

- Path traversal protection bo'lishi kerak.
- Raw stack trace va local path API response'ga chiqmasligi kerak.
- Audit logging qo'llab-quvvatlanishi kerak.
- Chat content to'liq log qilinmasligi kerak.
- Default holatda tizimda destructive yoki write-heavy actionlar yoqilmagan bo'lishi kerak.

## Storage

- SQLite asosiy lokal database bo'lishi kerak.
- Kelajakda FAISS va multilingual embedding qo'llab-quvvatlanishi mumkin.
- Conversation tarixi lokal saqlanishi kerak.

## Document and RAG Roadmap

Kelajakdagi bosqichlarda quyidagilar qo'shiladi:

- PDF, DOCX, TXT va MD upload
- RAG
- multilingual embedding
- FAISS vector store

Lekin hozircha bu funksiyalar bosqichma-bosqich, alohida implement qilinadi.

## Frontend

- Oddiy HTML/CSS/JavaScript
- Chat UI
- backend health ko'rinishi
- model status ko'rinishi
- keyingi bosqichlarda upload va RAG status

## Explicit Non-Goals

Quyidagilar ishlatilmaydi:

- Docker
- Kubernetes
- PostgreSQL
- Qdrant
- LangChain
- LlamaIndex

## Phase Documents

- 1-bosqich bootstrap prompti: [docs/phases/01-bootstrap.md](docs/phases/01-bootstrap.md)

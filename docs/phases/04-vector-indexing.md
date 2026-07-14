# Phase 4 - Vector Indexing

- Chunking deterministic bo'lib, paragraph, line, sentence, whitespace va hard boundary ustuvorligi bilan ishlaydi.
- Default embedding modeli `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, CPU-only va normalized `float32` vektorlar qaytaradi.
- FAISS cosine search `IndexIDMap2(IndexFlatIP)` orqali ishlaydi.
- Har rebuild yangi generation artifact yaratadi: `data/vector_store/generations/<generation-id>/index.faiss` va `manifest.json`.
- API endpointlar: `POST /documents/{id}/index`, `POST /vector-index/rebuild`, `GET /vector-index/status`, `POST /vector-search`.
- 8 GB RAM uchun model default unload qilinadi, batch size 16, bitta embedding operation va global rebuild strategiyasi ishlatiladi.
- `/chat` hali RAG context ishlatmaydi.

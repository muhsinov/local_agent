# Phase 3: Document Upload

## Maqsad

Lokal agent uchun xavfsiz hujjat yuklash, matn extraction va document management qatlamini qo'shish.

## Endpointlar

- `POST /documents/upload`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/text`
- `DELETE /documents/{document_id}?confirm=true`

## Xavfsizlik limitlari

- chunk bilan upload
- maksimal fayl hajmi `MAX_FILE_SIZE_MB`
- UUID asosidagi internal filename
- path traversal bloklanadi
- DOCX ZIP preflight
- PDF sahifa va content limitlari

## Qo'llab-quvvatlanadigan formatlar

- PDF
- DOCX
- TXT
- MD

## Extraction cheklovlari

- OCR yo'q
- scanned PDF `no_text` bo'lishi mumkin
- extraction hali bir vaqtning o'zida faqat bitta fayl uchun ishlaydi

## Eslatma

RAG hali ulanmagan. Upload qilingan hujjatlar `/chat` endpointiga avtomatik ulanmaydi.

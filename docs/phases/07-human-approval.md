# Phase 7 — human approval workflow

- Threat model: model output va frontend state untrusted. Write action faqat exact approved tool + exact approved arguments bilan bajariladi.
- Default policy: read-only tools approvalsiz ishlaydi, write tools esa approval-gated.
- Tool allowlist: faqat `rename_conversation` va `rebuild_vector_index`.
- Exact-action approval: approval record aniq `tool_name` va canonical `arguments_json` bilan bog'lanadi.
- Argument hash: canonical JSON `sha256` bilan hash qilinadi; approve vaqtida qayta canonical qilinib qayta tekshiriladi.
- One-time nonce: `secrets.token_urlsafe(APPROVAL_NONCE_BYTES)`; database'da faqat `nonce_sha256` saqlanadi.
- Expiry: `pending` request `APPROVAL_EXPIRY_SECONDS` dan keyin `expired` bo'ladi.
- Atomic state transition: `pending -> executing` va `pending -> rejected` compare-and-set SQL bilan bajariladi.
- Idempotency: `executed`, `rejected`, `failed`, `expired` holatlar qayta approve/reject qilinmaydi.
- Rejection va cancellation: reject write actionni bajarmaydi; cancelled chat/approve partial exchange yozmaydi.
- Resumable flow: approve'dan keyin write action bajariladi, so'ng final-only resume prompt bilan bitta final javob olinadi.
- Timeout: tool execution `APPROVAL_EXECUTION_TIMEOUT_SECONDS` bilan limitlangan.
- Privacy: audit nonce, nonce hash, raw arguments, original user message, final answer va raw tool resultni saqlamaydi.
- Origin policy: local browser origin ruxsat etiladi; origin yo'q bo'lsa nonce yetarli.
- No shell/destructive tools: shell, Python execution, web/browser, delete, arbitrary filesystem write va background autonomous action yo'q.
- Limitation: write action muvaffaqiyatli bo'lib, keyingi final model javobi yoki DB save muvaffaqiyatsiz tugashi mumkin; bunday holat `failed` sifatida saqlanadi.

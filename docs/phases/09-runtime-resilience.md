# Phase 9 - runtime resilience

- Threat model: a local browser or client can flood chat, upload, approval and read endpoints, exhausting a small machine's CPU, memory, database or model semaphore. The limiter is a local single-process control, not distributed abuse prevention.
- Backpressure: fixed-window in-memory limits are applied after Host/Origin, session/API-token and CSRF validation. Invalid authentication cannot spend a valid identity's bucket. Direct mutation limits do not enable actions; existing `DIRECT_ACTION_DISABLED` policy remains authoritative.
- Rate-limit identity: a valid browser session uses its internal server-side session hash; the configured non-browser API token uses the constant `local-api-client`; bootstrap uses one bounded global bucket. Raw cookie, token, host or IP values are never limiter keys or output.
- Groups: chat, upload, approval, bootstrap, read and direct mutation have independent configured windows. Exceeded requests return `429 RATE_LIMIT_EXCEEDED` with `Retry-After` and safe limit headers.
- Body guard: known JSON and URL-encoded mutation requests are rejected from `Content-Length` before parsing at `REQUEST_BODY_MAX_BYTES`. Multipart upload remains protected by its streaming file-size limit. Chunked oversized JSON is a known limitation and still relies on endpoint/Pydantic limits.
- Request correlation: every server response receives a server-generated `X-Request-ID`; client values are ignored. IDs are safe diagnostics only and are not associated with message, filename, nonce, token or body content.
- Safe logging: rotating JSONL logs contain only allowlisted request metadata. Logging failures are swallowed and never fail the request. `data/logs/` is runtime-only.
- Security headers: API and static responses receive nosniff, no-referrer, frame, permissions and opener policies. Static HTML receives a strict self-only CSP without `unsafe-inline`.
- Liveness/readiness: `/live` performs no dependency checks. `/ready` checks startup completion, draining state, database and safe vector metadata. Existing `/health` remains backward compatible.
- Draining: shutdown first disables admission, rejects expensive/state-changing work with `503 SERVER_DRAINING`, waits for tracked requests and coordinators under one global deadline, then closes the model client. Existing operations are not restarted.
- Lifecycle limitation: lifecycle, limiter and sessions are process-local in-memory state. Multiple workers would need shared coordination before this policy could be used as a multi-process service.

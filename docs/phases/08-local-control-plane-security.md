# Phase 8 - local control-plane security

- Trust boundary: the application is local, but a browser can be reached through a DNS-rebinding page or a cross-site request. Localhost is not treated as proof of caller intent.
- Host validation: API and static requests require an exact loopback Host (`localhost`, `127.0.0.1`, or `[::1]`) and the configured port. Suffixes, userinfo, malformed and comma-separated values are rejected.
- Origin policy: state-changing browser requests require a matching loopback Origin, or a matching Referer when Origin is absent. CORS is only a browser response policy; it is not CSRF protection and is enforced separately.
- Browser session: `POST /session/bootstrap` creates a bounded, expiring in-memory session. The HttpOnly SameSite cookie contains only the random session token; the server stores only its hash.
- CSRF token: the bootstrap response returns a random token that the frontend keeps in JavaScript memory and sends as `X-CSRF-Token`. The server stores only its hash and binds it to the session. It is never accepted in a query parameter, URL hash, browser storage, audit entry or log.
- State-changing methods: POST, PUT, PATCH and DELETE require a valid session and CSRF token. Bootstrap is the only mutation exception.
- Approval binding: approval endpoints require valid session, CSRF token and the existing exact approval nonce. An approval nonce never replaces the CSRF token.
- Direct mutation policy: direct vector index/rebuild and document delete endpoints are disabled by default with `DIRECT_ACTION_DISABLED`. The approval-gated `rebuild_vector_index` flow remains separate; no document-delete approval tool is added in this phase.
- Non-browser clients: disabled by default. Opt-in clients must use `Authorization: Bearer <LOCAL_API_TOKEN>` with a token of at least 32 characters. External browser Origin/Referer is rejected even when the API token is valid.
- Audit privacy: security audit entries contain only method, route template, reason, browser/session presence and host category. Cookies, session/CSRF values, API tokens, origins, referers and request bodies are not stored.
- Limitations: sessions are process-local and disappear on restart; this is intentional for a local control plane and is not a distributed authentication system.

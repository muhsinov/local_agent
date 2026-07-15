SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"x-frame-options": b"DENY",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
    b"cross-origin-opener-policy": b"same-origin",
}


def add_security_headers(headers, request_id: str | None = None, no_store: bool = False):
    result = list(headers)
    present = {key.lower() for key, _ in result}
    additions = dict(SECURITY_HEADERS)
    if request_id and b"x-request-id" not in present:
        additions[b"x-request-id"] = request_id.encode("ascii")
    if no_store and b"cache-control" not in present:
        additions[b"cache-control"] = b"no-store"
    result.extend((key, value) for key, value in additions.items() if key not in present)
    return result

from urllib.parse import urlsplit


def _is_loopback_hostname(hostname: str | None) -> bool:
    return hostname in {"localhost", "127.0.0.1", "::1"}


def validate_host(value: str | None, configured_port: int) -> bool:
    if not value or any(ord(char) < 32 for char in value) or "," in value or "@" in value:
        return False
    candidate = urlsplit(f"//{value}")
    try:
        port = candidate.port
    except ValueError:
        return False
    if candidate.username or candidate.password or candidate.path or candidate.query or candidate.fragment:
        return False
    return _is_loopback_hostname(candidate.hostname) and (port is None or port == configured_port)


def _validate_url(value: str | None, configured_port: int, *, require_empty_path: bool) -> bool:
    if not value or any(ord(char) < 32 for char in value):
        return False
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if (require_empty_path and parsed.path) or parsed.query or parsed.fragment or not _is_loopback_hostname(parsed.hostname):
        return False
    return port == configured_port


def validate_origin(value: str | None, configured_port: int) -> bool:
    return _validate_url(value, configured_port, require_empty_path=True)


def validate_referer(value: str | None, configured_port: int) -> bool:
    return _validate_url(value, configured_port, require_empty_path=False)

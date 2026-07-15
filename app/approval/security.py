import hashlib
import hmac
import json
import secrets
from urllib.parse import urlparse


def generate_approval_nonce(byte_length: int) -> str:
    return secrets.token_urlsafe(byte_length)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_arguments(arguments: dict) -> str:
    return json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def compare_hash(candidate: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_text(candidate), expected_hash)


def is_local_origin(origin_or_referer: str | None, port: int) -> bool:
    if not origin_or_referer:
        return True
    parsed = urlparse(origin_or_referer)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        return False
    return parsed.port in {None, port}

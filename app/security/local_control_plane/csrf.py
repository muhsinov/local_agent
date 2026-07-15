import hashlib
import hmac


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)

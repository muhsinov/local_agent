import time


def remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def safe_truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", True
    suffix = "\n...(truncated)"
    if limit <= len(suffix):
        return suffix[:limit], True
    head = limit - len(suffix)
    return f"{text[:head]}{suffix}", True

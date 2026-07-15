import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone


SAFE_FIELDS = {"timestamp", "level", "event", "request_id", "method", "route_template", "status_code", "duration_ms", "error_code", "rate_limit_group", "browser", "authenticated", "limit", "retry_after_seconds", "draining"}


class SafeJsonlLogger:
    def __init__(self, directory: Path, max_bytes: int, backup_count: int, enabled: bool = True) -> None:
        self.enabled = enabled
        self._logger = logging.getLogger(f"local-agent-runtime-{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if enabled:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(directory / "local-agent.jsonl", maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(message)s"))
                self._logger.addHandler(handler)
            except OSError:
                self.enabled = False

    def log(self, *, event: str, **fields) -> None:
        if not self.enabled:
            return
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": "INFO", "event": event}
        payload.update({key: value for key, value in fields.items() if key in SAFE_FIELDS and isinstance(value, (str, int, bool, float))})
        try:
            self._logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        except Exception:
            pass

    def close(self) -> None:
        for handler in list(self._logger.handlers):
            try:
                handler.close()
                self._logger.removeHandler(handler)
            except Exception:
                pass

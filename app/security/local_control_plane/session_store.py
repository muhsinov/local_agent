import secrets
import threading
from datetime import datetime, timedelta, timezone

from app.security.local_control_plane.csrf import hash_secret, secrets_equal
from app.security.local_control_plane.models import LocalSession


class LocalSessionStore:
    def __init__(self, *, ttl_seconds: int, max_active: int, session_bytes: int, csrf_bytes: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_active = max_active
        self._session_bytes = session_bytes
        self._csrf_bytes = csrf_bytes
        self._sessions: dict[str, LocalSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _cleanup_locked(self, now: datetime) -> None:
        self._sessions = {key: value for key, value in self._sessions.items() if value.expires_at > now}

    def create(self) -> tuple[str, str, LocalSession] | None:
        now = self._now()
        with self._lock:
            self._cleanup_locked(now)
            if len(self._sessions) >= self._max_active:
                return None
            raw_session = secrets.token_urlsafe(self._session_bytes)
            raw_csrf = secrets.token_urlsafe(self._csrf_bytes)
            record = LocalSession(
                session_hash=hash_secret(raw_session),
                csrf_hash=hash_secret(raw_csrf),
                created_at=now,
                expires_at=now + timedelta(seconds=self._ttl_seconds),
            )
            self._sessions[record.session_hash] = record
            return raw_session, raw_csrf, record

    def validate(self, raw_session: str | None, raw_csrf: str | None) -> bool:
        if not raw_session or not raw_csrf:
            return False
        now = self._now()
        session_hash = hash_secret(raw_session)
        csrf_hash = hash_secret(raw_csrf)
        with self._lock:
            self._cleanup_locked(now)
            record = self._sessions.get(session_hash)
            return bool(record and secrets_equal(record.session_hash, session_hash) and secrets_equal(record.csrf_hash, csrf_hash))

    def has_session(self, raw_session: str | None) -> bool:
        if not raw_session:
            return False
        now = self._now()
        session_hash = hash_secret(raw_session)
        with self._lock:
            self._cleanup_locked(now)
            record = self._sessions.get(session_hash)
            return bool(record and secrets_equal(record.session_hash, session_hash))

import secrets
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.security.local_control_plane.csrf import hash_secret, secrets_equal
from app.security.local_control_plane.models import LocalSession


class LocalSessionStore:
    def __init__(self, *, ttl_seconds: int, max_active: int, session_bytes: int, csrf_bytes: int, max_csrf_tokens: int = 16) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_active = max_active
        self._session_bytes = session_bytes
        self._csrf_bytes = csrf_bytes
        self._max_csrf_tokens = max_csrf_tokens
        self._sessions: dict[str, LocalSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _cleanup_locked(self, now: datetime) -> None:
        self._sessions = {key: value for key, value in self._sessions.items() if value.expires_at > now}

    def bootstrap(self, existing_raw_session: str | None) -> tuple[str, str, LocalSession] | None:
        now = self._now()
        with self._lock:
            self._cleanup_locked(now)
            existing_hash = hash_secret(existing_raw_session) if existing_raw_session else None
            existing = self._sessions.get(existing_hash) if existing_hash else None
            if existing is not None and existing.expires_at > now:
                raw_csrf = secrets.token_urlsafe(self._csrf_bytes)
                csrf_hashes = (*existing.csrf_hashes, hash_secret(raw_csrf))[-self._max_csrf_tokens :]
                record = replace(existing, csrf_hashes=csrf_hashes)
                self._sessions[record.session_hash] = record
                return existing_raw_session, raw_csrf, record
            if len(self._sessions) >= self._max_active:
                return None
            raw_session = secrets.token_urlsafe(self._session_bytes)
            raw_csrf = secrets.token_urlsafe(self._csrf_bytes)
            record = LocalSession(
                session_hash=hash_secret(raw_session),
                csrf_hashes=(hash_secret(raw_csrf),),
                created_at=now,
                expires_at=now + timedelta(seconds=self._ttl_seconds),
            )
            self._sessions[record.session_hash] = record
            return raw_session, raw_csrf, record

    def create(self) -> tuple[str, str, LocalSession] | None:
        return self.bootstrap(None)

    def validate(self, raw_session: str | None, raw_csrf: str | None) -> bool:
        if not raw_session or not raw_csrf:
            return False
        now = self._now()
        session_hash = hash_secret(raw_session)
        csrf_hash = hash_secret(raw_csrf)
        with self._lock:
            self._cleanup_locked(now)
            record = self._sessions.get(session_hash)
            if record is None:
                return False
            session_match = secrets_equal(record.session_hash, session_hash)
            csrf_match = False
            for candidate in record.csrf_hashes:
                csrf_match = secrets_equal(candidate, csrf_hash) | csrf_match
            return bool(session_match and csrf_match)

    def has_session(self, raw_session: str | None) -> bool:
        if not raw_session:
            return False
        now = self._now()
        session_hash = hash_secret(raw_session)
        with self._lock:
            self._cleanup_locked(now)
            record = self._sessions.get(session_hash)
            return bool(record and secrets_equal(record.session_hash, session_hash))

    def session_identity(self, raw_session: str | None) -> str | None:
        if not raw_session:
            return None
        now = self._now()
        session_hash = hash_secret(raw_session)
        with self._lock:
            self._cleanup_locked(now)
            record = self._sessions.get(session_hash)
            if record is None or not secrets_equal(record.session_hash, session_hash):
                return None
            return record.session_hash

    def active_count(self) -> int:
        with self._lock:
            self._cleanup_locked(self._now())
            return len(self._sessions)

    def csrf_token_count(self, raw_session: str | None) -> int:
        if not raw_session:
            return 0
        with self._lock:
            self._cleanup_locked(self._now())
            record = self._sessions.get(hash_secret(raw_session))
            return len(record.csrf_hashes) if record else 0

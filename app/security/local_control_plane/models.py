from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LocalSession:
    session_hash: str
    csrf_hash: str
    created_at: datetime
    expires_at: datetime

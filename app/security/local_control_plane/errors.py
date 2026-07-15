from dataclasses import dataclass


@dataclass(frozen=True)
class LocalSecurityError(Exception):
    status_code: int
    code: str
    message: str

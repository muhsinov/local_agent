from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeAdmissionError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] | None = None

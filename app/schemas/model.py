from pydantic import BaseModel


class ModelStatusResponse(BaseModel):
    """Model availability payload returned by the API."""

    ollama: str
    model: str
    installed: bool

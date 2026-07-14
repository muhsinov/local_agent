class OllamaError(Exception):
    """Base exception for Ollama client failures."""


class OllamaUnavailableError(OllamaError):
    """Raised when the Ollama server cannot be reached."""


class OllamaTimeoutError(OllamaError):
    """Raised when the Ollama server times out."""


class OllamaModelNotFoundError(OllamaError):
    """Raised when the configured Ollama model is unavailable."""


class OllamaInvalidResponseError(OllamaError):
    """Raised when Ollama returns an unexpected payload."""

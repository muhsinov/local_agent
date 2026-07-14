from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.errors import ApiError
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.schemas.model import ModelStatusResponse


router = APIRouter(prefix="/model", tags=["model"])


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status(request: Request) -> ModelStatusResponse:
    """Report Ollama reachability and model availability."""

    settings = request.app.state.settings
    client = request.app.state.ollama_client

    try:
        installed = await client.is_model_installed(settings.ollama_model)
    except OllamaUnavailableError:
        return JSONResponse(
            status_code=503,
            content=ModelStatusResponse(
                ollama="unreachable",
                model=settings.ollama_model,
                installed=False,
            ).model_dump(),
        )
    except OllamaTimeoutError:
        raise ApiError(
            status_code=504,
            code="OLLAMA_TIMEOUT",
            message="Ollama javobi kutish vaqtidan oshdi.",
        ) from None
    except OllamaInvalidResponseError:
        raise ApiError(
            status_code=502,
            code="OLLAMA_INVALID_RESPONSE",
            message="Ollama noto'g'ri javob qaytardi.",
        ) from None
    except OllamaModelNotFoundError:
        raise ApiError(
            status_code=502,
            code="OLLAMA_INVALID_RESPONSE",
            message="Ollama noto'g'ri javob qaytardi.",
        ) from None

    return ModelStatusResponse(
        ollama="ok",
        model=settings.ollama_model,
        installed=installed,
    )

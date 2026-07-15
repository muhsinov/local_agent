import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.errors import AgentError
from app.agent.models import ToolCall


class _FinalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["final"]
    answer: str = Field(min_length=1)


class _ToolCallEnvelopeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]


class _ToolCallEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"]
    calls: list[_ToolCallEnvelopeItem]


def _reject_constant(value: str) -> None:
    raise AgentError(422, "AGENT_RESPONSE_INVALID", f"Noto'g'ri JSON constant: {value}")


def _unwrap_markdown_json(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1] == "```":
            return "\n".join(lines[1:-1]).strip()
    return raw


def _max_depth(value: Any, depth: int = 1) -> int:
    if isinstance(value, dict):
        if not value:
            return depth
        return max(_max_depth(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return depth
        return max(_max_depth(item, depth + 1) for item in value)
    return depth


def parse_agent_response(raw: str, *, max_calls: int, max_depth: int = 6) -> tuple[str, str | list[ToolCall]]:
    text = _unwrap_markdown_json(raw)
    decoder = json.JSONDecoder(parse_constant=_reject_constant)
    try:
        payload, end = decoder.raw_decode(text)
    except AgentError:
        raise
    except json.JSONDecodeError as exc:
        raise AgentError(422, "AGENT_RESPONSE_INVALID", "Model tool javobi JSON formatda emas.") from exc

    if text[end:].strip():
        raise AgentError(422, "AGENT_RESPONSE_INVALID", "JSONdan keyin ortiqcha matn bor.")
    if not isinstance(payload, dict):
        raise AgentError(422, "AGENT_RESPONSE_INVALID", "Top-level JSON object bo'lishi kerak.")
    if _max_depth(payload) > max_depth:
        raise AgentError(422, "AGENT_RESPONSE_INVALID", "JSON depth limiti oshib ketdi.")

    response_type = payload.get("type")
    try:
        if response_type == "final":
            final = _FinalEnvelope.model_validate(payload)
            return ("final", final.answer.strip())
        if response_type == "tool_call":
            envelope = _ToolCallEnvelope.model_validate(payload)
        else:
            raise AgentError(422, "AGENT_RESPONSE_INVALID", "Model javobida noto'g'ri type bor.")
    except ValidationError as exc:
        raise AgentError(422, "AGENT_RESPONSE_INVALID", "Model tool javobi noto'g'ri.") from exc

    if len(envelope.calls) > max_calls:
        raise AgentError(422, "AGENT_TOOL_CALL_LIMIT", "Bir javobdagi tool call limiti oshdi.")
    seen_ids: set[str] = set()
    calls: list[ToolCall] = []
    for item in envelope.calls:
        if item.id in seen_ids:
            raise AgentError(422, "AGENT_RESPONSE_INVALID", "Duplicate tool call id ruxsat etilmagan.")
        seen_ids.add(item.id)
        calls.append(ToolCall(id=item.id, name=item.name, arguments=item.arguments))
    return ("tool_call", calls)


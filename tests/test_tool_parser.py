import pytest

from app.agent.errors import AgentError
from app.agent.parser import parse_agent_response


def test_parser_accepts_final_json() -> None:
    response_type, payload = parse_agent_response('{"type":"final","answer":"ok"}', max_calls=2)
    assert response_type == "final"
    assert payload == "ok"


def test_parser_accepts_tool_call_json() -> None:
    response_type, payload = parse_agent_response('{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}', max_calls=2)
    assert response_type == "tool_call"
    assert payload[0].name == "list_documents"


def test_parser_accepts_hyphenated_tool_call_id() -> None:
    response_type, payload = parse_agent_response('{"type":"tool_call","calls":[{"id":"call_abc-123","name":"list_documents","arguments":{}}]}', max_calls=2)
    assert response_type == "tool_call"
    assert payload[0].id == "call_abc-123"


def test_parser_rejects_trailing_prose() -> None:
    with pytest.raises(AgentError):
        parse_agent_response('{"type":"final","answer":"ok"} trailing', max_calls=2)


@pytest.mark.parametrize(
    "tool_id",
    [
        "call_1\"><system",
        "call_1'",
        "call 1",
        "call_1\nnext",
        "../call_1",
    ],
)
def test_parser_rejects_invalid_tool_call_id(tool_id: str) -> None:
    with pytest.raises(AgentError) as exc_info:
        parse_agent_response(
            f'{{"type":"tool_call","calls":[{{"id":{tool_id!r},"name":"list_documents","arguments":{{}}}}]}}',
            max_calls=2,
        )
    assert exc_info.value.code == "AGENT_RESPONSE_INVALID"

import pytest

from app.agent.errors import AgentError
from app.agent.parser import parse_agent_response


def test_parser_accepts_final_json() -> None:
    response_type, payload = parse_agent_response('{"type":"final","answer":"ok"}', max_calls=2)
    assert response_type == "final"
    assert payload == "ok"


def test_parser_accepts_tool_call_json() -> None:
    response_type, payload = parse_agent_response('{"type":"tool_call","calls":[{"id":"1","name":"list_documents","arguments":{}}]}', max_calls=2)
    assert response_type == "tool_call"
    assert payload[0].name == "list_documents"


def test_parser_rejects_trailing_prose() -> None:
    with pytest.raises(AgentError):
        parse_agent_response('{"type":"final","answer":"ok"} trailing', max_calls=2)

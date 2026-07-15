import json

from app.tools.system_info_tools import GetLocalSystemInfoTool
from tests.conftest import build_settings


def test_system_info_tool_returns_safe_fields_only(tmp_path) -> None:
    settings = build_settings(tmp_path)
    payload = json.loads(GetLocalSystemInfoTool(1).execute(type("Args", (), {})(), settings))
    assert "python_version" in payload
    assert "hostname" not in payload
    assert "username" not in payload

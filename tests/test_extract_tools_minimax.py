from python.helpers import extract_tools


def test_json_parse_dirty_still_parses_json():
    data = extract_tools.json_parse_dirty(
        '{"tool_name":"scheduler:show_task","tool_args":{"uuid":"abc123"}}'
    )
    assert data == {
        "tool_name": "scheduler:show_task",
        "tool_args": {"uuid": "abc123"},
    }


def test_json_parse_dirty_parses_minimax_xml_tool_call():
    text = """
<minimax:tool_call>
<invoke name="scheduler:show_task">
<parameter name="uuid">gpZaClf5</parameter>
</invoke>
</minimax:tool_call>
"""
    data = extract_tools.json_parse_dirty(text)
    assert data == {
        "tool_name": "scheduler:show_task",
        "tool_args": {"uuid": "gpZaClf5"},
    }


def test_json_parse_dirty_parses_minimax_xml_with_malformed_trailing_quote():
    text = """
<minimax:tool_call>
<invoke name="code_execution_tool">
<parameter name="runtime">python"</parameter>
<parameter name="session">0</parameter>
<parameter name="reset">false</parameter>
</invoke>
</minimax:tool_call>
"""
    data = extract_tools.json_parse_dirty(text)
    assert data == {
        "tool_name": "code_execution_tool",
        "tool_args": {"runtime": "python", "session": 0, "reset": False},
    }


def test_json_parse_dirty_uses_first_invoke_when_multiple_present():
    text = """
<minimax:tool_call>
<invoke name="scheduler:show_task">
<parameter name="uuid">first</parameter>
</invoke>
<invoke name="scheduler:list_tasks">
</invoke>
</minimax:tool_call>
"""
    data = extract_tools.json_parse_dirty(text)
    assert data == {
        "tool_name": "scheduler:show_task",
        "tool_args": {"uuid": "first"},
    }

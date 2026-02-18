from python.integrations.slack_socket_listener import SlackSocketListener


def test_to_slack_mrkdwn_normalizes_common_markdown():
    listener = SlackSocketListener()
    src = (
        "# Title\n\n"
        "**bold** and __also bold__ and ~~strike~~\n"
        "- [x] done\n"
        "- [ ] todo\n"
        "- item\n"
        "[OpenAI](https://openai.com)\n"
    )
    out = listener._to_slack_mrkdwn(src)
    assert "*Title*" in out
    assert "*bold* and *also bold* and ~strike~" in out
    assert "• [x] done" in out
    assert "• [ ] todo" in out
    assert "• item" in out
    assert "<https://openai.com|OpenAI>" in out


def test_parse_event_dm_accepts_human_client_message():
    listener = SlackSocketListener()
    event = {
        "type": "message",
        "channel_type": "im",
        "channel": "D123",
        "user": "U123",
        "text": "hello",
        "ts": "1700000000.100",
        "client_msg_id": "abc",
    }
    parsed = listener._parse_event(event)
    assert parsed is not None
    assert parsed["context_key"] == "dm:U123"
    assert parsed["channel"] == "D123"
    assert parsed["agent_message"] == "hello"


def test_parse_event_channel_rejects_missing_client_msg_id():
    listener = SlackSocketListener()
    event = {
        "type": "message",
        "channel_type": "channel",
        "channel": "C123",
        "user": "U123",
        "text": "hello",
        "thread_ts": "1700000000.100",
        # Missing client_msg_id should be treated as bot/system echo.
    }
    parsed = listener._parse_event(event)
    assert parsed is None

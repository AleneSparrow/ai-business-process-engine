from src.domain.sms_commands import classify_inbound_sms


def test_stop_keywords_are_whole_messages_only() -> None:
    assert classify_inbound_sms("stop") == "stop"
    assert classify_inbound_sms(" STOPALL ") == "stop"
    assert classify_inbound_sms("please stop") is None


def test_start_does_not_include_yes() -> None:
    assert classify_inbound_sms("START") == "start"
    assert classify_inbound_sms("yes") is None
    assert classify_inbound_sms("UNSTOP") == "start"


def test_help_is_exact() -> None:
    assert classify_inbound_sms("HELP") == "help"
    assert classify_inbound_sms("I need help") is None

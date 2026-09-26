import json

import pytest

from mimikr.importers import (
    ExportError,
    clean_name,
    detect_format,
    read_discord,
    read_export,
    read_telegram,
    read_whatsapp,
    write_transcript,
)
from mimikr.transcript import Message, parse_transcript


def test_written_messages_read_back_the_same():
    messages = [Message("Ana", "hi", "2024-01-01 10:00"), Message("Bo", "line one\nline two"), Message("Ana", "bye")]
    assert parse_transcript(write_transcript(messages)) == messages


def test_a_name_loses_colons_brackets_and_new_lines():
    assert clean_name("Dr. Who: The [Doctor]\n") == "Dr. Who The Doctor"
    assert clean_name(" : ") == "Unknown"


def test_a_message_with_no_text_is_not_written():
    assert write_transcript([Message("Ana", "  \n "), Message("Bo", "ok")]) == "Bo: ok\n"


def test_a_line_that_looks_like_a_comment_stays_text():
    text = write_transcript([Message("Ana", "first\n# not a heading")])
    assert parse_transcript(text)[0].text == "first\n# not a heading"


ANDROID = """12/31/23, 9:41\u202fPM - Messages and calls are end-to-end encrypted.
12/31/23, 9:41\u202fPM - June: are you up
12/31/23, 9:42\u202fPM - Sam: unfortunately
still at work
12/31/23, 9:42\u202fPM - Sam: <Media omitted>
12/31/23, 9:43\u202fPM - June changed the group name to "Late night"
1/1/24, 12:00\u202fAM - Sam: happy new year <This message was edited>
"""

IOS = """[31/12/2023, 21:41:05] June: are you up
[31/12/2023, 21:42:10] Sam: unfortunately
\u200e[31/12/2023, 21:42:30] Sam: \u200eimage omitted
[31/12/2023, 21:43:00] Sam: time: 10pm
"""


def test_reads_an_android_export():
    messages = read_whatsapp(ANDROID)
    assert [(m.speaker, m.text) for m in messages] == [
        ("June", "are you up"), ("Sam", "unfortunately\nstill at work"), ("Sam", "happy new year"),
    ]
    assert messages[0].time == "12/31/23 9:41 PM"


def test_reads_an_ios_export():
    messages = read_whatsapp(IOS)
    assert [(m.speaker, m.text) for m in messages] == [
        ("June", "are you up"), ("Sam", "unfortunately"), ("Sam", "time: 10pm"),
    ]
    assert messages[0].time == "31/12/2023 21:41:05"


def test_a_line_after_a_notice_is_not_added_to_a_message():
    text = "1/1/24, 10:00 AM - Sam: hi\n1/1/24, 10:01 AM - June left\nsecond line of the notice\n"
    assert [m.text for m in read_whatsapp(text)] == ["hi"]


def test_refuses_a_file_that_is_not_a_whatsapp_export():
    with pytest.raises(ExportError, match="no WhatsApp message"):
        read_whatsapp("this is not a chat\nat all")


def test_the_export_reads_back_through_the_transcript_reader():
    from mimikr.transcript import parse_transcript
    assert [(m.speaker, m.text) for m in parse_transcript(write_transcript(read_whatsapp(IOS)))] == [
        ("June", "are you up"), ("Sam", "unfortunately"), ("Sam", "time: 10pm"),
    ]


TELEGRAM = {
    "name": "June",
    "type": "personal_chat",
    "messages": [
        {"id": 1, "type": "service", "date": "2024-01-01T10:00:00", "action": "phone_call"},
        {"id": 2, "type": "message", "date": "2024-01-01T10:01:00", "from": "June", "text": "noodles?"},
        {"id": 3, "type": "message", "date": "2024-01-01T10:02:00", "from": "Sam",
         "text": ["say ", {"type": "bold", "text": "less"}, "\nsee u at 1"]},
        {"id": 4, "type": "message", "date": "2024-01-01T10:03:00", "from": "Sam", "text": "",
         "photo": "photos/photo_1.jpg"},
        {"id": 5, "type": "message", "date": "2024-01-01T10:04:00", "from": None, "text": "hello"},
    ],
}


def test_reads_a_telegram_export():
    messages = read_telegram(json.dumps(TELEGRAM))
    assert [(m.speaker, m.text) for m in messages] == [
        ("June", "noodles?"), ("Sam", "say less\nsee u at 1"), ("Deleted Account", "hello"),
    ]
    assert messages[0].time == "2024-01-01 10:01:00"


def test_refuses_the_export_of_all_telegram_chats():
    with pytest.raises(ExportError, match="Export one chat"):
        read_telegram(json.dumps({"chats": {"list": []}}))


def test_refuses_a_file_that_is_not_json():
    with pytest.raises(ExportError, match="not the JSON export of Telegram Desktop"):
        read_telegram("12/31/23, 9:41 PM - June: hi")


DISCORD = {
    "guild": {"name": "Friends"},
    "channel": {"name": "general"},
    "messages": [
        {"type": "Default", "timestamp": "2024-01-01T10:00:00.123+00:00", "content": "noodles?",
         "author": {"name": "june_92", "nickname": "June"}},
        {"type": "Reply", "timestamp": "2024-01-01T10:01:00+00:00", "content": "say less",
         "author": {"name": "sam.cooks", "nickname": None}},
        {"type": "ChannelPinnedMessage", "timestamp": "2024-01-01T10:02:00+00:00", "content": "pinned",
         "author": {"name": "sam.cooks"}},
        {"type": "Default", "timestamp": "2024-01-01T10:03:00+00:00", "content": "",
         "author": {"name": "sam.cooks"}, "attachments": [{"fileName": "cat.png"}]},
    ],
}


def test_reads_a_discord_export():
    messages = read_discord(json.dumps(DISCORD))
    assert [(m.speaker, m.text) for m in messages] == [("June", "noodles?"), ("sam.cooks", "say less")]
    assert messages[0].time == "2024-01-01 10:00:00"


def test_refuses_json_that_is_not_a_chat_export():
    with pytest.raises(ExportError, match="one chat in DiscordChatExporter"):
        read_discord(json.dumps({"hello": "world"}))


def test_detect_format_knows_each_export():
    assert detect_format(ANDROID) == "whatsapp"
    assert detect_format(IOS) == "whatsapp"
    assert detect_format(json.dumps(TELEGRAM)) == "telegram"
    assert detect_format(json.dumps(DISCORD)) == "discord"
    assert detect_format(json.dumps({"chats": {"list": []}})) == "telegram"


def test_detect_format_does_not_guess():
    assert detect_format("hello\nworld") is None
    assert detect_format(json.dumps({"messages": [1, 2]})) is None
    assert detect_format("Sam: this is already a chat.md file") is None


def test_read_export_reads_with_the_detected_reader():
    kind, messages = read_export(json.dumps(DISCORD))
    assert kind == "discord" and messages[0].text == "noodles?"
    with pytest.raises(ExportError, match="does not know this file"):
        read_export("just some notes")

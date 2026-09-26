import pytest

from mimikr.importers import ExportError, clean_name, read_whatsapp, write_transcript
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

from mimikr.importers import clean_name, write_transcript
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

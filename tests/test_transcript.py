import pytest

from mimikr.transcript import TranscriptError, parse_transcript, speakers, turn_starts


def test_reads_one_message_on_each_line():
    messages = parse_transcript("Ana: hi\nBo: hello there\n")
    assert [(m.speaker, m.text) for m in messages] == [("Ana", "hi"), ("Bo", "hello there")]


def test_reads_a_time_in_brackets():
    [message] = parse_transcript("[2024-05-01 21:14] Ana: hi")
    assert (message.time, message.speaker, message.text) == ("2024-05-01 21:14", "Ana", "hi")


def test_an_indented_line_continues_the_previous_message():
    [message] = parse_transcript("Ana: first line\n  second line\n\tthird line")
    assert message.text == "first line\nsecond line\nthird line"


def test_a_colon_inside_the_text_stays_in_the_text():
    [message] = parse_transcript("Ana: note: see https://example.com")
    assert (message.speaker, message.text) == ("Ana", "note: see https://example.com")


def test_ignores_comments_and_empty_lines():
    messages = parse_transcript("# exported from my phone\n\nAna: hi\n\n")
    assert len(messages) == 1


def test_accepts_a_name_with_spaces_and_extra_spaces_before_the_colon():
    [message] = parse_transcript("Ana Maria   :  hi")
    assert (message.speaker, message.text) == ("Ana Maria", "hi")


def test_drops_a_message_with_no_text():
    assert parse_transcript("Ana:\nBo: hi") == parse_transcript("Bo: hi")


def test_refuses_a_line_with_no_speaker():
    with pytest.raises(TranscriptError, match="line 2"):
        parse_transcript("Ana: hi\nthis line has no speaker")


def test_refuses_a_continuation_line_at_the_start():
    with pytest.raises(TranscriptError, match="line 1"):
        parse_transcript("  orphan line")


def test_speakers_keeps_the_order_of_the_first_message():
    assert speakers(parse_transcript("Bo: a\nAna: b\nBo: c")) == ["Bo", "Ana"]


def test_a_turn_is_a_run_of_messages_from_the_speaker():
    messages = parse_transcript("Ana: a\nAna: b\nBo: c\nAna: d")
    assert turn_starts(messages, "Ana") == [0, 3]

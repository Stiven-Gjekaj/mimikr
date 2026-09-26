import pytest

from mimikr.evaluate import EvaluationError, split_cases, turn_starts
from mimikr.transcript import Message


def chat(*lines: str) -> list[Message]:
    """Build messages from 'Speaker: text' strings."""
    return [Message(*line.split(": ", 1)) for line in lines]


def test_a_turn_is_a_run_of_messages_from_the_speaker():
    messages = chat("Ana: a", "Ana: b", "Bo: c", "Ana: d")
    assert turn_starts(messages, "Ana") == [0, 3]


def test_the_test_cases_are_the_last_turns_and_the_training_ends_before_them():
    messages = chat(
        "Bo: 1", "Ana: 2", "Bo: 3", "Ana: 4", "Bo: 5", "Ana: 6", "Ana: 7", "Bo: 8", "Ana: 9", "Bo: 10"
    )
    training, cases = split_cases(messages, "Ana", test_fraction=0.5)
    assert [m.text for m in training] == ["1", "2", "3", "4", "5"]
    assert [[m.text for m in case.reply] for case in cases] == [["6", "7"], ["9"]]
    assert [m.text for m in cases[1].context] == ["1", "2", "3", "4", "5", "6", "7", "8"]


def test_no_real_test_reply_is_in_the_training_messages():
    messages = chat(*[f"{'Ana' if n % 2 else 'Bo'}: message {n}" for n in range(40)])
    training, cases = split_cases(messages, "Ana")
    replies = {m.text for case in cases for m in case.reply}
    assert replies and not replies & {m.text for m in training}


def test_the_context_has_a_limit():
    messages = chat(*[f"Bo: {n}" for n in range(50)], "Ana: a", "Bo: b", "Ana: c")
    _, [case] = split_cases(messages, "Ana", context_size=5)
    assert [m.text for m in case.context] == ["47", "48", "49", "a", "b"]


def test_the_training_always_holds_a_turn_of_the_speaker():
    training, cases = split_cases(chat("Ana: a", "Bo: b", "Ana: c"), "Ana", test_fraction=0.9)
    assert [m.text for m in training] == ["a", "b"]
    assert len(cases) == 1


def test_refuses_a_transcript_with_one_turn():
    with pytest.raises(EvaluationError, match="two or more turns"):
        split_cases(chat("Bo: hi", "Ana: a", "Ana: b"), "Ana")

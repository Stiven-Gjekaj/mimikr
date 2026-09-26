import zlib

import pytest

from mimikr.evaluate import (
    EvaluationError,
    feature_difference,
    score_meaning,
    score_style,
    split_cases,
)
from mimikr.transcript import Message


def chat(*lines: str) -> list[Message]:
    """Build messages from 'Speaker: text' strings."""
    return [Message(*line.split(": ", 1)) for line in lines]


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


CASUAL = [["lol", "who is asking"], ["nah"], ["ok 😂", "fine", "see u"]]
FORMAL = [["Good evening. I hope that you are well, and that the day went as planned."],
          ["Thank you for the message. I will answer it tomorrow morning!"],
          ["Yes. That is correct, and I agree with the plan."]]


def test_the_same_replies_have_the_best_style_score():
    assert score_style(CASUAL, CASUAL).score == 1.0


def test_replies_of_a_different_person_have_a_worse_style_score():
    assert score_style(CASUAL, FORMAL).score < 0.6


def test_the_score_holds_both_values_of_each_feature():
    features = score_style(CASUAL, FORMAL).features
    assert features["lowercase_start"] == (1.0, 0.0)
    assert features["messages_per_turn"] == (2.0, 1.0)


def test_a_count_difference_is_relative_and_a_rate_difference_is_absolute():
    assert feature_difference("median_words", 4, 8) == 0.5
    assert feature_difference("median_words", 0, 0) == 0.0
    assert feature_difference("emoji_rate", 0.1, 0.4) == pytest.approx(0.3)


class WordEmbedder:
    """Embed a text as the counts of its words, in 64 buckets. Keep each call."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            vector = [0.0] * 64
            for word in text.lower().split():
                vector[zlib.crc32(word.encode()) % 64] += 1
            vectors.append(vector)
        return vectors


REAL = [["the kitchen was chaos"], ["breakfast is a myth"], ["lunch tho", "lunch i can do"]]


def test_the_same_replies_have_the_best_meaning_score():
    assert score_meaning(REAL, REAL, WordEmbedder()).score == pytest.approx(1.0)


def test_unrelated_replies_have_a_worse_meaning_score():
    other = [["my cat sleeps"], ["taxes are due"], ["see you monday"]]
    assert score_meaning(REAL, other, WordEmbedder()).score < 0.5


def test_the_baseline_compares_each_real_reply_with_a_different_real_reply():
    result = score_meaning(REAL, REAL, WordEmbedder())
    assert result.baseline is not None and result.baseline < 0.5
    assert score_meaning(REAL[:1], REAL[:1], WordEmbedder()).baseline is None


def test_an_empty_reply_scores_zero_and_is_not_embedded():
    embedder = WordEmbedder()
    result = score_meaning(REAL, [REAL[0], [], REAL[2]], embedder)
    assert result.score == pytest.approx(2 / 3)
    assert "" not in embedder.calls[0]
    assert len(embedder.calls) == 1

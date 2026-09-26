from mimikr.style import build_profile
from mimikr.transcript import Message


def conversation(*lines: tuple[str, str]) -> list[Message]:
    return [Message(speaker, text) for speaker, text in lines]


def test_an_unknown_speaker_gives_an_empty_profile():
    profile = build_profile(conversation(("Ana", "hi")), "Bo")
    assert profile.message_count == 0
    assert profile.describe() == []


def test_counts_only_the_messages_of_the_speaker():
    profile = build_profile(conversation(("Ana", "one two three"), ("Bo", "a b c d e f g")), "Ana")
    assert profile.message_count == 1
    assert profile.median_words == 3


def test_finds_lowercase_starts_and_no_periods():
    profile = build_profile(conversation(("Ana", "yeah sure"), ("Ana", "ok cool"), ("Ana", "lol")), "Ana")
    assert profile.lowercase_start == 1.0
    assert profile.ends_with_period == 0.0
    described = profile.describe()
    assert "Start most messages with a lowercase letter." in described
    assert "Do not put a period at the end of a message." in described


def test_finds_emoji_and_the_favorites():
    profile = build_profile(
        conversation(("Ana", "nice 😂"), ("Ana", "wow 😂😂"), ("Ana", "ok 🔥"), ("Ana", "fine")), "Ana"
    )
    assert profile.emoji_rate == 0.75
    assert profile.top_emoji[0] == "😂"


def test_finds_short_replies_that_repeat():
    profile = build_profile(
        conversation(("Ana", "LOL"), ("Bo", "x"), ("Ana", "lol"), ("Bo", "y"), ("Ana", "maybe once")), "Ana"
    )
    assert profile.stock_replies == ["lol"]


def test_counts_messages_in_a_row_as_one_turn():
    profile = build_profile(
        conversation(("Ana", "a"), ("Ana", "b"), ("Ana", "c"), ("Bo", "x"), ("Ana", "d")), "Ana"
    )
    assert profile.messages_per_turn == 2.0
    assert any("short messages in a row" in line for line in profile.describe())


def test_links_mentions_and_custom_emoji_are_not_stock_replies():
    lines = [("Ana", text) for text in ["https://tenor.com/view/cat-123"] * 3 + ["@june"] * 3 + [":pepe:"] * 3
             + ["<:pepe:123456>"] * 3 + ["bet"] * 2]
    profile = build_profile(conversation(*lines), "Ana")
    assert profile.stock_replies == ["bet"]

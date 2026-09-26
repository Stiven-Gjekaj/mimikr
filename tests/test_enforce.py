from mimikr.style import StyleProfile, drop_repeats, enforce


def casual(**changes) -> StyleProfile:
    values = dict(message_count=20, lowercase_start=1.0, ends_with_period=0.0, emoji_rate=0.0)
    values.update(changes)
    return StyleProfile(**values)


def test_a_casual_person_loses_the_capital_the_period_and_the_emoji():
    assert enforce(casual(), ["Sure thing.", "See you 😂"]) == ["sure thing", "see you"]


def test_i_and_words_of_capitals_keep_their_capitals():
    assert enforce(casual(), ["I think so.", "I'm late", "NASA called."]) == ["I think so", "I'm late", "NASA called"]


def test_three_dots_stay():
    assert enforce(casual(), ["well..."]) == ["well..."]


def test_a_person_who_uses_capitals_periods_and_emoji_keeps_them():
    formal = casual(lowercase_start=0.1, ends_with_period=0.8, emoji_rate=0.3)
    assert enforce(formal, ["Good evening. 😊"]) == ["Good evening. 😊"]


def test_a_few_messages_do_not_show_a_habit():
    assert enforce(casual(message_count=3), ["Sure thing."]) == ["Sure thing."]


def test_a_message_of_emoji_only_goes_away():
    assert enforce(casual(), ["😂😂", "ok"]) == ["ok"]


def test_a_repeat_of_a_recent_message_goes_away_with_no_case_or_space():
    assert drop_repeats(["Bet", "see u at 1"], recent=["bet ", "ok"]) == ["see u at 1"]


def test_a_repeat_inside_one_reply_goes_away():
    assert drop_repeats(["lol", "LOL", "ok"], recent=[]) == ["lol", "ok"]

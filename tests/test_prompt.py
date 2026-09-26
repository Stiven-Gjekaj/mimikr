from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.prompt import EARLIER, build_messages, recent_messages, select_examples, split_reply
from mimikr.rooms import USER, Room, RoomMessage
from mimikr.style import StyleProfile, build_profile
from mimikr.transcript import Message

NAMES = {USER: "You", "ana": "Ana", "bo": "Bo"}


def ana(transcript: list[Message] | None = None) -> Identity:
    transcript = transcript or []
    return Identity(
        id="ana",
        display_name="Ana",
        personality="Ana is a nurse who loves hiking.",
        speaker="Ana" if transcript else None,
        transcript=transcript,
        style=build_profile(transcript, "Ana"),
    )


def say(author: str, text: str) -> RoomMessage:
    return RoomMessage(author=author, name=NAMES[author], text=text)


def test_the_system_prompt_holds_the_personality_the_style_and_the_examples():
    transcript = [Message("Ana", "yeah sure"), Message("Bo", "ok?"), Message("Ana", "lol ok")]
    system = build_messages(ana(transcript), Room("r", ["ana"]), NAMES)[0]
    assert system["role"] == "system"
    assert "Ana is a nurse who loves hiking." in system["content"]
    assert "lowercase letter" in system["content"]
    assert "Bo: ok?\nAna: lol ok" in system["content"]


def test_the_identity_is_the_assistant_and_the_others_have_names():
    room = Room("r", ["ana", "bo"])
    room.messages += [say(USER, "hi all"), say("bo", "yo"), say("ana", "hey")]
    turns = build_messages(ana(), room, NAMES)[1:]
    assert turns[0] == {"role": "user", "content": "You: hi all\nBo: yo"}
    assert turns[1] == {"role": "assistant", "content": "hey"}


def test_the_roles_always_alternate_and_start_and_end_with_the_user():
    room = Room("r", ["ana"])
    room.messages += [say("ana", "a"), say("ana", "b")]
    roles = [turn["role"] for turn in build_messages(ana(), room, NAMES)[1:]]
    assert roles == ["user", "assistant", "user"]


def test_an_empty_room_asks_for_the_first_message():
    turns = build_messages(ana(), Room("r", ["ana"]), NAMES)[1:]
    assert [turn["role"] for turn in turns] == ["user"]


def test_the_examples_fit_the_budget_and_keep_the_most_recent_messages():
    transcript = [Message("Ana", f"message {n}") for n in range(100)]
    examples = select_examples(ana(transcript), budget=50)
    assert examples[-1].text == "message 99"
    assert sum(len(m.speaker) + len(m.text) + 3 for m in examples) <= 50


def test_split_reply_removes_the_name_before_the_text():
    assert split_reply(ana(), "Ana: hello") == ["hello"]


def test_split_reply_keeps_one_message_for_a_person_who_writes_long_messages():
    assert split_reply(ana(), "one\ntwo") == ["one\ntwo"]


def test_split_reply_makes_many_messages_for_a_person_who_writes_in_bursts():
    identity = ana()
    identity.style = StyleProfile(message_count=10, messages_per_turn=3.0)
    assert split_reply(identity, "one\n\nAna: two\nthree") == ["one", "two", "three"]


def test_the_chosen_exchanges_replace_the_recent_examples():
    transcript = [Message("Bo", "recent question"), Message("Ana", "recent answer")]
    exchanges = [
        Exchange([Message("Bo", "noodles?"), Message("Ana", "yes")], "noodles?"),
        Exchange([Message("Bo", "noodles again?"), Message("Ana", "always")], "noodles again?"),
    ]
    system = build_messages(ana(transcript), Room("r", ["ana"]), NAMES, exchanges)[0]["content"]
    assert "Bo: noodles?\nAna: yes\n...\nBo: noodles again?\nAna: always" in system
    assert "recent answer" not in system


def test_no_exchanges_means_the_recent_examples():
    transcript = [Message("Bo", "recent question"), Message("Ana", "recent answer")]
    system = build_messages(ana(transcript), Room("r", ["ana"]), NAMES, [])[0]["content"]
    assert "Bo: recent question\nAna: recent answer" in system


def test_a_long_room_sends_only_the_recent_messages():
    room = Room("r", ["ana"])
    room.messages += [say(USER, f"message number {n}") for n in range(2000)]
    turns = build_messages(ana(), room, NAMES, history_budget=500)[1:]
    sent = "\n".join(turn["content"] for turn in turns)
    assert turns[0]["content"].startswith(EARLIER)
    assert "message number 1999" in sent and "message number 1000" not in sent
    assert len(sent) < 600


def test_a_short_room_sends_everything_with_no_note():
    room = Room("r", ["ana"])
    room.messages += [say(USER, "hi"), say("ana", "hey")]
    turns = build_messages(ana(), room, NAMES)[1:]
    assert EARLIER not in turns[0]["content"]


def test_the_last_message_goes_even_if_it_is_longer_than_the_budget():
    room = Room("r", ["ana"])
    room.messages += [say(USER, "old"), say(USER, "x" * 100)]
    kept, trimmed = recent_messages(room.messages, budget=10)
    assert [m.text for m in kept] == ["x" * 100] and trimmed


def test_split_reply_removes_the_name_of_another_person_on_the_first_line():
    assert split_reply(ana(), "Bo: omg bro ur not in the server yet", ["Bo", "You"]) == ["omg bro ur not in the server yet"]


def test_split_reply_ends_where_the_model_writes_for_another_person():
    identity = ana()
    identity.style = StyleProfile(message_count=10, messages_per_turn=3.0)
    reply = "ok\nAna: sure\nBo: wait what\nAna: never mind"
    assert split_reply(identity, reply, ["Bo"]) == ["ok", "sure"]


def test_split_reply_keeps_a_colon_that_is_not_after_a_name():
    assert split_reply(ana(), "note: bring cash", ["Bo"]) == ["note: bring cash"]


def test_split_reply_removes_the_name_of_the_identity_in_the_transcript():
    identity = ana([Message("ana_k", "hey"), Message("Bo", "yo")])
    identity.speaker = "ana_k"
    assert split_reply(identity, "ana_k: hello") == ["hello"]

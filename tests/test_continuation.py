from mimikr.continuation import build_continuation, split_continuation
from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.rooms import USER, Room, RoomMessage
from mimikr.style import build_profile
from mimikr.transcript import Message

NAMES = {USER: "You", "sam": "Sam", "bo": "Bo"}


def sam(transcript=None) -> Identity:
    transcript = transcript if transcript is not None else [Message("June", "you up"), Message("Sam", "unfortunately")]
    return Identity(id="sam", display_name="Sam", personality="A cook.\nLikes noodles.", speaker="Sam",
                    transcript=transcript, style=build_profile(transcript, "Sam"))


def say(author: str, name: str, text: str) -> RoomMessage:
    return RoomMessage(author=author, name=name, text=text)


def test_the_log_holds_the_personality_the_examples_the_room_and_ends_with_the_name():
    room = Room("r", ["sam"])
    room.messages += [say(USER, "You", "hi"), say("sam", "Sam", "hey\nwhat"), say(USER, "You", "noodles?")]
    text, _ = build_continuation(sam(), room, NAMES)
    assert text.startswith("The chat log of Sam.\n\nAbout Sam: A cook. Likes noodles.\n\n")
    assert text.endswith("June: you up\nSam: unfortunately\n...\nYou: hi\nSam: hey\nSam: what\nYou: noodles?\nSam:")


def test_the_stop_sequences_are_the_names_of_the_other_people():
    room = Room("r", ["sam", "bo"])
    room.messages += [say("bo", "Bo", "yo")]
    _, stop = build_continuation(sam(), room, NAMES)
    assert stop == ["\nBo:", "\nJune:", "\nYou:"]


def test_the_exchanges_replace_the_recent_examples():
    exchanges = [Exchange([Message("Kim", "pizza?"), Message("Sam", "never")], "pizza?")]
    text, stop = build_continuation(sam(), Room("r", ["sam"]), NAMES, exchanges)
    assert "Kim: pizza?\nSam: never\n...\nSam:" in text
    assert "unfortunately" not in text
    assert "\nKim:" in stop


def test_an_identity_with_no_chat_uses_its_display_name():
    identity = Identity(id="june", display_name="June", personality="A teacher.")
    text, _ = build_continuation(identity, Room("r", ["june"]), {USER: "You", "june": "June"})
    assert text.endswith("The chat log of June.\n\nAbout June: A teacher.\n\nJune:")


def test_lines_with_the_name_start_new_messages_and_other_lines_continue_them():
    assert split_continuation(sam(), " lol\nSam: who is asking\nand why", ["June"]) == ["lol", "who is asking\nand why"]


def test_the_name_of_another_person_or_three_dots_ends_the_reply():
    assert split_continuation(sam(), " ok\nJune: wait\nSam: no", ["June"]) == ["ok"]
    assert split_continuation(sam(), " ok\n...\nSam: no", ["June"]) == ["ok"]


def test_a_colon_in_a_line_of_the_person_is_not_a_speaker():
    assert split_continuation(sam(), " fine\nnote: bring cash", ["June"]) == ["fine\nnote: bring cash"]


def test_an_empty_first_line_takes_the_next_line():
    assert split_continuation(sam(), "\nok then", ["June"]) == ["ok then"]

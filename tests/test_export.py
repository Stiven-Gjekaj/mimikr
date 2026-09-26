from datetime import datetime, timedelta, timezone

from mimikr.export import file_name, room_as_text
from mimikr.rooms import USER, Room, RoomMessage
from mimikr.transcript import parse_transcript

NAMES = {USER: "You", "june": "June", "sam": "Sam"}
NOW = datetime(2026, 9, 26, 16, 50, tzinfo=timezone.utc)


def room() -> Room:
    room = Room("Late night", ["june", "sam"])
    room.messages = [
        RoomMessage(author=USER, name="You", text="anyone up?", time="2026-09-26T15:00:05+00:00"),
        RoomMessage(author="june", name="June", text="yes\nwhy", time="2026-09-26T15:01:00+00:00"),
        RoomMessage(author="sam", name="Sam", text="lol", time="2026-09-26T15:02:00+00:00"),
    ]
    return room


def test_the_export_says_who_wrote_the_messages():
    text = room_as_text(room(), NAMES, now=NOW, zone=timezone.utc)
    assert text.startswith(
        "# Late night\n"
        "# With June and Sam.\n"
        "# Exported from mimikr on 2026-09-26 16:50.\n"
        "# A language model wrote the messages of June and Sam.\n"
        "# June and Sam did not write them.\n\n"
    )


def test_the_messages_have_the_form_of_chat_md():
    text = room_as_text(room(), NAMES, now=NOW, zone=timezone.utc)
    assert text.endswith(
        "[2026-09-26 15:00] You: anyone up?\n"
        "[2026-09-26 15:01] June: yes\n"
        "  why\n"
        "[2026-09-26 15:02] Sam: lol\n"
    )
    assert [(m.speaker, m.text) for m in parse_transcript(text)] == [
        ("You", "anyone up?"), ("June", "yes\nwhy"), ("Sam", "lol"),
    ]


def test_the_times_are_in_the_time_zone():
    text = room_as_text(room(), NAMES, now=NOW, zone=timezone(timedelta(hours=2)))
    assert "[2026-09-26 17:00] You: anyone up?" in text


def test_an_empty_room_says_so():
    assert room_as_text(Room("Quiet", ["sam"]), NAMES, now=NOW).endswith("# The room has no messages.\n")


def test_the_file_name_is_safe():
    assert file_name(Room("Late night: part 2/3", ["sam"]), NOW) == "Late night part 23 2026-09-26.txt"
    assert file_name(Room("???", ["sam"]), NOW) == "room 2026-09-26.txt"

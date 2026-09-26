"""Write a room as plain text, to share it or to keep it.

The lines have the form of chat.md: `[time] Name: text`, and a second line of a
message starts with two spaces. Thus the transcript reader can read an export.

The first lines say that a language model wrote the messages of the
identities. A reader of the file must not think that the real people wrote
them. TERMS.md section 5 says why.
"""

import re
from datetime import datetime, tzinfo

from mimikr.rooms import USER, Room, quote_of


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def local_time(value: str, zone: tzinfo | None) -> str:
    """Write the time of a message in the time zone, to the minute."""
    try:
        return datetime.fromisoformat(value).astimezone(zone).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def room_as_text(room: Room, names: dict[str, str], now: datetime | None = None,
                 zone: tzinfo | None = None) -> str:
    """Return the room as text. zone is the time zone of the times. None is the zone of the computer."""
    members = [names.get(member, member) for member in room.members]
    now = (now or datetime.now().astimezone()).astimezone(zone)
    lines = [
        f"# {room.name}",
        f"# With {join_names(members)}.",
        f"# Exported from mimikr on {now.strftime('%Y-%m-%d %H:%M')}.",
        f"# A language model wrote the messages of {join_names(members)}.",
        f"# {join_names(members)} did not write them.",
        "",
    ]
    for message in room.messages:
        text_lines = [line.strip() for line in message.text.splitlines() if line.strip()]
        if not text_lines:
            continue
        quote = quote_of(room, message)
        if quote:
            text_lines[0] = f"(a reply to {quote.split(':', 1)[0]}) {text_lines[0]}"
        name = "You" if message.author == USER else message.name
        name = re.sub(r"[:\[\]#\s]+", " ", name).strip() or "Unknown"
        lines.append(f"[{local_time(message.time, zone)}] {name}: {text_lines[0]}")
        lines += [f"  {line}" for line in text_lines[1:]]
    if not room.messages:
        lines.append("# The room has no messages.")
    return "\n".join(lines) + "\n"


def file_name(room: Room, now: datetime | None = None) -> str:
    """Suggest a file name: the name of the room and the date."""
    safe = re.sub(r"[^\w\- ]+", "", room.name).strip() or "room"
    return f"{safe} {(now or datetime.now()).strftime('%Y-%m-%d')}.txt"

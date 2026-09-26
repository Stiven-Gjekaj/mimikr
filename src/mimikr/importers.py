"""Read the export of a chat application, and write it as a chat.md transcript.

Each reader returns a list of messages. `write_transcript` writes them in the
`Name: message` form that `transcript.py` reads.
"""

import re

from mimikr.transcript import Message


class ExportError(ValueError):
    """The file is not an export that the reader knows."""

    pass


def clean_name(name: str) -> str:
    """Make a name that the transcript reader accepts: no colon, no brackets, one line."""
    name = re.sub(r"[:\[\]#\s]+", " ", name).strip()
    return name[:64] or "Unknown"


def write_transcript(messages: list[Message]) -> str:
    """Write messages as transcript lines. A second line of a message starts with two spaces."""
    lines = []
    for message in messages:
        text_lines = [line.strip() for line in message.text.strip().splitlines() if line.strip()]
        if not text_lines:
            continue
        time = f"[{message.time}] " if message.time else ""
        lines.append(f"{time}{clean_name(message.speaker)}: {text_lines[0]}")
        lines += [f"  {line}" for line in text_lines[1:]]
    return "\n".join(lines) + "\n" if lines else ""

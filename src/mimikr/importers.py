"""Read the export of a chat application, and write it as a chat.md transcript.

Each reader returns a list of messages. `write_transcript` writes them in the
`Name: message` form that `transcript.py` reads.
"""

import re

from mimikr.transcript import Message


# The start of a message line in a WhatsApp export. Android writes
# "12/31/23, 9:41 PM - Name: text", and iOS writes "[31/12/2023, 21:41:05] Name: text".
_WHATSAPP_LINE = re.compile(
    r"^\[?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?(?:[\s\u202f]?[AaPp]\.?[Mm]\.?)?)\]?\s*(?:-\s*)?(?P<rest>.*)$"
)
# Text that WhatsApp writes in place of a file or of a deleted message.
_WHATSAPP_PLACEHOLDERS = re.compile(
    r"^(?:<Media omitted>|(?:image|video|audio|sticker|GIF|document|Contact card) omitted|"
    r"This message was deleted\.?|You deleted this message\.?|null)$",
    re.IGNORECASE,
)


class ExportError(ValueError):
    """The file is not an export that the reader knows."""


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


def read_whatsapp(text: str) -> list[Message]:
    """Read the text file of 'Export chat' in WhatsApp, with no media.

    A line with no name after the time is a notice from WhatsApp, such as a
    change of the group name. The reader skips it.
    """
    messages: list[Message] = []
    last_was_notice = False
    for line in text.replace("\u200e", "").replace("\u200f", "").splitlines():
        match = _WHATSAPP_LINE.match(line)
        if match is None:
            if messages and not last_was_notice and line.strip():
                messages[-1].text += "\n" + line
            continue
        speaker, separator, body = match["rest"].partition(": ")
        last_was_notice = not separator
        if last_was_notice:
            continue
        body = body.replace("<This message was edited>", "").strip()
        time = f"{match['date']} {match['time'].replace(chr(0x202F), ' ')}"
        messages.append(Message(speaker=speaker.strip(), text=body, time=time))
    if not messages and text.strip():
        raise ExportError("no WhatsApp message found. Export the chat as a text file, with no media")
    return [m for m in messages if not _WHATSAPP_PLACEHOLDERS.match(m.text.strip())]

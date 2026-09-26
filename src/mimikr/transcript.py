"""Read a chat transcript in the `Name: message` form.

The rules:

- One message starts on each line that has the form `Name: text`.
- A line can start with a time in brackets: `[2024-05-01 21:14] Name: text`.
- A line that starts with a space or a tab continues the previous message.
- A line that starts with `#` is a comment. The reader ignores it.
  An indented line that starts with `#` continues a message.
- The reader ignores empty lines.
- A colon must have a space or the end of the line after it.
  Thus `https://example.com` does not start a message.
"""

import re
from dataclasses import dataclass

_MESSAGE_LINE = re.compile(
    r"^(?:\[(?P<time>[^\]]*)\]\s*)?(?P<speaker>[^\s:#\[][^:]{0,63}?)\s*:(?:\s+(?P<text>.*))?$"
)


@dataclass
class Message:
    speaker: str
    text: str
    time: str | None = None


class TranscriptError(ValueError):
    pass


def parse_transcript(source: str) -> list[Message]:
    messages: list[Message] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        if line[0] in " \t":
            if not messages:
                raise TranscriptError(f"line {number}: a continuation line has no message before it")
            messages[-1].text += "\n" + line.strip()
            continue
        match = _MESSAGE_LINE.match(line.rstrip())
        if match is None:
            raise TranscriptError(f"line {number}: expected 'Name: message', got {line.strip()!r}")
        messages.append(
            Message(
                speaker=match["speaker"].strip(),
                text=(match["text"] or "").strip(),
                time=match["time"],
            )
        )
    return [message for message in messages if message.text]


def speakers(messages: list[Message]) -> list[str]:
    """Return each speaker one time, in the order of the first message."""
    return list(dict.fromkeys(message.speaker for message in messages))


def turn_starts(messages: list[Message], speaker: str) -> list[int]:
    """Return the index of the first message of each turn of the speaker."""
    return [
        index
        for index, message in enumerate(messages)
        if message.speaker == speaker and (index == 0 or messages[index - 1].speaker != speaker)
    ]

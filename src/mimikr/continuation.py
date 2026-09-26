"""Build a transcript for a base model to continue.

A base model does not follow instructions, but it continues a document well.
So the prompt is a plain chat log that ends with the name of the person and a
colon. The model writes the next line, and it stops at the name of another
person.
"""

import re

from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.prompt import format_examples
from mimikr.rooms import Room


def speaker_name(identity: Identity) -> str:
    """Return the name of the identity in the log. It is the name in chat.md, if there is one."""
    return identity.speaker or identity.display_name


def other_names(identity: Identity, room: Room, names: dict[str, str], exchanges: list[Exchange] | None) -> list[str]:
    me = speaker_name(identity)
    found = [names.get(member, member) for member in room.members if member != identity.id]
    found += [message.name for message in room.messages if message.author != identity.id]
    found += [message.speaker for message in identity.transcript]
    found += [message.speaker for exchange in exchanges or [] for message in exchange.messages]
    found.append("You")
    return [name for name in dict.fromkeys(found) if name != me]


def build_continuation(identity: Identity, room: Room, names: dict[str, str],
                       exchanges: list[Exchange] | None = None) -> tuple[str, list[str]]:
    """Return the text for the model to continue, and the stop sequences."""
    me = speaker_name(identity)
    parts = [f"The chat log of {me}.", f"About {me}: " + " ".join(identity.personality.split())]
    examples = format_examples(identity, exchanges)
    lines = []
    for message in room.messages:
        who = me if message.author == identity.id else message.name
        lines += [f"{who}: {line}" for line in message.text.splitlines() if line.strip()]
    log = "\n".join([*([examples, "..."] if examples else []), *lines, f"{me}:"])
    parts.append(log)
    stop = [f"\n{name}:" for name in other_names(identity, room, names, exchanges)]
    return "\n\n".join(parts), stop


def split_continuation(identity: Identity, text: str, others: list[str]) -> list[str]:
    """Turn the text of the model into messages.

    A line that starts with the name of the identity starts a new message.
    A line that starts with the name of another person, or a line of three
    dots, ends the reply. A server that ignores the stop sequences thus gives
    no words to another person.
    """
    own = re.compile(rf"^\s*{re.escape(speaker_name(identity))}\s*:\s?")
    foreign = re.compile(r"^\s*(?:" + "|".join(re.escape(name) for name in others) + r")\s*:") if others else None
    messages: list[str] = []
    for number, line in enumerate(text.splitlines()):
        if number > 0 and (line.strip() == "..." or (foreign and foreign.match(line))):
            break
        if number == 0 or own.match(line):
            messages.append(own.sub("", line).strip())
        elif line.strip():
            messages[-1] = f"{messages[-1]}\n{line.strip()}" if messages[-1] else line.strip()
    return [message for message in messages if message]

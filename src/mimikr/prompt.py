"""Build the request to the model for one identity in one room."""

import re

from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.rooms import Room
from mimikr.transcript import Message

# The maximum number of characters of real transcript in the prompt.
EXAMPLE_BUDGET = 6000


def select_examples(identity: Identity, budget: int = EXAMPLE_BUDGET) -> list[Message]:
    """Return the most recent part of the transcript that fits the budget."""
    selected: list[Message] = []
    used = 0
    for message in reversed(identity.transcript):
        cost = len(message.speaker) + len(message.text) + 3
        if used + cost > budget:
            break
        selected.append(message)
        used += cost
    return list(reversed(selected))


def format_examples(identity: Identity, exchanges: list[Exchange] | None) -> str:
    """Write the examples as transcript lines.

    With no exchanges, use the most recent part of the transcript.
    Separate exchanges with a line of three dots, because each is a different
    moment of the conversation.
    """
    if exchanges:
        return "\n...\n".join(
            "\n".join(f"{message.speaker}: {message.text}" for message in exchange.messages)
            for exchange in exchanges
        )
    return "\n".join(f"{message.speaker}: {message.text}" for message in select_examples(identity))


def system_prompt(identity: Identity, room: Room, names: dict[str, str],
                  exchanges: list[Exchange] | None = None) -> str:
    name = identity.display_name
    others = [names.get(member, member) for member in room.members if member != identity.id]
    people = ", ".join(["the user", *others])
    parts = [
        f"You are {name}. You are in a text chat with {people}.",
        f"Write exactly as {name} writes. Write only the text of your next message.",
        f"Do not put your name before the message. Do not say that you are an AI or a model.",
        f"## About {name}\n\n{identity.personality}",
    ]
    style = identity.style.describe()
    if style:
        parts.append(f"## How {name} writes\n\n" + "\n".join(f"- {line}" for line in style))
    transcript = format_examples(identity, exchanges)
    if transcript:
        parts.append(
            f"## Real messages from {name}\n\n"
            f"In this transcript, {name} is '{identity.speaker}'. Copy the tone and the style."
            f" Do not copy the facts into the new chat.\n\n{transcript}"
        )
    return "\n\n".join(parts)


def build_messages(identity: Identity, room: Room, names: dict[str, str],
                   exchanges: list[Exchange] | None = None) -> list[dict]:
    """Return the chat messages for an OpenAI-compatible API.

    The messages of the identity become 'assistant' messages.
    The messages of all other members become 'user' messages with the name first.
    The function joins messages with the same role, because some local models
    need the roles to alternate.
    """
    turns: list[dict] = []
    for message in room.messages:
        if message.author == identity.id:
            role, text = "assistant", message.text
        else:
            role, text = "user", f"{message.name}: {message.text}"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + text
        else:
            turns.append({"role": role, "content": text})

    if not turns:
        turns.append({"role": "user", "content": "(The chat starts. Write the first message.)"})
    if turns[0]["role"] == "assistant":
        turns.insert(0, {"role": "user", "content": "(The chat starts.)"})
    if turns[-1]["role"] == "assistant":
        turns.append({"role": "user", "content": "(Nobody answers. Write your next message.)"})

    return [{"role": "system", "content": system_prompt(identity, room, names, exchanges)}, *turns]


def split_reply(identity: Identity, reply: str) -> list[str]:
    """Clean the reply of the model and split it into messages.

    The function removes a name that the model puts before the text.
    If the person often sends many short messages, each line becomes a message.
    """
    prefix = re.compile(rf"^\s*{re.escape(identity.display_name)}\s*:\s*", re.IGNORECASE)
    lines = [prefix.sub("", line).strip() for line in reply.strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []
    if identity.style.messages_per_turn >= 1.5:
        return lines
    return ["\n".join(lines)]

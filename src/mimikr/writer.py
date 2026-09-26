"""Write the next reply of an identity, in the chat mode or the continuation mode.

The rooms and the evaluation both call this function, so that a score measures
the same prompt that a room sends.
"""

from collections.abc import Callable, Iterable
from typing import Protocol

from mimikr.continuation import build_continuation, other_names, split_continuation
from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.prompt import HISTORY_BUDGET, build_messages, split_reply
from mimikr.rooms import Room
from mimikr.style import drop_repeats, enforce

MODES = ("chat", "continue")
# The number of recent messages of the identity that a new message must not repeat.
REPEAT_WINDOW = 6


class Completer(Protocol):
    def complete(self, messages: list[dict], model: str, temperature: float) -> str: ...

    def continue_text(self, prompt: str, model: str, temperature: float, stop: list[str]) -> str: ...


class ModeError(ValueError):
    pass


def collect(pieces: Iterable[str], split: Callable[[str], list[str]], on_text: Callable[[str], None]) -> str:
    """Join the pieces of a streamed reply. After each piece, show the clean text so far."""
    reply = ""
    for piece in pieces:
        reply += piece
        on_text("\n".join(split(reply)))
    return reply


def write_reply(identity: Identity, room: Room, names: dict[str, str], exchanges: list[Exchange] | None,
                completer: Completer, model: str, temperature: float, mode: str,
                on_text: Callable[[str], None] | None = None, history_budget: int = HISTORY_BUDGET,
                enforce_style: bool = False, avoid_repeats: bool = False) -> list[str]:
    """Return the new messages of the identity.

    With enforce_style, the messages lose what the person clearly never does.

    With on_text, and a completer that can stream, the function calls on_text
    with the text so far while the model writes.
    """
    recent = [message.text for message in room.messages if message.author == identity.id][-REPEAT_WINDOW:]

    def finish(texts: list[str]) -> list[str]:
        texts = enforce(identity.style, texts) if enforce_style else texts
        return drop_repeats(texts, recent) if avoid_repeats else texts

    if mode == "chat":
        messages = build_messages(identity, room, names, exchanges, history_budget)

        others = other_names(identity, room, names, exchanges)

        def split(reply: str) -> list[str]:
            return split_reply(identity, reply, others)

        if on_text and hasattr(completer, "stream_complete"):
            reply = collect(completer.stream_complete(messages, model, temperature), split, on_text)
        else:
            reply = completer.complete(messages, model=model, temperature=temperature)
        return finish(split(reply))
    if mode == "continue":
        text, stop = build_continuation(identity, room, names, exchanges, history_budget)
        others = other_names(identity, room, names, exchanges)

        def split(reply: str) -> list[str]:
            return split_continuation(identity, reply, others)

        if on_text and hasattr(completer, "stream_continue"):
            reply = collect(completer.stream_continue(text, model, temperature, stop), split, on_text)
        else:
            reply = completer.continue_text(text, model=model, temperature=temperature, stop=stop)
        return finish(split(reply))
    raise ModeError(f"the mode is {mode!r}. Use 'chat' or 'continue'")

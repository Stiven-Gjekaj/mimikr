"""Write the next reply of an identity, in the chat mode or the continuation mode.

The rooms and the evaluation both call this function, so that a score measures
the same prompt that a room sends.
"""

from collections.abc import Callable, Iterable
from typing import Protocol

from mimikr.continuation import build_continuation, other_names, split_continuation
from mimikr.examples import Exchange
from mimikr.identity import Identity
from mimikr.prompt import build_messages, split_reply
from mimikr.rooms import Room

MODES = ("chat", "continue")


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
                on_text: Callable[[str], None] | None = None) -> list[str]:
    """Return the new messages of the identity.

    With on_text, and a completer that can stream, the function calls on_text
    with the text so far while the model writes.
    """
    if mode == "chat":
        messages = build_messages(identity, room, names, exchanges)

        def split(reply: str) -> list[str]:
            return split_reply(identity, reply)

        if on_text and hasattr(completer, "stream_complete"):
            reply = collect(completer.stream_complete(messages, model, temperature), split, on_text)
        else:
            reply = completer.complete(messages, model=model, temperature=temperature)
        return split(reply)
    if mode == "continue":
        text, stop = build_continuation(identity, room, names, exchanges)
        others = other_names(identity, room, names, exchanges)

        def split(reply: str) -> list[str]:
            return split_continuation(identity, reply, others)

        if on_text and hasattr(completer, "stream_continue"):
            reply = collect(completer.stream_continue(text, model, temperature, stop), split, on_text)
        else:
            reply = completer.continue_text(text, model=model, temperature=temperature, stop=stop)
        return split(reply)
    raise ModeError(f"the mode is {mode!r}. Use 'chat' or 'continue'")

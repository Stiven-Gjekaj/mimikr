"""Write the next reply of an identity, in the chat mode or the continuation mode.

The rooms and the evaluation both call this function, so that a score measures
the same prompt that a room sends.
"""

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


def write_reply(identity: Identity, room: Room, names: dict[str, str], exchanges: list[Exchange] | None,
                completer: Completer, model: str, temperature: float, mode: str) -> list[str]:
    """Return the new messages of the identity."""
    if mode == "chat":
        reply = completer.complete(build_messages(identity, room, names, exchanges), model=model,
                                   temperature=temperature)
        return split_reply(identity, reply)
    if mode == "continue":
        text, stop = build_continuation(identity, room, names, exchanges)
        reply = completer.continue_text(text, model=model, temperature=temperature, stop=stop)
        return split_continuation(identity, reply, other_names(identity, room, names, exchanges))
    raise ModeError(f"the mode is {mode!r}. Use 'chat' or 'continue'")

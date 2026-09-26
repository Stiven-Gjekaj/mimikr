"""The room engine. It connects rooms, identities and the model.

The engine does not know about the GUI. The GUI calls it from a worker thread.
"""

from typing import Protocol

from mimikr.config import Config
from mimikr.identity import Identity, list_identities
from mimikr.prompt import build_messages, split_reply
from mimikr.rooms import USER, Room, RoomMessage, RoomStore


class Completer(Protocol):
    def complete(self, messages: list[dict], model: str, temperature: float) -> str: ...


class EngineError(RuntimeError):
    pass


class RoomEngine:
    def __init__(self, config: Config, completer: Completer):
        self.config = config
        self.store = RoomStore(config.data_dir)
        self.completer = completer

    def identities(self) -> tuple[dict[str, Identity], dict[str, str]]:
        # Load the files again each time, so that edits take effect without a restart.
        return list_identities(self.config.identities_dir)

    def create_room(self, name: str, members: list[str]) -> Room:
        known, _ = self.identities()
        unknown = [member for member in members if member not in known]
        if unknown or not members:
            raise EngineError(f"a room needs one or more known identities. Unknown: {unknown}")
        return self.store.create(name.strip() or "Room", members)

    def post_user_message(self, room: Room, text: str) -> RoomMessage:
        message = RoomMessage(author=USER, name="You", text=text.strip())
        room.messages.append(message)
        self.store.save(room)
        return message

    def speak(self, room: Room, member: str) -> list[RoomMessage]:
        """Let one member write. Save and return the new messages.

        Raise EngineError or LLMError if the member cannot write.
        """
        known, errors = self.identities()
        identity = known.get(member)
        if identity is None:
            raise EngineError(errors.get(member) or f"the identity {member!r} does not exist")
        names = {USER: "You"} | {key: value.display_name for key, value in known.items()}
        reply = self.completer.complete(
            build_messages(identity, room, names),
            model=identity.model or self.config.model,
            temperature=identity.temperature if identity.temperature is not None else self.config.temperature,
        )
        new = [RoomMessage(author=member, name=identity.display_name, text=text)
               for text in split_reply(identity, reply)]
        room.messages.extend(new)
        self.store.save(room)
        return new

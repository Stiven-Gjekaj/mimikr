"""The room engine. It connects rooms, identities and the model.

The engine does not know about the GUI. The GUI calls it from a worker thread.
"""

import random
import re
from collections.abc import Callable

from mimikr import prompt
from mimikr.config import Config
from mimikr.examples import Embedder, Exchange, ExampleIndex, recent_query
from mimikr.identity import Identity, list_identities
from mimikr.rooms import USER, Room, RoomMessage, RoomStore
from mimikr.transcript import Message
from mimikr.writer import Completer, ModeError, write_reply

# The maximum number of characters of liked replies in a prompt.
LIKED_BUDGET = 1500


class EngineError(RuntimeError):
    pass


class RoomEngine:
    def __init__(self, config: Config, completer: Completer, embed: Embedder | None = None):
        self.config = config
        self.store = RoomStore(config.data_dir)
        self.completer = completer
        self.embed = embed

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

    def find_message(self, room: Room, message_id: str) -> RoomMessage:
        for message in room.messages:
            if message.id == message_id:
                return message
        raise EngineError(f"the room has no message with the id {message_id!r}")

    def delete_message(self, room: Room, message_id: str) -> None:
        room.messages.remove(self.find_message(room, message_id))
        self.store.save(room)

    def edit_message(self, room: Room, message_id: str, text: str) -> None:
        if not text.strip():
            raise EngineError("a message needs text. Delete the message instead")
        self.find_message(room, message_id).text = text.strip()
        self.store.save(room)

    def set_liked(self, room: Room, message_id: str, liked: bool) -> None:
        message = self.find_message(room, message_id)
        if message.author not in room.members:
            raise EngineError("only a reply of an identity can be liked")
        message.liked = liked
        self.store.save(room)

    def last_turn(self, room: Room) -> tuple[str, list[RoomMessage]] | None:
        """Return the member of the last turn and its messages, if an identity wrote the last message."""
        if not room.messages or room.messages[-1].author not in room.members:
            return None
        author = room.messages[-1].author
        turn = []
        for message in reversed(room.messages):
            if message.author != author:
                break
            turn.append(message)
        return author, list(reversed(turn))

    def remove_last_turn(self, room: Room) -> str:
        """Remove the last turn of an identity, so that the identity can write it again. Return the member."""
        last = self.last_turn(room)
        if last is None:
            raise EngineError("the last message is not from an identity")
        member, turn = last
        del room.messages[len(room.messages) - len(turn):]
        self.store.save(room)
        return member

    def liked_exchanges(self, identity: Identity) -> list[Exchange]:
        """Return the replies of the identity that the user liked, in all rooms, with the message before each."""
        me = identity.speaker or identity.display_name
        found: list[Exchange] = []
        for room in self.store.list():
            for index, message in enumerate(room.messages):
                if not (message.liked and message.author == identity.id):
                    continue
                before = room.messages[index - 1] if index and room.messages[index - 1].author != identity.id else None
                lines = ([Message(before.name, before.text)] if before else []) + [Message(me, message.text)]
                found.append(Exchange(messages=lines, query=before.text if before else ""))
        chosen, used = [], 0
        for exchange in reversed(found):
            if used + exchange.cost() > LIKED_BUDGET:
                break
            chosen.append(exchange)
            used += exchange.cost()
        return list(reversed(chosen))

    def next_speaker(self, room: Room, rng: random.Random | None = None) -> str:
        """Choose the member that speaks next.

        With turn_taking = "rotate", the members speak in the order of the room.
        With "smart", a member whose name is in the last message speaks next.
        Otherwise a random member speaks, but not the member that spoke last.
        """
        if self.config.turn_taking == "rotate" or len(room.members) == 1:
            return room.next_speaker()
        if self.config.turn_taking != "smart":
            raise EngineError(f"the setting turn_taking is {self.config.turn_taking!r}. Use 'smart' or 'rotate'")
        if not any(message.author in room.members for message in room.messages):
            return room.members[0]
        last = room.messages[-1]
        candidates = [member for member in room.members if member != last.author]
        known, _ = self.identities()
        for member in candidates:
            name = known[member].display_name if member in known else member
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", last.text, re.IGNORECASE):
                return member
        return (rng or random).choice(candidates)

    def choose_exchanges(self, identity: Identity, room: Room) -> list[Exchange] | None:
        """Return the exchanges for the prompt, or None for the recent examples."""
        if self.config.examples == "recent" or identity.speaker is None:
            return None
        if self.config.examples != "similar":
            raise EngineError(f"the setting examples is {self.config.examples!r}. Use 'recent' or 'similar'")
        if self.embed is None:
            raise EngineError("the setting examples = 'similar' needs an embedding model")
        index = ExampleIndex.cached(
            identity.transcript,
            identity.speaker,
            self.embed,
            self.config.data_dir / "index" / f"{identity.id}.json",
            self.config.embedding_model,
        )
        query = recent_query([(message.author == identity.id, message.text) for message in room.messages])
        return index.select(query, self.embed, prompt.EXAMPLE_BUDGET)

    def speak(self, room: Room, member: str, on_text: Callable[[str], None] | None = None) -> list[RoomMessage]:
        """Let one member write. Save and return the new messages.

        on_text receives the text so far while the model writes.

        Raise EngineError or LLMError if the member cannot write.
        """
        known, errors = self.identities()
        identity = known.get(member)
        if identity is None:
            raise EngineError(errors.get(member) or f"the identity {member!r} does not exist")
        names = {USER: "You"} | {key: value.display_name for key, value in known.items()}
        exchanges = self.choose_exchanges(identity, room)
        liked = self.liked_exchanges(identity)
        if liked:
            # The liked replies come after the examples of the transcript.
            recent = [Exchange(prompt.select_examples(identity), "")] if identity.transcript else []
            exchanges = (exchanges or recent) + liked
        try:
            texts = write_reply(
                identity, room, names, exchanges, self.completer,
                model=identity.model or self.config.model,
                temperature=identity.temperature if identity.temperature is not None else self.config.temperature,
                mode=identity.mode or self.config.mode,
                on_text=on_text,
                history_budget=self.config.history_budget,
                enforce_style=self.config.enforce_style,
                avoid_repeats=self.config.avoid_repeats,
            )
        except ModeError as error:
            raise EngineError(str(error)) from None
        new = [RoomMessage(author=member, name=identity.display_name, text=text) for text in texts]
        room.messages.extend(new)
        self.store.save(room)
        return new

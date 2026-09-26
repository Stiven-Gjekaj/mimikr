"""Rooms: conversations between the user and one or more identities.

The store keeps each room as one JSON file in `<data_dir>/rooms/`.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

USER = "user"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class RoomMessage:
    author: str
    name: str
    text: str
    id: str = field(default_factory=_new_id)
    time: str = field(default_factory=_now)


@dataclass
class Room:
    name: str
    members: list[str]
    id: str = field(default_factory=_new_id)
    created: str = field(default_factory=_now)
    messages: list[RoomMessage] = field(default_factory=list)

    def next_speaker(self) -> str:
        """Return the member that speaks after the last member that spoke."""
        if not self.members:
            raise ValueError("the room has no members")
        for message in reversed(self.messages):
            if message.author in self.members:
                position = self.members.index(message.author)
                return self.members[(position + 1) % len(self.members)]
        return self.members[0]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        messages = [RoomMessage(**message) for message in data.get("messages", [])]
        return cls(
            name=data["name"],
            members=list(data["members"]),
            id=data["id"],
            created=data["created"],
            messages=messages,
        )


class RoomStore:
    def __init__(self, data_dir: Path):
        self.directory = data_dir / "rooms"
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, room_id: str) -> Path:
        if not room_id.isalnum():
            raise KeyError(room_id)
        return self.directory / f"{room_id}.json"

    def create(self, name: str, members: list[str]) -> Room:
        room = Room(name=name, members=members)
        self.save(room)
        return room

    def get(self, room_id: str) -> Room:
        path = self._path(room_id)
        if not path.is_file():
            raise KeyError(room_id)
        return Room.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[Room]:
        rooms = [
            Room.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in self.directory.glob("*.json")
        ]
        return sorted(rooms, key=lambda room: room.created)

    def save(self, room: Room) -> None:
        path = self._path(room.id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(room.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def delete(self, room_id: str) -> None:
        self._path(room_id).unlink(missing_ok=True)

import pytest

from mimikr.config import Config
from mimikr.engine import EngineError, RoomEngine


class FakeModel:
    """Reply with a fixed text and keep each request."""

    def __init__(self, reply: str = "hello"):
        self.reply = reply
        self.requests: list[dict] = []

    def complete(self, messages, model, temperature):
        self.requests.append({"messages": messages, "model": model, "temperature": temperature})
        return self.reply


def make_engine(tmp_path, model: FakeModel, people=("ana", "bo")) -> RoomEngine:
    for person in people:
        directory = tmp_path / "identities" / person
        directory.mkdir(parents=True)
        (directory / "personality.md").write_text(f"This is {person}.", encoding="utf-8")
    config = Config(identities_dir=tmp_path / "identities", data_dir=tmp_path / "data", model="default-model")
    return RoomEngine(config, model)


def test_refuses_a_room_with_an_unknown_member(tmp_path):
    engine = make_engine(tmp_path, FakeModel())
    with pytest.raises(EngineError, match="zed"):
        engine.create_room("r", ["zed"])


def test_a_member_replies_and_the_store_keeps_the_messages(tmp_path):
    model = FakeModel(reply="hey")
    engine = make_engine(tmp_path, model)
    room = engine.create_room("r", ["ana", "bo"])
    engine.post_user_message(room, "  hi all ")
    [reply] = engine.speak(room, "ana")
    assert (reply.author, reply.name, reply.text) == ("ana", "ana", "hey")
    assert model.requests[0]["model"] == "default-model"
    assert "This is ana." in model.requests[0]["messages"][0]["content"]
    assert [m.text for m in engine.store.get(room.id).messages] == ["hi all", "hey"]


def test_the_identity_settings_choose_the_model(tmp_path):
    model = FakeModel()
    engine = make_engine(tmp_path, model)
    (tmp_path / "identities" / "ana" / "identity.toml").write_text('model = "small"\ntemperature = 0.1\n')
    room = engine.create_room("r", ["ana"])
    engine.speak(room, "ana")
    assert (model.requests[0]["model"], model.requests[0]["temperature"]) == ("small", 0.1)


def test_a_removed_identity_gives_an_error(tmp_path):
    engine = make_engine(tmp_path, FakeModel())
    room = engine.create_room("r", ["ana"])
    (tmp_path / "identities" / "ana" / "personality.md").unlink()
    with pytest.raises(EngineError, match="does not exist"):
        engine.speak(room, "ana")

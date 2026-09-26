import pytest

from test_evaluate import WordEmbedder

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


NOODLE_CHAT = "\n".join([
    "June: how was the kitchen shift", "Ana: chaos as usual",
    "June: want noodles for lunch", "Ana: noodles always",
    "June: did you watch the football match", "Ana: we lost again",
])


def similar_engine(tmp_path, model, embed=None):
    engine = make_engine(tmp_path, model, people=("ana",))
    (tmp_path / "identities" / "ana" / "chat.md").write_text(NOODLE_CHAT, encoding="utf-8")
    engine.config.examples = "similar"
    engine.embed = embed
    return engine


def test_similar_examples_put_the_matching_exchange_into_the_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr("mimikr.prompt.EXAMPLE_BUDGET", 60)
    model = FakeModel()
    engine = similar_engine(tmp_path, model, WordEmbedder())
    room = engine.create_room("r", ["ana"])
    engine.post_user_message(room, "noodles tonight?")
    engine.speak(room, "ana")
    system = model.requests[0]["messages"][0]["content"]
    assert "Ana: noodles always" in system
    assert "football" not in system and "kitchen" not in system
    assert (tmp_path / "data" / "index" / "ana.json").is_file()


def test_recent_examples_ignore_the_message(tmp_path, monkeypatch):
    monkeypatch.setattr("mimikr.prompt.EXAMPLE_BUDGET", 60)
    model = FakeModel()
    engine = similar_engine(tmp_path, model, WordEmbedder())
    engine.config.examples = "recent"
    room = engine.create_room("r", ["ana"])
    engine.post_user_message(room, "noodles tonight?")
    engine.speak(room, "ana")
    assert "Ana: we lost again" in model.requests[0]["messages"][0]["content"]


def test_similar_examples_need_an_embedding_model(tmp_path):
    engine = similar_engine(tmp_path, FakeModel(), embed=None)
    room = engine.create_room("r", ["ana"])
    with pytest.raises(EngineError, match="needs an embedding model"):
        engine.speak(room, "ana")


def test_an_unknown_examples_setting_is_an_error(tmp_path):
    engine = similar_engine(tmp_path, FakeModel(), WordEmbedder())
    engine.config.examples = "best"
    room = engine.create_room("r", ["ana"])
    with pytest.raises(EngineError, match="'recent' or 'similar'"):
        engine.speak(room, "ana")

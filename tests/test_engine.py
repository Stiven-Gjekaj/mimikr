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

    def continue_text(self, prompt, model, temperature, stop):
        self.requests.append({"prompt": prompt, "stop": stop, "model": model})
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


def test_the_continue_mode_sends_a_chat_log(tmp_path):
    model = FakeModel(reply=" sure\nana: why not\nYou: ok")
    engine = make_engine(tmp_path, model, people=("ana",))
    engine.config.mode = "continue"
    room = engine.create_room("r", ["ana"])
    engine.post_user_message(room, "lunch?")
    new = engine.speak(room, "ana")
    assert model.requests[0]["prompt"].endswith("You: lunch?\nana:")
    assert "\nYou:" in model.requests[0]["stop"]
    assert [m.text for m in new] == ["sure", "why not"]


def test_the_mode_of_the_identity_has_priority(tmp_path):
    model = FakeModel()
    engine = make_engine(tmp_path, model, people=("ana",))
    (tmp_path / "identities" / "ana" / "identity.toml").write_text('mode = "continue"\n')
    engine.speak(engine.create_room("r", ["ana"]), "ana")
    assert "prompt" in model.requests[0]


def test_an_unknown_mode_is_an_error(tmp_path):
    engine = make_engine(tmp_path, FakeModel(), people=("ana",))
    engine.config.mode = "poetry"
    with pytest.raises(EngineError, match="'chat' or 'continue'"):
        engine.speak(engine.create_room("r", ["ana"]), "ana")


class StreamingModel(FakeModel):
    def stream_complete(self, messages, model, temperature):
        yield from ["Ana: ", "lol", " ok"]

    def stream_continue(self, prompt, model, temperature, stop):
        yield from [" su", "re\nYou: x"]


def test_speak_shows_the_text_while_the_model_writes(tmp_path):
    engine = make_engine(tmp_path, StreamingModel(), people=("ana",))
    seen = []
    new = engine.speak(engine.create_room("r", ["ana"]), "ana", on_text=seen.append)
    assert seen == ["", "lol", "lol ok"]
    assert [m.text for m in new] == ["lol ok"]


def test_speak_streams_in_the_continue_mode_and_hides_other_speakers(tmp_path):
    engine = make_engine(tmp_path, StreamingModel(), people=("ana",))
    engine.config.mode = "continue"
    seen = []
    new = engine.speak(engine.create_room("r", ["ana"]), "ana", on_text=seen.append)
    assert seen == ["su", "sure"]
    assert [m.text for m in new] == ["sure"]


def test_a_model_that_cannot_stream_still_replies(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="hey"), people=("ana",))
    seen = []
    assert [m.text for m in engine.speak(engine.create_room("r", ["ana"]), "ana", on_text=seen.append)] == ["hey"]
    assert seen == []


def test_the_engine_uses_the_history_budget_of_the_settings(tmp_path):
    model = FakeModel()
    engine = make_engine(tmp_path, model, people=("ana",))
    engine.config.history_budget = 100
    room = engine.create_room("r", ["ana"])
    for n in range(50):
        engine.post_user_message(room, f"message {n}")
    engine.speak(room, "ana")
    sent = "\n".join(m["content"] for m in model.requests[0]["messages"][1:])
    assert "message 49" in sent and "message 0\n" not in sent

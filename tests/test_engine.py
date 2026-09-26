import random

import pytest

from test_evaluate import WordEmbedder

from mimikr.config import Config
from mimikr.engine import EngineError, RoomEngine
from mimikr.rooms import RoomMessage


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
    config = Config(identities_dir=tmp_path / "identities", data_dir=tmp_path / "data", model="default-model",
                    mode="chat")
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


def test_the_engine_enforces_the_style_of_the_transcript(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="Sure thing."), people=("ana",))
    (tmp_path / "identities" / "ana" / "chat.md").write_text(
        "\n".join(f"June: q{n}\nana: yeah ok {n}" for n in range(6)), encoding="utf-8")
    room = engine.create_room("r", ["ana"])
    assert [m.text for m in engine.speak(room, "ana")] == ["sure thing"]
    engine.config.enforce_style = False
    assert [m.text for m in engine.speak(room, "ana")] == ["Sure thing."]


def three(tmp_path) -> tuple:
    engine = make_engine(tmp_path, FakeModel(), people=("ana", "bo", "cy"))
    return engine, engine.create_room("r", ["ana", "bo", "cy"])


def test_the_first_member_speaks_first(tmp_path):
    engine, room = three(tmp_path)
    assert engine.next_speaker(room) == "ana"


def test_a_member_named_in_the_last_message_speaks_next(tmp_path):
    engine, room = three(tmp_path)
    engine.speak(room, "ana")
    engine.post_user_message(room, "what do you think, CY?")
    assert engine.next_speaker(room, random.Random(1)) == "cy"


def test_a_name_inside_a_word_does_not_count(tmp_path):
    engine, room = three(tmp_path)
    room.messages.append(RoomMessage(author="ana", name="ana", text="the boat is late"))
    picks = {engine.next_speaker(room, random.Random(seed)) for seed in range(30)}
    assert picks == {"bo", "cy"}


def test_the_last_speaker_does_not_speak_twice_in_a_row(tmp_path):
    engine, room = three(tmp_path)
    room.messages.append(RoomMessage(author="bo", name="bo", text="hm"))
    assert all(engine.next_speaker(room, random.Random(seed)) != "bo" for seed in range(30))


def test_rotate_keeps_the_order_of_the_room(tmp_path):
    engine, room = three(tmp_path)
    engine.config.turn_taking = "rotate"
    room.messages.append(RoomMessage(author="ana", name="ana", text="hey cy"))
    assert engine.next_speaker(room) == "bo"


def test_edit_and_delete_change_the_saved_room(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="hey"), people=("ana",))
    room = engine.create_room("r", ["ana"])
    first = engine.post_user_message(room, "hi")
    [reply] = engine.speak(room, "ana")
    engine.edit_message(room, reply.id, "  hello there ")
    engine.delete_message(room, first.id)
    assert [m.text for m in engine.store.get(room.id).messages] == ["hello there"]
    with pytest.raises(EngineError, match="needs text"):
        engine.edit_message(room, reply.id, "   ")


def test_regenerate_removes_the_whole_last_turn(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="a\nb"), people=("ana",))
    room = engine.create_room("r", ["ana"])
    engine.post_user_message(room, "hi")
    room.messages += [RoomMessage(author="ana", name="ana", text=t) for t in ("one", "two")]
    assert engine.remove_last_turn(room) == "ana"
    assert [m.text for m in engine.store.get(room.id).messages] == ["hi"]
    with pytest.raises(EngineError, match="not from an identity"):
        engine.remove_last_turn(room)


def test_a_liked_reply_is_an_example_in_later_prompts(tmp_path):
    model = FakeModel(reply="hey")
    engine = make_engine(tmp_path, model, people=("ana",))
    room = engine.create_room("r", ["ana"])
    engine.post_user_message(room, "noodles tonight?")
    [reply] = engine.speak(room, "ana")
    engine.set_liked(room, reply.id, True)
    other = engine.create_room("other", ["ana"])
    engine.speak(other, "ana")
    system = model.requests[-1]["messages"][0]["content"]
    assert "You: noodles tonight?\nana: hey" in system
    engine.set_liked(room, reply.id, False)
    engine.speak(other, "ana")
    assert "noodles tonight" not in model.requests[-1]["messages"][0]["content"]


def test_only_a_reply_of_an_identity_can_be_liked(tmp_path):
    engine = make_engine(tmp_path, FakeModel(), people=("ana",))
    room = engine.create_room("r", ["ana"])
    mine = engine.post_user_message(room, "hi")
    with pytest.raises(EngineError, match="only a reply"):
        engine.set_liked(room, mine.id, True)


def test_old_room_files_with_no_liked_field_still_load(tmp_path):
    import json

    engine = make_engine(tmp_path, FakeModel(), people=("ana",))
    room = engine.create_room("r", ["ana"])
    path = tmp_path / "data" / "rooms" / f"{room.id}.json"
    data = json.loads(path.read_text())
    data["messages"] = [{"author": "user", "name": "You", "text": "hi", "id": "abc", "time": "2026-01-01T00:00:00+00:00"}]
    path.write_text(json.dumps(data))
    assert engine.store.get(room.id).messages[0].liked is False


def test_a_reply_that_starts_with_the_name_of_another_member_loses_the_name(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="bo: you are late\nbo: sorry"), people=("ana", "bo"))
    room = engine.create_room("r", ["ana", "bo"])
    assert [m.text for m in engine.speak(room, "ana")] == ["you are late"]


def test_the_engine_does_not_send_the_same_short_reply_again(tmp_path):
    engine = make_engine(tmp_path, FakeModel(reply="bet"), people=("ana",))
    room = engine.create_room("r", ["ana"])
    assert [m.text for m in engine.speak(room, "ana")] == ["bet"]
    assert engine.speak(room, "ana") == []
    engine.config.avoid_repeats = False
    assert [m.text for m in engine.speak(room, "ana")] == ["bet"]

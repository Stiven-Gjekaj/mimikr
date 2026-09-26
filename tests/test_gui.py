"""Drive the window with no screen. Qt draws into memory."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from mimikr.config import Config
from mimikr.engine import RoomEngine
from mimikr.gui import MainWindow
from mimikr.llm import LLMError


class FakeModel:
    def __init__(self, reply: str = "hello", error: str | None = None):
        self.reply = reply
        self.error = error

    def complete(self, messages, model, temperature):
        if self.error:
            raise LLMError(self.error)
        return self.reply


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def make_window(tmp_path, model: FakeModel) -> MainWindow:
    for person in ("ana", "bo"):
        directory = tmp_path / "identities" / person
        directory.mkdir(parents=True)
        (directory / "personality.md").write_text(f"This is {person}.", encoding="utf-8")
    config = Config(identities_dir=tmp_path / "identities", data_dir=tmp_path / "data")
    return MainWindow(RoomEngine(config, model))


def wait_until_idle(application, window: MainWindow) -> None:
    deadline = time.monotonic() + 5
    while window.busy:
        assert time.monotonic() < deadline, "the worker did not stop"
        application.processEvents()
        time.sleep(0.01)
    application.processEvents()


def test_the_window_lists_the_saved_rooms(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    window.engine.create_room("Friends", ["ana", "bo"])
    window.reload_rooms()
    assert window.rooms.item(0).text() == "Friends\nana, bo"


def test_each_member_replies_to_the_user(application, tmp_path):
    window = make_window(tmp_path, FakeModel(reply="hey"))
    room = window.engine.create_room("r", ["ana", "bo"])
    window.select_room(room.id)
    window.composer.setPlainText("hi all")
    window.send()
    wait_until_idle(application, window)
    assert window.view.texts() == ["hi all", "hey", "hey"]
    assert window.composer.toPlainText() == ""
    assert [m.author for m in window.engine.store.get(room.id).messages] == ["user", "ana", "bo"]


def test_next_speaker_lets_the_members_talk_in_turn(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    room = window.engine.create_room("r", ["ana", "bo"])
    window.select_room(room.id)
    for _ in range(3):
        window.next_speaker()
        wait_until_idle(application, window)
    assert [m.author for m in window.engine.store.get(room.id).messages] == ["ana", "bo", "ana"]


def test_a_model_fault_shows_in_the_status_line(application, tmp_path):
    window = make_window(tmp_path, FakeModel(error="cannot reach the model server"))
    room = window.engine.create_room("r", ["ana"])
    window.select_room(room.id)
    window.next_speaker()
    wait_until_idle(application, window)
    assert window.status.text() == "cannot reach the model server"
    assert window.send_button.isEnabled()


class StreamingModel(FakeModel):
    def stream_complete(self, messages, model, temperature):
        yield from ["say", " less"]


def test_the_reply_shows_as_a_draft_and_then_as_a_message(application, tmp_path):
    window = make_window(tmp_path, StreamingModel())
    drafts = []
    window.bridge.partial.connect(lambda room, author, name, text: drafts.append(window.view.draft_text()))
    room = window.engine.create_room("r", ["ana"])
    window.select_room(room.id)
    window.next_speaker()
    wait_until_idle(application, window)
    # The window handles each piece first, so the draft already shows the text so far.
    assert drafts == ["say", "say less"]
    assert window.view.texts() == ["say less"]
    assert window.view.draft is None


def test_a_draft_is_not_a_message(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    view = window.view
    view.show_draft("ana", "ana", "hel")
    view.show_draft("ana", "ana", "hello")
    assert view.draft_text() == "hello"
    assert view.texts() == []
    view.clear_draft()
    assert view.draft is None


def test_auto_lets_the_members_talk_for_the_number_of_turns(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    room = window.engine.create_room("r", ["ana", "bo"])
    window.select_room(room.id)
    window.turns.setValue(10)
    window.auto_or_stop()
    assert window.auto_button.text() == "Stop"
    wait_until_idle(application, window)
    authors = [m.author for m in window.engine.store.get(room.id).messages]
    assert authors == ["ana", "bo"] * 5
    assert window.auto_button.text() == "Auto"


class StopAfter(FakeModel):
    """Click Stop from inside the third reply, as a user who clicks during a turn."""

    def __init__(self, window_holder, count):
        super().__init__()
        self.window_holder = window_holder
        self.count = count
        self.calls = 0

    def complete(self, messages, model, temperature):
        self.calls += 1
        if self.calls == self.count:
            self.window_holder[0].stop_event.set()
        return "hi"


def test_stop_ends_an_automatic_conversation_after_the_current_turn(application, tmp_path):
    holder = []
    window = make_window(tmp_path, StopAfter(holder, 3))
    holder.append(window)
    room = window.engine.create_room("r", ["ana", "bo"])
    window.select_room(room.id)
    window.auto_or_stop()
    wait_until_idle(application, window)
    assert len(window.engine.store.get(room.id).messages) == 3
    assert window.status.text() == "Stopped."


class StopWhileWriting(FakeModel):
    def __init__(self, window_holder):
        super().__init__()
        self.window_holder = window_holder

    def stream_complete(self, messages, model, temperature):
        yield "half"
        self.window_holder[0].stop_event.set()
        yield " of a reply"


def test_stop_while_the_model_writes_keeps_no_part_of_the_reply(application, tmp_path):
    holder = []
    window = make_window(tmp_path, StopWhileWriting(holder))
    holder.append(window)
    room = window.engine.create_room("r", ["ana"])
    window.select_room(room.id)
    window.auto_or_stop()
    wait_until_idle(application, window)
    assert window.engine.store.get(room.id).messages == []
    assert window.view.texts() == [] and window.view.draft is None
    assert window.status.text() == "Stopped."

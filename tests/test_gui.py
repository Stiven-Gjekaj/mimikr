"""Drive the window with no screen. Qt draws into memory."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

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


def make_window(tmp_path, model: FakeModel, reconnect=None) -> MainWindow:
    for person in ("ana", "bo"):
        directory = tmp_path / "identities" / person
        directory.mkdir(parents=True)
        (directory / "personality.md").write_text(f"This is {person}.", encoding="utf-8")
    config = Config(identities_dir=tmp_path / "identities", data_dir=tmp_path / "data")
    return MainWindow(RoomEngine(config, model), config_path=tmp_path / "mimikr.toml", reconnect=reconnect)


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
    card = window.rooms.itemWidget(window.rooms.item(0))
    assert card.findChild(QLabel, "roomTitle").text() == "Friends"
    assert card.findChild(QLabel, "roomMembers").text() == "ana, bo"


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


def test_a_short_message_does_not_wrap_and_a_long_one_does(application, tmp_path):
    from mimikr.gui import BUBBLE_WIDTH
    from mimikr.rooms import RoomMessage

    window = make_window(tmp_path, FakeModel())
    window.view.add(RoomMessage(author="ana", name="ana", text="who is asking"))
    window.view.add(RoomMessage(author="ana", name="ana", text="word " * 80))
    short, long = [label for label in window.view.findChildren(QLabel) if label.objectName() == "bubble"]
    assert not short.wordWrap()
    assert long.wordWrap() and long.minimumWidth() <= BUBBLE_WIDTH


def test_the_window_uses_the_theme_of_the_settings(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    window.engine.config.theme = "dark"
    window.engine.config.accent = "#123456"
    window.apply_theme()
    assert window.palette_now.dark
    assert "#123456" in window.styleSheet()


def test_the_settings_button_opens_and_closes_the_settings(application, tmp_path):
    from mimikr.gui import EMPTY_PAGE, SETTINGS_PAGE

    window = make_window(tmp_path, FakeModel())
    window.settings_button.click()
    assert window.pages.currentIndex() == SETTINGS_PAGE
    window.settings_button.click()
    assert window.pages.currentIndex() == EMPTY_PAGE


def test_a_change_of_the_look_shows_before_the_save_and_revert_takes_it_back(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    window.engine.config.theme = "light"
    window.settings.load(window.engine.config)
    window.settings.saved_config.theme = "light"
    window.apply_theme()
    window.settings.theme.setCurrentIndex(2)
    window.settings.swatches["teal"].click()
    assert window.palette_now.dark and window.palette_now.accent == "#14b8a6"
    assert not (tmp_path / "mimikr.toml").exists()
    window.settings.revert()
    assert not window.palette_now.dark and window.palette_now.accent == "#8b5cf6"


def test_save_writes_the_file_and_reconnects(application, tmp_path):
    from mimikr.config import load_config

    reconnected = []
    window = make_window(tmp_path, FakeModel(), reconnect=reconnected.append)
    page = window.settings
    page.base_url.setText("http://localhost:8080/v1")
    page.model.setText("mistral-nemo")
    page.embedding_url.setText("http://localhost:8081/v1")
    page.mode.setCurrentIndex(page.mode.findData("continue"))
    page.examples.setCurrentIndex(page.examples.findData("similar"))
    page.temperature.setValue(0.65)
    page.font_size.setValue(16)
    page.save_button.click()
    saved = load_config(tmp_path / "mimikr.toml", environ={})
    assert (saved.base_url, saved.model, saved.embedding_url) == (
        "http://localhost:8080/v1", "mistral-nemo", "http://localhost:8081/v1")
    assert (saved.mode, saved.examples, saved.temperature, saved.font_size) == ("continue", "similar", 0.65, 16)
    assert reconnected == [window.engine.config]
    assert "Saved to" in page.note.text()


def test_a_wrong_custom_accent_is_refused(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    page = window.settings
    page.custom_accent.setText("orange-ish")
    page.choose_custom_accent()
    assert "six hex digits" in page.accent_error.text()
    assert window.engine.config.accent == "violet"
    page.custom_accent.setText("#FF8800")
    page.choose_custom_accent()
    assert window.engine.config.accent == "#ff8800" and page.accent_error.text() == ""


def test_test_connection_checks_the_fields_before_a_save(application, tmp_path):
    seen = []

    def checker(config):
        seen.append((config.base_url, config.model))
        return [(True, "Chat server: 1 model (mistral-nemo)."), (False, "Embedding server: refused.")]

    window = make_window(tmp_path, FakeModel())
    page = window.settings
    page.checker = checker
    page.base_url.setText("http://localhost:8080/v1")
    page.model.setText("mistral-nemo")
    page.check()
    deadline = time.monotonic() + 5
    while not page.check_button.isEnabled():
        assert time.monotonic() < deadline
        application.processEvents()
        time.sleep(0.01)
    assert seen == [("http://localhost:8080/v1", "mistral-nemo")]
    assert page.check_result.text() == "OK: Chat server: 1 model (mistral-nemo).\nFault: Embedding server: refused."
    # The check does not change the settings.
    assert window.engine.config.base_url != "http://localhost:8080/v1"


def write_picture(path, width=40, height=20, color="red"):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path))
    return path


def avatars_in(widget):
    return [label for label in widget.findChildren(QLabel) if label.objectName() == "avatar"]


def test_an_identity_with_a_picture_shows_it_and_one_with_none_shows_initials(application, tmp_path):
    from mimikr.rooms import RoomMessage

    window = make_window(tmp_path, FakeModel())
    write_picture(tmp_path / "identities" / "ana" / "avatar.png")
    window.view.add(RoomMessage(author="ana", name="ana", text="hi"))
    window.view.add(RoomMessage(author="bo", name="bo", text="yo"))
    ana, bo = avatars_in(window.view)
    assert not ana.pixmap().isNull() and ana.text() == ""
    assert bo.pixmap().isNull() and bo.text() == "B"


def test_the_picture_is_a_circle_from_the_middle_of_the_image(application, tmp_path):
    from mimikr.gui import round_picture

    pixmap = round_picture(write_picture(tmp_path / "wide.png", 80, 20), 28)
    image = pixmap.toImage()
    assert image.width() == image.height() == 56
    # The corner is outside the circle, and the middle is inside it.
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(28, 28).red() == 255


def test_a_file_that_is_not_a_picture_shows_the_initials(application, tmp_path):
    from mimikr.gui import avatar

    broken = tmp_path / "avatar.png"
    broken.write_bytes(b"not a png")
    assert avatar("ana", "ana", picture=broken).text() == "A"


def test_a_room_card_shows_the_picture_of_the_room(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    room = window.engine.create_room("r", ["ana"])
    write_picture(window.avatars.path_for("room", room.id))
    window.reload_rooms()
    [picture] = avatars_in(window.rooms.itemWidget(window.rooms.item(0)))
    assert not picture.pixmap().isNull()


def test_choose_a_picture_for_an_identity_from_the_settings(application, tmp_path):
    from PySide6.QtGui import QImage

    window = make_window(tmp_path, FakeModel())
    window.pick_image = lambda: write_picture(tmp_path / "photo.jpg", 300, 200)
    window.show_settings()
    window.choose_picture("identity", "ana")
    saved = tmp_path / "data" / "avatars" / "identity-ana.png"
    image = QImage(str(saved))
    assert (image.width(), image.height()) == (256, 256)
    # The directory of the identity gets no file.
    assert sorted(p.name for p in (tmp_path / "identities" / "ana").iterdir()) == ["personality.md"]
    rows = [label for label in window.settings.findChildren(QLabel) if label.objectName() == "avatar"]
    assert any(not label.pixmap().isNull() for label in rows)


def test_a_file_that_is_not_an_image_is_refused(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    window = make_window(tmp_path, FakeModel())
    text = tmp_path / "notes.png"
    text.write_text("hello", encoding="utf-8")
    window.pick_image = lambda: text
    window.choose_picture("identity", "ana")
    assert warnings == ["notes.png is not an image that mimikr can read"]
    assert not (tmp_path / "data" / "avatars" / "identity-ana.png").exists()


def test_a_cancelled_choice_changes_nothing(application, tmp_path):
    window = make_window(tmp_path, FakeModel())
    window.pick_image = lambda: None
    window.choose_picture("room", "abc")
    assert not (tmp_path / "data" / "avatars").exists()


def test_the_room_picture_shows_in_the_header_and_goes_with_the_room(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = make_window(tmp_path, FakeModel())
    room = window.engine.create_room("r", ["ana"])
    window.select_room(room.id)
    window.pick_image = lambda: write_picture(tmp_path / "room.png")
    window.choose_picture("room", room.id)
    [header_picture] = avatars_in(window.room_picture)
    assert not header_picture.pixmap().isNull()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.delete_room()
    assert not window.avatars.path_for("room", room.id).exists()

"""The desktop window of mimikr. It uses Qt through PySide6.

The model calls block, so a worker thread runs them.
The worker sends its results to the window through Qt signals.
Only one worker runs at a time.
"""

import sys
import threading

from collections.abc import Callable

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mimikr import theme
from mimikr.config import Config, embedding_base_url
from mimikr.engine import EngineError, RoomEngine
from mimikr.llm import ChatClient, LLMError
from mimikr.rooms import USER, Room, RoomMessage

BUBBLE_WIDTH = 520
AVATAR_SIZE = 28
# The pages of the main area.
EMPTY_PAGE, ROOM_PAGE, SETTINGS_PAGE = 0, 1, 2


def avatar(key: str, name: str, size: int = AVATAR_SIZE) -> QLabel:
    """Return a round picture with the initials of a name, in the color of the key."""
    label = QLabel(theme.initials(name), objectName="avatar", alignment=Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(size, size)
    label.setStyleSheet(f"background: {theme.avatar_color(key)}; border-radius: {size // 2}px;")
    return label


def system_is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


class Stopped(Exception):
    """The user clicked Stop while the model wrote."""


class Bridge(QObject):
    """Carry events from the worker thread to the window."""

    message = Signal(str, object)
    typing = Signal(str, str)
    # The room, the author, the name and the text so far of a reply that the model still writes.
    partial = Signal(str, str, str, str)
    failed = Signal(str, str)
    notice = Signal(str, str)
    idle = Signal(str)


class Composer(QPlainTextEdit):
    """A text field. Enter sends the text. Shift+Enter starts a new line.

    The field grows with its text, from one line to six.
    """

    submitted = Signal()

    def __init__(self, **kwargs):
        super().__init__(objectName="composer", **kwargs)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self.fit_height)
        self.fit_height()

    def fit_height(self) -> None:
        line = self.fontMetrics().lineSpacing()
        count = int(self.document().size().height())
        lines = max(1, min(6, count))
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if count > 6 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setFixedHeight(lines * line + 16)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class NewRoomDialog(QDialog):
    def __init__(self, identities: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New room")
        self.setMinimumWidth(360)
        self.name = QLineEdit(placeholderText="Late night")
        self.members = QListWidget(objectName="members")
        for identity in identities.values():
            item = QListWidgetItem(identity.display_name)
            item.setData(Qt.ItemDataRole.UserRole, identity.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.members.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Create")
        self.ok.setObjectName("primary")
        self.ok.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.members.itemChanged.connect(lambda _: self.ok.setEnabled(bool(self.selected())))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(8)
        title = QLabel("New room", objectName="cardTitle")
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(QLabel("NAME", objectName="sectionLabel"))
        layout.addWidget(self.name)
        layout.addSpacing(8)
        layout.addWidget(QLabel("MEMBERS", objectName="sectionLabel"))
        if not identities:
            layout.addWidget(QLabel("No identities found. Add a directory to identities/.", objectName="hint"))
        layout.addWidget(self.members)
        layout.addSpacing(6)
        layout.addWidget(buttons)

    def selected(self) -> list[str]:
        return [
            self.members.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.members.count())
            if self.members.item(row).checkState() == Qt.CheckState.Checked
        ]


class MessageView(QScrollArea):
    """Show the messages of a room as bubbles."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget(objectName="messages")
        self.column = QVBoxLayout(body)
        self.column.setContentsMargins(28, 20, 28, 20)
        self.column.setSpacing(5)
        self.column.addStretch(1)
        self.setWidget(body)
        self.last_author: str | None = None
        self.draft: tuple[QWidget, QLabel] | None = None
        # The size of the font in the style sheet. A new label has no parent yet
        # when fit() measures it, so the style sheet does not apply to it then.
        self.font_px = 14
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(lambda _minimum, maximum: bar.setValue(maximum))

    def clear(self) -> None:
        self.draft = None
        while self.column.count() > 1:
            widget = self.column.takeAt(1).widget()
            if widget is not None:
                widget.deleteLater()
        self.last_author = None

    def fit(self, bubble: QLabel, text: str) -> None:
        """Set the text. A label that wraps asks for a small width, so give it the width that its text needs."""
        bubble.setText(text)
        font = bubble.font()
        font.setPixelSize(self.font_px)
        padding = 30
        metrics = QFontMetrics(font)
        single = max((metrics.horizontalAdvance(line) for line in text.splitlines() or [""]), default=0)
        if single + padding <= BUBBLE_WIDTH:
            # The text fits on its lines, so the label needs no wrap. A label that
            # wraps keeps space for a second line that it does not use.
            bubble.setWordWrap(False)
            bubble.setMinimumWidth(single + padding)
        else:
            bubble.setWordWrap(True)
            needed = metrics.boundingRect(0, 0, BUBBLE_WIDTH - padding, 0, Qt.TextFlag.TextWordWrap, text).width()
            bubble.setMinimumWidth(min(BUBBLE_WIDTH, needed + padding))

    def name_row(self, author: str, name: str) -> QWidget:
        """Return the round picture and the name that start a group of messages."""
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 12, 0, 2)
        line.setSpacing(8)
        line.addWidget(avatar(author, name))
        line.addWidget(QLabel(name, objectName="name"))
        line.addStretch(1)
        return row

    def bubble_row(self, text: str, kind: str, mine: bool) -> tuple[QWidget, QLabel]:
        bubble = QLabel(objectName=kind)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(BUBBLE_WIDTH)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.fit(bubble, text)
        row = QWidget()
        line = QHBoxLayout(row)
        # A message of an identity starts under its name, after the round picture.
        line.setContentsMargins(0 if mine else AVATAR_SIZE + 8, 0, 0, 0)
        if mine:
            line.addStretch(1)
        line.addWidget(bubble)
        if not mine:
            line.addStretch(1)
        return row, bubble

    def add(self, message: RoomMessage) -> None:
        self.clear_draft()
        mine = message.author == USER
        if not mine and message.author != self.last_author:
            self.column.addWidget(self.name_row(message.author, message.name))
        elif mine and self.last_author not in (None, USER):
            self.column.addSpacing(10)
        self.last_author = message.author
        row, _ = self.bubble_row(message.text, "mine" if mine else "bubble", mine)
        self.column.addWidget(row)

    def show_draft(self, author: str, name: str, text: str) -> None:
        """Show the reply that the model still writes, in one bubble that grows."""
        if self.draft is None:
            box = QWidget()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            if author != self.last_author:
                layout.addWidget(self.name_row(author, name))
            row, bubble = self.bubble_row(text, "draft", mine=False)
            layout.addWidget(row)
            self.column.addWidget(box)
            self.draft = (box, bubble)
        else:
            self.fit(self.draft[1], text)
        self.draft[1].setVisible(bool(text))

    def clear_draft(self) -> None:
        if self.draft is not None:
            self.column.removeWidget(self.draft[0])
            self.draft[0].deleteLater()
            self.draft = None

    def draft_text(self) -> str | None:
        return None if self.draft is None else self.draft[1].text()

    def set_font_px(self, size: int) -> None:
        """Measure each bubble again after a change of the font size."""
        self.font_px = size
        for label in self.findChildren(QLabel):
            if label.objectName() in ("mine", "bubble", "draft"):
                self.fit(label, label.text())

    def texts(self) -> list[str]:
        return [label.text() for label in self.findChildren(QLabel) if label.objectName() in ("mine", "bubble")]


class MainWindow(QMainWindow):
    def __init__(self, engine: RoomEngine):
        super().__init__()
        self.engine = engine
        self.room: Room | None = None
        self.busy = False
        self.bridge = Bridge()
        self.bridge.message.connect(self.on_message)
        self.bridge.typing.connect(self.on_typing)
        self.bridge.partial.connect(self.on_partial)
        self.bridge.failed.connect(self.on_failed)
        self.bridge.notice.connect(self.on_notice)
        self.stop_event = threading.Event()
        self.bridge.idle.connect(self.on_idle)

        self.setWindowTitle("mimikr")
        self.resize(1080, 720)
        self.setMinimumSize(760, 520)
        self.build()
        self.build_menu()
        self.apply_theme()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self.apply_theme())
        self.reload_rooms()

    # Layout

    def build(self) -> None:
        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_empty_page())
        self.pages.addWidget(self.build_room_page())
        self.pages.addWidget(self.build_settings_page())

        main = QWidget(objectName="main")
        layout = QHBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(main)

    def build_sidebar(self) -> QWidget:
        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(264)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(6)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(0)
        brand.addWidget(QLabel("mimikr", objectName="brand"))
        brand.addWidget(QLabel(".", objectName="brandDot"))
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(10)

        new_room = QPushButton("+  New room", objectName="primary")
        new_room.clicked.connect(self.new_room)
        side.addWidget(new_room)
        side.addSpacing(12)
        rooms_label = QLabel("ROOMS", objectName="sectionLabel")
        rooms_label.setContentsMargins(6, 0, 0, 2)
        side.addWidget(rooms_label)

        self.rooms = QListWidget(objectName="rooms")
        self.rooms.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.rooms.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rooms.currentItemChanged.connect(self.on_room_selected)
        side.addWidget(self.rooms, 1)

        self.identity_errors = QLabel(objectName="error", wordWrap=True)
        self.identity_errors.hide()
        side.addWidget(self.identity_errors)

        self.settings_button = QPushButton("Settings", objectName="ghost", checkable=True)
        self.settings_button.clicked.connect(self.toggle_settings)
        side.addWidget(self.settings_button)
        return sidebar

    def build_empty_page(self) -> QWidget:
        page = QWidget(objectName="page")
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        title = QLabel("mimikr", objectName="emptyTitle", alignment=Qt.AlignmentFlag.AlignCenter)
        text = QLabel("Talk to the people you know, as they write.\nSelect a room on the left, or start a new one.",
                      objectName="emptyText", alignment=Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("+  New room", objectName="primary")
        button.clicked.connect(self.new_room)
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(text)
        layout.addSpacing(18)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)
        return page

    def build_room_page(self) -> QWidget:
        header = QWidget(objectName="header")
        head = QHBoxLayout(header)
        head.setContentsMargins(28, 16, 20, 14)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.title = QLabel(objectName="title")
        self.subtitle = QLabel(objectName="subtitle")
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        head.addLayout(heading, 1)
        delete = QPushButton("Delete room", objectName="danger")
        delete.clicked.connect(self.delete_room)
        head.addWidget(delete, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.view = MessageView()

        self.status = QLabel(objectName="status")
        self.next_button = QPushButton("Next speaker")
        self.next_button.setToolTip("The next member of the room writes a message.")
        self.next_button.clicked.connect(self.next_speaker)
        self.turns = QSpinBox(minimum=1, maximum=200, value=10, suffix=" turns")
        self.turns.setToolTip("The number of messages in an automatic conversation.")
        self.auto_button = QPushButton("Auto")
        self.auto_button.setToolTip("The members talk to each other for the number of turns. Click Stop to end.")
        self.auto_button.clicked.connect(self.auto_or_stop)
        toolbar = QWidget(objectName="toolbar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(8)
        tools.addWidget(self.status, 1)
        tools.addWidget(self.next_button)
        tools.addWidget(self.turns)
        tools.addWidget(self.auto_button)

        self.composer = Composer(placeholderText="Write a message. Enter sends it, and Shift+Enter starts a new line.")
        self.composer.submitted.connect(self.send)
        self.send_button = QPushButton("Send", objectName="primary")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self.send)
        box = QWidget(objectName="composerBox")
        compose = QHBoxLayout(box)
        compose.setContentsMargins(12, 6, 6, 6)
        compose.setSpacing(8)
        compose.addWidget(self.composer, 1)
        compose.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignBottom)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(24, 8, 24, 20)
        bottom.setSpacing(10)
        bottom.addWidget(toolbar)
        bottom.addWidget(box)

        page = QWidget(objectName="page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.view, 1)
        layout.addLayout(bottom)
        return page

    def build_settings_page(self) -> QWidget:
        # The settings page comes in a later step.
        return QWidget(objectName="page")

    def build_menu(self) -> None:
        menu = self.menuBar().addMenu("Room")
        for text, shortcut, slot in (
            ("New room", QKeySequence.StandardKey.New, self.new_room),
            ("Next speaker", QKeySequence("Ctrl+Shift+Return"), self.next_speaker),
            ("Reload identities", QKeySequence.StandardKey.Refresh, self.reload_rooms),
            ("Settings", QKeySequence.StandardKey.Preferences, self.show_settings),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)

    def apply_theme(self) -> None:
        config = self.engine.config
        dark = theme.is_dark(config.theme, system_is_dark())
        self.palette_now = theme.palette(dark, config.accent)
        self.setStyleSheet(theme.stylesheet(self.palette_now, config.font_size))
        self.view.set_font_px(theme.font_size(config.font_size))

    def toggle_settings(self) -> None:
        if self.pages.currentIndex() == SETTINGS_PAGE:
            self.open_room(self.room.id if self.room else None)
        else:
            self.show_settings()

    def show_settings(self) -> None:
        self.settings_button.setChecked(True)
        self.pages.setCurrentIndex(SETTINGS_PAGE)

    # Rooms

    def names(self, members: list[str]) -> str:
        identities, _ = self.engine.identities()
        return ", ".join(identities[m].display_name if m in identities else m for m in members)

    def reload_rooms(self) -> None:
        current = self.room.id if self.room else None
        _, errors = self.engine.identities()
        self.identity_errors.setText("\n".join(f"{name}: {error}" for name, error in errors.items()))
        self.identity_errors.setVisible(bool(errors))
        self.rooms.blockSignals(True)
        self.rooms.clear()
        for room in self.engine.store.list():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, room.id)
            card = self.room_card(room)
            item.setSizeHint(QSize(0, card.sizeHint().height()))
            self.rooms.addItem(item)
            self.rooms.setItemWidget(item, card)
            if room.id == current:
                self.rooms.setCurrentItem(item)
        self.rooms.blockSignals(False)

    def room_card(self, room: Room) -> QWidget:
        """Return the entry of a room in the list: a round picture, the name and the members."""
        card = QWidget()
        card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        line = QHBoxLayout(card)
        line.setContentsMargins(10, 8, 10, 8)
        line.setSpacing(10)
        first = room.members[0] if room.members else room.id
        line.addWidget(avatar(first, self.names([first]) or room.name, 32))
        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel(room.name, objectName="roomTitle")
        members = QLabel(self.names(room.members), objectName="roomMembers")
        for label in (title, members):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(title)
        text.addWidget(members)
        line.addLayout(text, 1)
        return card

    def on_room_selected(self, item: QListWidgetItem | None, _previous=None) -> None:
        self.open_room(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def open_room(self, room_id: str | None) -> None:
        self.settings_button.setChecked(False)
        if room_id is None:
            self.room = None
            self.pages.setCurrentIndex(EMPTY_PAGE)
            return
        self.room = self.engine.store.get(room_id)
        self.title.setText(self.room.name)
        self.subtitle.setText("With " + self.names(self.room.members))
        self.view.clear()
        for message in self.room.messages:
            self.view.add(message)
        self.set_status("")
        self.pages.setCurrentIndex(ROOM_PAGE)
        self.composer.setFocus()

    def select_room(self, room_id: str) -> None:
        self.reload_rooms()
        for row in range(self.rooms.count()):
            if self.rooms.item(row).data(Qt.ItemDataRole.UserRole) == room_id:
                self.rooms.setCurrentRow(row)

    def new_room(self) -> None:
        identities, _ = self.engine.identities()
        dialog = NewRoomDialog(identities, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            room = self.engine.create_room(dialog.name.text(), dialog.selected())
        except EngineError as error:
            QMessageBox.warning(self, "mimikr", str(error))
            return
        self.select_room(room.id)

    def delete_room(self) -> None:
        if self.room is None or self.busy:
            return
        answer = QMessageBox.question(self, "Delete room", f'Delete the room "{self.room.name}"?')
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.engine.store.delete(self.room.id)
        self.room = None
        self.reload_rooms()
        self.open_room(None)

    # Conversation

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setObjectName("error" if error else "status")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setEnabled(not busy)
        self.next_button.setEnabled(not busy)
        self.turns.setEnabled(not busy)
        self.auto_button.setText("Stop" if busy else "Auto")
        self.auto_button.setObjectName("danger" if busy else "")
        self.auto_button.style().unpolish(self.auto_button)
        self.auto_button.style().polish(self.auto_button)

    def send(self) -> None:
        text = self.composer.toPlainText().strip()
        if self.room is None or self.busy or not text:
            return
        self.composer.clear()
        self.view.add(self.engine.post_user_message(self.room, text))
        members = iter(self.room.members)
        self.start(lambda room: next(members, None))

    def next_speaker(self) -> None:
        if self.room is None or self.busy:
            return
        members = iter([self.room.next_speaker()])
        self.start(lambda room: next(members, None))

    def auto_or_stop(self) -> None:
        """Start an automatic conversation, or stop the work that runs."""
        if self.busy:
            self.stop_event.set()
            return
        if self.room is None:
            return
        remaining = [self.turns.value()]

        def next_member(room: Room) -> str | None:
            if remaining[0] == 0:
                return None
            remaining[0] -= 1
            return room.next_speaker()

        self.start(next_member)

    def start(self, next_member: Callable[[Room], str | None]) -> None:
        """Let members write in a worker thread, until next_member gives None or the user stops."""
        room = self.room
        self.stop_event = threading.Event()
        stop = self.stop_event
        self.set_busy(True)
        self.set_status("")

        def work() -> None:
            try:
                while not stop.is_set():
                    member = next_member(room)
                    if member is None:
                        break
                    identities, _ = self.engine.identities()
                    name = identities[member].display_name if member in identities else member
                    self.bridge.typing.emit(room.id, name)

                    def on_text(text: str, member: str = member, name: str = name) -> None:
                        if stop.is_set():
                            raise Stopped
                        self.bridge.partial.emit(room.id, member, name, text)

                    for message in self.engine.speak(room, member, on_text=on_text):
                        self.bridge.message.emit(room.id, message)
                if stop.is_set():
                    raise Stopped
            except Stopped:
                self.bridge.notice.emit(room.id, "Stopped.")
            except (EngineError, LLMError) as error:
                self.bridge.failed.emit(room.id, str(error))
            finally:
                self.bridge.idle.emit(room.id)

        threading.Thread(target=work, daemon=True).start()

    def is_open(self, room_id: str) -> bool:
        return self.room is not None and self.room.id == room_id

    def on_message(self, room_id: str, message: RoomMessage) -> None:
        if self.is_open(room_id):
            self.view.add(message)

    def on_typing(self, room_id: str, name: str) -> None:
        if self.is_open(room_id):
            self.set_status(f"{name} is writing...")

    def on_partial(self, room_id: str, author: str, name: str, text: str) -> None:
        if self.is_open(room_id):
            self.view.show_draft(author, name, text)

    def on_notice(self, room_id: str, text: str) -> None:
        if self.is_open(room_id):
            self.view.clear_draft()
            self.set_status(text)

    def on_failed(self, room_id: str, detail: str) -> None:
        if self.is_open(room_id):
            self.view.clear_draft()
            self.set_status(detail, error=True)

    def on_idle(self, room_id: str) -> None:
        self.set_busy(False)
        if self.is_open(room_id):
            self.view.clear_draft()
            # The worker changed its own copy of the room. Load the saved copy.
            self.room = self.engine.store.get(room_id)
            if self.status.objectName() != "error" and self.status.text() != "Stopped.":
                self.set_status("")


def run(config: Config) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("mimikr")
    chat = ChatClient(config.base_url, config.api_key)
    embedding_client = ChatClient(embedding_base_url(config), config.api_key)

    def embed(texts: list[str]) -> list[list[float]]:
        return embedding_client.embed(texts, config.embedding_model)

    window = MainWindow(RoomEngine(config, chat, embed))
    window.show()
    return application.exec()

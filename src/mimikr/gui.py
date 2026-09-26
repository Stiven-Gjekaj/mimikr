"""The desktop window of mimikr. It uses Qt through PySide6.

The model calls block, so a worker thread runs them.
The worker sends its results to the window through Qt signals.
Only one worker runs at a time.
"""

import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QPalette
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
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mimikr.config import Config, embedding_base_url
from mimikr.engine import EngineError, RoomEngine
from mimikr.llm import ChatClient, LLMError
from mimikr.rooms import USER, Room, RoomMessage

BUBBLE_WIDTH = 520


class Bridge(QObject):
    """Carry events from the worker thread to the window."""

    message = Signal(str, object)
    typing = Signal(str, str)
    failed = Signal(str, str)
    idle = Signal(str)


class Composer(QPlainTextEdit):
    """A text field. Enter sends the text. Shift+Enter starts a new line."""

    submitted = Signal()

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
        self.name = QLineEdit(placeholderText="Room")
        self.members = QListWidget()
        for identity in identities.values():
            item = QListWidgetItem(identity.display_name)
            item.setData(Qt.ItemDataRole.UserRole, identity.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.members.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Create")
        self.ok.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.members.itemChanged.connect(lambda _: self.ok.setEnabled(bool(self.selected())))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name)
        layout.addWidget(QLabel("Members" if identities else "No identities found. Add a directory to identities/."))
        layout.addWidget(self.members)
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
        body = QWidget()
        self.column = QVBoxLayout(body)
        self.column.setContentsMargins(20, 20, 20, 20)
        self.column.setSpacing(4)
        self.column.addStretch(1)
        self.setWidget(body)
        self.last_author: str | None = None
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(lambda _minimum, maximum: bar.setValue(maximum))

    def clear(self) -> None:
        while self.column.count() > 1:
            widget = self.column.takeAt(1).widget()
            if widget is not None:
                widget.deleteLater()
        self.last_author = None

    def add(self, message: RoomMessage) -> None:
        mine = message.author == USER
        if not mine and message.author != self.last_author:
            name = QLabel(message.name, objectName="name")
            self.column.addWidget(name)
        self.last_author = message.author

        bubble = QLabel(message.text, objectName="mine" if mine else "bubble")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(BUBBLE_WIDTH)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # A label that wraps asks for a small width. Give it the width that its text needs.
        padding = 30
        needed = bubble.fontMetrics().boundingRect(
            0, 0, BUBBLE_WIDTH - padding, 0, Qt.TextFlag.TextWordWrap, message.text
        ).width()
        bubble.setMinimumWidth(min(BUBBLE_WIDTH, needed + padding))
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        if mine:
            line.addStretch(1)
        line.addWidget(bubble)
        if not mine:
            line.addStretch(1)
        self.column.addWidget(row)

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
        self.bridge.failed.connect(self.on_failed)
        self.bridge.idle.connect(self.on_idle)

        self.setWindowTitle("mimikr")
        self.resize(980, 680)
        self.build()
        self.build_menu()
        self.reload_rooms()

    # Layout

    def build(self) -> None:
        self.rooms = QListWidget()
        self.rooms.currentItemChanged.connect(self.on_room_selected)
        new_room = QPushButton("New room")
        new_room.clicked.connect(self.new_room)
        self.identity_errors = QLabel(objectName="error", wordWrap=True)
        self.identity_errors.hide()
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.addWidget(new_room)
        side.addWidget(self.rooms, 1)
        side.addWidget(self.identity_errors)

        self.title = QLabel(objectName="title")
        self.subtitle = QLabel(objectName="subtitle")
        delete = QPushButton("Delete room")
        delete.clicked.connect(self.delete_room)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading, 1)
        header.addWidget(delete)

        self.view = MessageView()
        self.status = QLabel(objectName="status")
        self.composer = Composer(placeholderText="Write a message. Press Enter to send.")
        self.composer.setFixedHeight(64)
        self.composer.submitted.connect(self.send)
        self.send_button = QPushButton("Send")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self.send)
        self.next_button = QPushButton("Next speaker")
        self.next_button.setToolTip("The next member of the room writes a message.")
        self.next_button.clicked.connect(self.next_speaker)
        controls = QHBoxLayout()
        controls.addWidget(self.composer, 1)
        buttons = QVBoxLayout()
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.next_button)
        controls.addLayout(buttons)

        room_page = QWidget()
        room_layout = QVBoxLayout(room_page)
        room_layout.addLayout(header)
        room_layout.addWidget(self.view, 1)
        room_layout.addWidget(self.status)
        room_layout.addLayout(controls)

        empty = QLabel("Select a room or make a new room.", alignment=Qt.AlignmentFlag.AlignCenter)
        self.pages = QStackedWidget()
        self.pages.addWidget(empty)
        self.pages.addWidget(room_page)

        splitter = QSplitter()
        splitter.addWidget(sidebar)
        splitter.addWidget(self.pages)
        splitter.setSizes([240, 740])
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)
        self.apply_style()

    def build_menu(self) -> None:
        menu = self.menuBar().addMenu("Room")
        for text, shortcut, slot in (
            ("New room", QKeySequence.StandardKey.New, self.new_room),
            ("Next speaker", QKeySequence("Ctrl+Shift+Return"), self.next_speaker),
            ("Reload identities", QKeySequence.StandardKey.Refresh, self.reload_rooms),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)

    def apply_style(self) -> None:
        palette = self.palette()
        accent = palette.color(QPalette.ColorRole.Highlight).name()
        accent_text = palette.color(QPalette.ColorRole.HighlightedText).name()
        bubble = palette.color(QPalette.ColorRole.AlternateBase).name()
        muted = palette.color(QPalette.ColorRole.PlaceholderText).name()
        self.setStyleSheet(f"""
            QLabel#bubble {{ background: {bubble}; border-radius: 12px; padding: 7px 11px; }}
            QLabel#mine {{ background: {accent}; color: {accent_text}; border-radius: 12px; padding: 7px 11px; }}
            QLabel#name, QLabel#subtitle, QLabel#status {{ color: {muted}; font-size: 12px; }}
            QLabel#name {{ margin: 6px 4px 0 4px; }}
            QLabel#title {{ font-size: 16px; font-weight: 600; }}
            QLabel#error {{ color: #d9534f; }}
        """)

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
            item = QListWidgetItem(f"{room.name}\n{self.names(room.members)}")
            item.setData(Qt.ItemDataRole.UserRole, room.id)
            self.rooms.addItem(item)
            if room.id == current:
                self.rooms.setCurrentItem(item)
        self.rooms.blockSignals(False)

    def on_room_selected(self, item: QListWidgetItem | None, _previous=None) -> None:
        self.open_room(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def open_room(self, room_id: str | None) -> None:
        if room_id is None:
            self.room = None
            self.pages.setCurrentIndex(0)
            return
        self.room = self.engine.store.get(room_id)
        self.title.setText(self.room.name)
        self.subtitle.setText("With " + self.names(self.room.members))
        self.view.clear()
        for message in self.room.messages:
            self.view.add(message)
        self.set_status("")
        self.pages.setCurrentIndex(1)
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
        self.status.setStyleSheet("color: #d9534f;" if error else "")

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setEnabled(not busy)
        self.next_button.setEnabled(not busy)

    def send(self) -> None:
        text = self.composer.toPlainText().strip()
        if self.room is None or self.busy or not text:
            return
        self.composer.clear()
        self.view.add(self.engine.post_user_message(self.room, text))
        self.start(self.room.members)

    def next_speaker(self) -> None:
        if self.room is None or self.busy:
            return
        self.start([self.room.next_speaker()])

    def start(self, members: list[str]) -> None:
        """Let the members write in order, in a worker thread."""
        room = self.room
        self.set_busy(True)
        self.set_status("")

        def work() -> None:
            try:
                for member in members:
                    identities, _ = self.engine.identities()
                    name = identities[member].display_name if member in identities else member
                    self.bridge.typing.emit(room.id, name)
                    for message in self.engine.speak(room, member):
                        self.bridge.message.emit(room.id, message)
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

    def on_failed(self, room_id: str, detail: str) -> None:
        if self.is_open(room_id):
            self.set_status(detail, error=True)

    def on_idle(self, room_id: str) -> None:
        self.set_busy(False)
        if self.is_open(room_id):
            # The worker changed its own copy of the room. Load the saved copy.
            self.room = self.engine.store.get(room_id)
            if not self.status.styleSheet():
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

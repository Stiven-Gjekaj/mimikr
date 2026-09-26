"""The desktop window of mimikr. It uses Qt through PySide6.

The model calls block, so a worker thread runs them.
The worker sends its results to the window through Qt signals.
Only one worker runs at a time.
"""

import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import fields, replace
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
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
from mimikr.avatars import AvatarStore
from mimikr.config import Config, config_file, embedding_base_url, sampling, save_config
from mimikr import editing
from mimikr.engine import EngineError, RoomEngine
from mimikr.identity import IdentityError, load_identity
from mimikr.importers import ExportError, read_export
from mimikr.transcript import TranscriptError, parse_transcript
from mimikr.export import file_name, room_as_text
from mimikr.llm import ChatClient, LLMError
from mimikr.local_servers import LocalServer, ServerError, find_llama_server
from mimikr.rooms import USER, Room, RoomMessage, matches, quote_of, search_rooms
from mimikr.servers import check_servers

BUBBLE_WIDTH = 520
AVATAR_SIZE = 28
# The pages of the main area.
EMPTY_PAGE, ROOM_PAGE, SETTINGS_PAGE, IDENTITIES_PAGE = 0, 1, 2, 3


_round_pictures: dict[tuple[str, float, int, float], QPixmap] = {}


def round_picture(path: Path, size: int, ratio: float = 2.0) -> QPixmap | None:
    """Return the picture cut to a circle of the size, or None if the file is not a picture.

    The middle square of the picture fills the circle. The result stays in a
    cache until the file changes.
    """
    try:
        key = (str(path), path.stat().st_mtime, size, ratio)
    except OSError:
        return None
    if key in _round_pictures:
        return _round_pictures[key]
    image = QImage(str(path))
    if image.isNull():
        return None
    pixels = round(size * ratio)
    side = min(image.width(), image.height())
    square = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
    square = square.scaled(pixels, pixels, Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(pixels, pixels)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    circle = QPainterPath()
    circle.addEllipse(0, 0, pixels, pixels)
    painter.setClipPath(circle)
    painter.drawImage(0, 0, square)
    painter.end()
    result.setDevicePixelRatio(ratio)
    _round_pictures[key] = result
    return result


def detach(widget: QWidget | None) -> None:
    """Take the widget out of the window now, and delete it later.

    deleteLater alone keeps the widget as a child until the event loop runs, so
    a search of the children would still find it.
    """
    if widget is not None:
        widget.setParent(None)
        widget.deleteLater()


PICTURE_SIZE = 256
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


def save_picture(source: Path, target: Path) -> None:
    """Cut the middle square of the image, make it 256 pixels wide, and write it as PNG.

    Raise ValueError if the file is not an image.
    """
    image = QImage(str(source))
    if image.isNull():
        raise ValueError(f"{source.name} is not an image that mimikr can read")
    side = min(image.width(), image.height())
    square = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
    square = square.scaled(PICTURE_SIZE, PICTURE_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not square.save(str(target), "PNG"):
        raise ValueError(f"cannot write {target}")


def avatar(key: str, name: str, size: int = AVATAR_SIZE, picture: Path | None = None) -> QLabel:
    """Return a round picture. With no picture file, show the initials of the name in the color of the key."""
    label = QLabel(objectName="avatar", alignment=Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(size, size)
    pixmap = round_picture(picture, size) if picture else None
    if pixmap is not None:
        label.setPixmap(pixmap)
        label.setStyleSheet("background: transparent;")
    else:
        label.setText(theme.initials(name))
        label.setStyleSheet(f"background: {theme.avatar_color(key)}; border-radius: {size // 2}px;")
    return label


def system_is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def typing_seconds(text: str) -> float:
    """Return about how long a person takes to write the text on a phone."""
    return min(0.6 + 0.035 * len(text), 5.0)


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
    # The result of a start of the local servers: an error, or an empty text.
    servers = Signal(str)


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
        self.topic = QLineEdit(placeholderText="Optional. For example: the new chapter of Soultale is out")
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
        layout.addWidget(QLabel("TOPIC", objectName="sectionLabel"))
        layout.addWidget(self.topic)
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

    # The id of a message, and the place on the screen, when the user asks for its menu.
    menu_requested = Signal(str, object)

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
        # The window sets this to find the picture of an author.
        self.picture_for: Callable[[str], Path | None] = lambda author: None
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(lambda _minimum, maximum: bar.setValue(maximum))

    def clear(self) -> None:
        self.draft = None
        while self.column.count() > 1:
            detach(self.column.takeAt(1).widget())
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
        line.addWidget(avatar(author, name, picture=self.picture_for(author)))
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

    def add(self, message: RoomMessage, quote: str | None = None) -> None:
        self.clear_draft()
        mine = message.author == USER
        if not mine and message.author != self.last_author:
            self.column.addWidget(self.name_row(message.author, message.name))
        elif mine and self.last_author not in (None, USER):
            self.column.addSpacing(10)
        self.last_author = message.author
        if quote:
            label = QLabel(f"Reply to {quote}", objectName="replyQuote")
            label.setTextFormat(Qt.TextFormat.PlainText)
            line = QHBoxLayout()
            line.setContentsMargins(0 if mine else AVATAR_SIZE + 8, 4, 0, 0)
            if mine:
                line.addStretch(1)
            line.addWidget(label)
            if not mine:
                line.addStretch(1)
            holder = QWidget()
            holder.setLayout(line)
            self.column.addWidget(holder)
        row, bubble = self.bubble_row(message.text, "mine" if mine else "bubble", mine)
        bubble.setProperty("message_id", message.id)
        bubble.setProperty("liked", message.liked)
        bubble.setToolTip("You liked this reply." if message.liked else "")
        bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bubble.customContextMenuRequested.connect(
            lambda point, bubble=bubble: self.menu_requested.emit(
                bubble.property("message_id"), bubble.mapToGlobal(point)))
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

    def bubble(self, message_id: str) -> QLabel | None:
        for label in self.findChildren(QLabel):
            if label.property("message_id") == message_id:
                return label
        return None

    def texts(self) -> list[str]:
        return [label.text() for label in self.findChildren(QLabel) if label.objectName() in ("mine", "bubble")]


class SettingsPage(QScrollArea):
    """Edit the settings. A change of the look shows at once. Save writes mimikr.toml."""

    # The window applies the look of the settings on the page, before they are saved.
    look_changed = Signal()
    saved = Signal()
    # The lines of a connection check, from its worker thread.
    checked = Signal(object)

    def __init__(self, config: Config, checker: Callable[[Config], list[tuple[bool, str]]] = check_servers):
        super().__init__()
        self.config = config
        self.checker = checker
        self.checked.connect(self.show_check)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget(objectName="page")
        column = QVBoxLayout(body)
        column.setContentsMargins(32, 28, 32, 28)
        column.setSpacing(18)
        title = QLabel("Settings", objectName="title")
        column.addWidget(title)

        # Appearance.
        self.theme = QComboBox()
        self.theme.addItems(["System", "Light", "Dark"])
        self.swatches: dict[str, QPushButton] = {}
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        for name, color in theme.ACCENTS.items():
            button = QPushButton(objectName="swatch", checkable=True, toolTip=name.capitalize())
            button.setFixedSize(28, 28)
            button.setStyleSheet(
                f"QPushButton#swatch {{ background: {color}; border-radius: 14px; border: 3px solid {color}; }}"
                f"QPushButton#swatch:checked {{ border: 3px solid #9ca3af; }}"
            )
            button.clicked.connect(lambda _checked, name=name: self.choose_accent(name))
            self.swatches[name] = button
            swatch_row.addWidget(button)
        self.custom_accent = QLineEdit(placeholderText="#rrggbb")
        self.custom_accent.setMaximumWidth(110)
        self.custom_accent.editingFinished.connect(self.choose_custom_accent)
        swatch_row.addSpacing(6)
        swatch_row.addWidget(self.custom_accent)
        swatch_row.addStretch(1)
        self.accent_error = QLabel(objectName="error")
        self.accent_error.hide()
        self.font_size = QSpinBox(minimum=theme.FONT_SIZES.start, maximum=theme.FONT_SIZES.stop - 1, suffix=" px")
        appearance = self.card("Appearance", "How the window looks. The change shows at once.")
        form = self.form(appearance)
        form.addRow(self.label("Theme"), self.theme)
        accent_cell = QVBoxLayout()
        accent_cell.setSpacing(4)
        accent_cell.addLayout(swatch_row)
        accent_cell.addWidget(self.accent_error)
        form.addRow(self.label("Accent"), accent_cell)
        form.addRow(self.label("Text size"), self.font_size)
        column.addWidget(appearance)

        # Model server.
        self.base_url = QLineEdit(placeholderText="http://localhost:11434/v1")
        self.model = QLineEdit(placeholderText="llama3.1")
        self.api_key = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.embedding_url = QLineEdit(placeholderText="Empty: the chat server")
        self.embedding_model = QLineEdit(placeholderText="nomic-embed-text")
        server = self.card("Model server", "Any server with the OpenAI API: Ollama, LM Studio or llama.cpp.")
        form = self.form(server)
        form.addRow(self.label("Chat server"), self.base_url)
        form.addRow(self.label("Chat model"), self.model)
        form.addRow(self.label("API key"), self.api_key)
        form.addRow(self.label("Embedding server"), self.embedding_url)
        form.addRow(self.label("Embedding model"), self.embedding_model)
        self.check_button = QPushButton("Test connection")
        self.check_button.clicked.connect(self.check)
        self.check_result = QLabel(objectName="hint", wordWrap=True)
        self.check_result.setTextFormat(Qt.TextFormat.PlainText)
        check_row = QHBoxLayout()
        check_row.addWidget(self.check_button, alignment=Qt.AlignmentFlag.AlignTop)
        check_row.addWidget(self.check_result, 1)
        form.addRow(self.label(""), check_row)
        column.addWidget(server)

        local = self.card("Local llama.cpp", "mimikr can start llama-server for you: one server for the chat model "
                                             "and one for the embedding model.")
        form = self.form(local)
        self.llama_server = QLineEdit(placeholderText=find_llama_server() or "The path of llama-server")
        self.chat_gguf = QLineEdit(placeholderText="A .gguf file")
        self.embedding_gguf = QLineEdit(placeholderText="A .gguf file")
        self.chat_port = QSpinBox(minimum=1024, maximum=65535)
        self.embedding_port = QSpinBox(minimum=1024, maximum=65535)
        self.context_size = QSpinBox(minimum=1024, maximum=131072, singleStep=1024)
        self.start_servers = QCheckBox("Start the servers when mimikr opens")
        form.addRow(self.label("llama-server"), self.llama_server)
        form.addRow(self.label("Chat model file"), self.file_row(self.chat_gguf))
        form.addRow(self.label("Embedding file"), self.file_row(self.embedding_gguf))
        ports = QHBoxLayout()
        ports.addWidget(self.chat_port)
        ports.addWidget(QLabel("chat", objectName="hint"))
        ports.addSpacing(12)
        ports.addWidget(self.embedding_port)
        ports.addWidget(QLabel("embeddings", objectName="hint"))
        ports.addStretch(1)
        form.addRow(self.label("Ports"), ports)
        form.addRow(self.label("Context"), self.context_size)
        form.addRow(self.label(""), self.start_servers)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.server_status = QLabel(objectName="hint", wordWrap=True)
        self.server_status.setTextFormat(Qt.TextFormat.PlainText)
        controls = QHBoxLayout()
        controls.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignTop)
        controls.addWidget(self.stop_button, alignment=Qt.AlignmentFlag.AlignTop)
        controls.addWidget(self.server_status, 1)
        form.addRow(self.label(""), controls)
        column.addWidget(local)

        # Replies.
        self.mode = QComboBox()
        self.mode.addItem("Chat: an instruct model answers", "chat")
        self.mode.addItem("Continue: the model continues a chat log", "continue")
        self.examples = QComboBox()
        self.examples.addItem("Recent: the end of the transcript", "recent")
        self.examples.addItem("Similar: the most similar exchanges", "similar")
        self.temperature = QDoubleSpinBox(minimum=0.0, maximum=2.0, singleStep=0.05, decimals=2)
        # A point, and not the comma of some locales, as in mimikr.toml.
        self.temperature.setLocale(QLocale.c())
        replies = self.card("Replies", "An identity can set its own model, temperature and mode in identity.toml.")
        form = self.form(replies)
        form.addRow(self.label("Mode"), self.mode)
        form.addRow(self.label("Examples"), self.examples)
        form.addRow(self.label("Temperature"), self.temperature)
        self.turn_taking = QComboBox()
        self.turn_taking.addItem("Smart: the member that is named, or a random one", "smart")
        self.turn_taking.addItem("Rotate: the order of the room", "rotate")
        form.addRow(self.label("Next speaker"), self.turn_taking)
        self.enforce_style = QCheckBox("Remove capitals, periods and emoji that the person never uses")
        form.addRow(self.label("Match the habits"), self.enforce_style)
        self.realistic_timing = QCheckBox("Wait about the time that a person takes to write each message")
        form.addRow(self.label("Realistic timing"), self.realistic_timing)
        column.addWidget(replies)

        pictures = self.card("Pictures", "A picture for each identity. The change shows at once, with no Save. "
                                                "mimikr keeps a copy in data/avatars/.")
        self.pictures = QVBoxLayout()
        self.pictures.setSpacing(8)
        pictures.layout().addLayout(self.pictures)
        column.addWidget(pictures)

        self.note = QLabel(objectName="hint", wordWrap=True)
        self.save_button = QPushButton("Save", objectName="primary")
        self.save_button.clicked.connect(self.save)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert)
        actions = QHBoxLayout()
        actions.addWidget(self.note, 1)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.save_button)
        column.addLayout(actions)
        column.addStretch(1)
        self.setWidget(body)

        self.accent = config.accent
        self.saved_config = replace(config)
        self.load(config)
        self.theme.currentIndexChanged.connect(self.preview)
        self.font_size.valueChanged.connect(self.preview)

    @staticmethod
    def card(title: str, hint: str) -> QWidget:
        card = QWidget(objectName="card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title, objectName="cardTitle"))
        layout.addWidget(QLabel(hint, objectName="hint", wordWrap=True))
        layout.addSpacing(10)
        return card

    # Ask the user for a model file. A test puts a function here that gives a path.
    pick_model: Callable[[], Path | None] | None = None

    def file_row(self, field: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(field, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self.browse_model(field))
        row.addWidget(browse)
        return row

    def browse_model(self, field: QLineEdit) -> None:
        if self.pick_model is not None:
            path = self.pick_model()
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Choose a model", str(Path.home() / "Models"),
                                                    "GGUF models (*.gguf)")
            path = Path(chosen) if chosen else None
        if path is not None:
            field.setText(str(path))

    @staticmethod
    def label(text: str) -> QLabel:
        """Return a label of one width, so that the fields of all cards start at one line."""
        label = QLabel(text, objectName="formLabel")
        label.setFixedWidth(150)
        return label

    @staticmethod
    def form(card: QWidget) -> QFormLayout:
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        card.layout().addLayout(form)
        return form

    def load(self, config: Config) -> None:
        """Show the values of the config on the page."""
        for widget in (self.theme, self.font_size):
            widget.blockSignals(True)
        self.theme.setCurrentIndex(max(0, theme.THEMES.index(config.theme)) if config.theme in theme.THEMES else 0)
        self.font_size.setValue(theme.font_size(config.font_size))
        for widget in (self.theme, self.font_size):
            widget.blockSignals(False)
        self.accent = config.accent
        self.custom_accent.setText("" if config.accent in theme.ACCENTS else config.accent)
        self.mark_accent()
        self.base_url.setText(config.base_url)
        self.model.setText(config.model)
        self.api_key.setText(config.api_key)
        self.embedding_url.setText(config.embedding_url)
        self.embedding_model.setText(config.embedding_model)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.mode)))
        self.examples.setCurrentIndex(max(0, self.examples.findData(config.examples)))
        self.temperature.setValue(config.temperature)
        self.llama_server.setText(config.llama_server)
        self.chat_gguf.setText(config.chat_gguf)
        self.embedding_gguf.setText(config.embedding_gguf)
        self.chat_port.setValue(config.chat_port)
        self.embedding_port.setValue(config.embedding_port)
        self.context_size.setValue(config.context_size)
        self.start_servers.setChecked(config.start_servers)
        self.turn_taking.setCurrentIndex(max(0, self.turn_taking.findData(config.turn_taking)))
        self.enforce_style.setChecked(config.enforce_style)
        self.realistic_timing.setChecked(config.realistic_timing)
        self.accent_error.setText("")
        self.accent_error.hide()

    def mark_accent(self) -> None:
        for name, button in self.swatches.items():
            button.setChecked(name == self.accent)

    def choose_accent(self, name: str) -> None:
        self.accent = name
        self.custom_accent.setText("")
        self.accent_error.setText("")
        self.accent_error.hide()
        self.mark_accent()
        self.preview()

    def choose_custom_accent(self) -> None:
        text = self.custom_accent.text().strip()
        if not text:
            return
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            self.accent_error.setText("Write a color as # and six hex digits, for example #ff8800.")
            self.accent_error.show()
            return
        self.accent_error.setText("")
        self.accent_error.hide()
        self.accent = text.lower()
        self.mark_accent()
        self.preview()

    def apply_look(self, config: Config) -> None:
        config.theme = theme.THEMES[self.theme.currentIndex()]
        config.accent = self.accent
        config.font_size = self.font_size.value()

    def preview(self) -> None:
        self.apply_look(self.config)
        self.look_changed.emit()

    def apply_server(self, config: Config) -> None:
        config.base_url = self.base_url.text().strip() or Config.base_url
        config.model = self.model.text().strip() or Config.model
        config.api_key = self.api_key.text() or Config.api_key
        config.embedding_url = self.embedding_url.text().strip()
        config.embedding_model = self.embedding_model.text().strip() or Config.embedding_model

    def apply_local(self, config: Config) -> None:
        config.llama_server = self.llama_server.text().strip()
        config.chat_gguf = self.chat_gguf.text().strip()
        config.embedding_gguf = self.embedding_gguf.text().strip()
        config.chat_port = self.chat_port.value()
        config.embedding_port = self.embedding_port.value()
        config.context_size = self.context_size.value()
        config.start_servers = self.start_servers.isChecked()

    def check(self) -> None:
        """Check the servers in the fields, before a save, in a worker thread."""
        trial = replace(self.config)
        self.apply_server(trial)
        self.check_button.setEnabled(False)
        self.check_result.setText("Checking...")
        threading.Thread(target=lambda: self.checked.emit(self.checker(trial)), daemon=True).start()

    def show_check(self, lines: list[tuple[bool, str]]) -> None:
        self.check_button.setEnabled(True)
        self.check_result.setText("\n".join(f"{'OK' if ok else 'Fault'}: {text}" for ok, text in lines))

    def save(self) -> None:
        config = self.config
        self.apply_look(config)
        self.apply_server(config)
        self.apply_local(config)
        config.mode = self.mode.currentData()
        config.examples = self.examples.currentData()
        config.temperature = round(self.temperature.value(), 2)
        config.turn_taking = self.turn_taking.currentData()
        config.enforce_style = self.enforce_style.isChecked()
        config.realistic_timing = self.realistic_timing.isChecked()
        self.saved_config = replace(config)
        self.load(config)
        self.saved.emit()

    def revert(self) -> None:
        """Go back to the saved settings, and show the saved look again."""
        for item in fields(Config):
            setattr(self.config, item.name, getattr(self.saved_config, item.name))
        self.load(self.config)
        self.note.setText("")
        self.look_changed.emit()


class DropArea(QWidget):
    """A page that takes a file that the user drops on it."""

    dropped = Signal(object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.dropped.emit(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return


class MainWindow(QMainWindow):
    def __init__(self, engine: RoomEngine, config_path: Path | None = None,
                 reconnect: Callable[[Config], None] | None = None):
        super().__init__()
        self.local_servers: list[LocalServer] = []
        self.engine = engine
        self.avatars = AvatarStore(engine.config.data_dir, engine.config.identities_dir)
        self.config_path = config_path or config_file()
        # The window calls this after a save, so that new server settings take effect.
        self.reconnect = reconnect
        # Ask the user for an image file. A test puts a function here that gives a path.
        self.pick_image: Callable[[], Path | None] = self.ask_for_image
        # Ask the user for the name of a new identity.
        self.ask_name: Callable[[], str | None] = self.ask_for_name
        # Ask the user which name in an export is the person. It gets "name (count)" labels.
        self.pick_speaker: Callable[[list[str], int], int | None] = self.ask_for_speaker
        # Ask the user a question with yes or no.
        self.confirm: Callable[[str], bool] = self.ask_to_confirm
        # Ask the user for a chat export to import.
        self.pick_export: Callable[[], Path | None] = self.ask_for_export
        # Ask the user for the topic of a room. It gets the old topic.
        self.ask_topic: Callable[[str], str | None] = self.ask_for_topic
        # Ask the user for the new text of a message. It gets the old text.
        self.ask_text: Callable[[str], str | None] = self.ask_for_text
        # Ask the user where to save an export. It gets a suggested name.
        self.pick_save_path: Callable[[str], Path | None] = self.ask_for_save_path
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
        self.bridge.servers.connect(self.on_servers)

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
        self.pages.addWidget(self.build_identities_page())

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
        self.search = QLineEdit(placeholderText="Search rooms and messages")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self.reload_rooms())
        side.addWidget(self.search)
        side.addSpacing(6)
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

        self.identities_button = QPushButton("Identities", objectName="ghost", checkable=True)
        self.identities_button.clicked.connect(self.toggle_identities)
        side.addWidget(self.identities_button)
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
        self.room_picture = QPushButton(objectName="ghost", toolTip="Change the picture of the room")
        self.room_picture.setFixedSize(44, 44)
        self.room_picture.setStyleSheet("QPushButton#ghost { padding: 0; border-radius: 22px; }")
        self.room_picture.clicked.connect(self.room_picture_menu)
        self.room_picture_holder = QHBoxLayout(self.room_picture)
        self.room_picture_holder.setContentsMargins(4, 4, 4, 4)
        head.addWidget(self.room_picture)
        head.addSpacing(8)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.title = QLabel(objectName="title")
        self.subtitle = QLabel(objectName="subtitle")
        self.topic_label = QLabel(objectName="subtitle", wordWrap=True)
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        heading.addWidget(self.topic_label)
        head.addLayout(heading, 1)
        self.topic_button = QPushButton("Topic...")
        self.topic_button.setToolTip("What happens in the room now. The identities know it.")
        self.topic_button.clicked.connect(self.change_topic)
        head.addWidget(self.topic_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        head.addSpacing(6)
        self.export_button = QPushButton("Export")
        self.export_button.setToolTip("Save the room as a text file, or copy it as text")
        self.export_button.clicked.connect(self.export_menu)
        head.addWidget(self.export_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        head.addSpacing(6)
        delete = QPushButton("Delete room", objectName="danger")
        delete.clicked.connect(self.delete_room)
        head.addWidget(delete, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.view = MessageView()
        self.view.menu_requested.connect(self.message_menu)
        self.view.picture_for = lambda author: self.avatars.find("identity", author)

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

        self.reply_bar = QWidget(objectName="replyBar")
        reply_line = QHBoxLayout(self.reply_bar)
        reply_line.setContentsMargins(12, 6, 6, 6)
        self.reply_label = QLabel(objectName="replyQuote")
        self.reply_label.setTextFormat(Qt.TextFormat.PlainText)
        cancel_reply = QPushButton("Cancel", objectName="ghost")
        cancel_reply.clicked.connect(lambda: self.set_reply(None))
        reply_line.addWidget(self.reply_label, 1)
        reply_line.addWidget(cancel_reply)
        self.reply_bar.hide()
        self.replying_to: str | None = None

        bottom = QVBoxLayout()
        bottom.setContentsMargins(24, 8, 24, 20)
        bottom.setSpacing(10)
        bottom.addWidget(toolbar)
        bottom.addWidget(self.reply_bar)
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
        self.settings = SettingsPage(self.engine.config)
        self.settings.start_button.clicked.connect(self.start_local_servers)
        self.settings.stop_button.clicked.connect(self.stop_local_servers)
        self.settings.stop_button.setEnabled(False)
        self.settings.look_changed.connect(self.apply_theme)
        self.settings.saved.connect(self.save_settings)
        return self.settings

    def save_settings(self) -> None:
        try:
            save_config(self.engine.config, self.config_path)
        except OSError as error:
            self.settings.note.setText(f"Cannot write {self.config_path}: {error.strerror}")
            return
        if self.reconnect:
            self.reconnect(self.engine.config)
        self.apply_theme()
        self.settings.note.setText(f"Saved to {self.config_path}. An environment variable has priority at the next start.")

    def build_menu(self) -> None:
        menu = self.menuBar().addMenu("Room")
        for text, shortcut, slot in (
            ("New room", QKeySequence.StandardKey.New, self.new_room),
            ("Next speaker", QKeySequence("Ctrl+Shift+Return"), self.next_speaker),
            ("Reload identities", QKeySequence.StandardKey.Refresh, self.reload_rooms),
            ("Export as text file...", QKeySequence("Ctrl+E"), self.export_to_file),
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

    def toggle_identities(self) -> None:
        if self.pages.currentIndex() == IDENTITIES_PAGE:
            self.open_room(self.room.id if self.room else None)
        else:
            self.show_identities()

    def show_identities(self, select: str | None = None) -> None:
        self.settings_button.setChecked(False)
        self.identities_button.setChecked(True)
        self.refresh_identities(select)
        self.pages.setCurrentIndex(IDENTITIES_PAGE)

    def show_settings(self) -> None:
        self.identities_button.setChecked(False)
        self.settings_button.setChecked(True)
        self.refresh_pictures()
        self.pages.setCurrentIndex(SETTINGS_PAGE)

    # Identities

    def build_identities_page(self) -> QWidget:
        page = DropArea(objectName="page")
        page.dropped.connect(lambda path: self.import_chat(self.editing_id, path) if self.editing_id else None)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(QLabel("Identities", objectName="title"))
        self.identity_list = QListWidget(objectName="rooms")
        self.identity_list.setFixedWidth(240)
        self.identity_list.currentItemChanged.connect(
            lambda item, _previous: self.edit_identity(item.data(Qt.ItemDataRole.UserRole) if item else None))
        left.addWidget(self.identity_list, 1)
        new_identity = QPushButton("+  New identity", objectName="primary")
        new_identity.clicked.connect(self.new_identity)
        left.addWidget(new_identity)
        outer.addLayout(left)

        editor = QScrollArea()
        editor.setWidgetResizable(True)
        editor.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget(objectName="page")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(18)

        profile = SettingsPage.card("Profile", "The files of this identity. Save writes them.")
        form = SettingsPage.form(profile)
        self.edit_name = QLineEdit()
        self.edit_speaker = QComboBox()
        self.edit_personality = QPlainTextEdit()
        self.edit_personality.setMinimumHeight(150)
        self.edit_model = QLineEdit(placeholderText="The model in the settings")
        self.edit_temperature = QLineEdit(placeholderText="The temperature in the settings")
        self.edit_mode = QComboBox()
        self.edit_mode.addItem("The mode in the settings", "")
        self.edit_mode.addItem("Chat", "chat")
        self.edit_mode.addItem("Continue", "continue")
        form.addRow(SettingsPage.label("Name"), self.edit_name)
        form.addRow(SettingsPage.label("Name in chat.md"), self.edit_speaker)
        form.addRow(SettingsPage.label("Personality"), self.edit_personality)
        form.addRow(SettingsPage.label("Model"), self.edit_model)
        form.addRow(SettingsPage.label("Temperature"), self.edit_temperature)
        form.addRow(SettingsPage.label("Mode"), self.edit_mode)
        self.identity_note = QLabel(objectName="hint", wordWrap=True)
        save = QPushButton("Save", objectName="primary")
        save.clicked.connect(self.save_identity)
        actions = QHBoxLayout()
        actions.addWidget(self.identity_note, 1)
        actions.addWidget(save)
        profile.layout().addSpacing(8)
        profile.layout().addLayout(actions)
        column.addWidget(profile)

        chat = SettingsPage.card("Chat", "Import an export of WhatsApp, Telegram Desktop or DiscordChatExporter, "
                                         "or a chat.md file. You can also drop the file on this page.")
        self.chat_summary = QLabel(objectName="hint", wordWrap=True)
        self.chat_summary.setTextFormat(Qt.TextFormat.PlainText)
        chat.layout().addWidget(self.chat_summary)
        import_button = QPushButton("Import a chat...")
        import_button.clicked.connect(lambda: self.import_chat(self.editing_id) if self.editing_id else None)
        chat.layout().addSpacing(6)
        chat.layout().addWidget(import_button, alignment=Qt.AlignmentFlag.AlignLeft)
        column.addWidget(chat)

        lore = SettingsPage.card("Group lore", "What the whole group knows: who is who, running jokes, what "
                                               "happened. Each identity reads it. It stays in identities/lore.md.")
        self.lore_editor = QPlainTextEdit()
        self.lore_editor.setMinimumHeight(120)
        self.lore_editor.setPlaceholderText("For example: Stiven writes Soultale. Jackie lives in Belgium.")
        self.lore_note = QLabel(objectName="hint")
        save_lore = QPushButton("Save lore", objectName="primary")
        save_lore.clicked.connect(self.save_lore)
        lore_actions = QHBoxLayout()
        lore_actions.addWidget(self.lore_note, 1)
        lore_actions.addWidget(save_lore)
        lore.layout().addWidget(self.lore_editor)
        lore.layout().addSpacing(6)
        lore.layout().addLayout(lore_actions)
        column.addWidget(lore)
        column.addStretch(1)
        editor.setWidget(body)
        self.identity_editor = editor
        outer.addWidget(editor, 1)
        self.editing_id: str | None = None
        return page

    def refresh_identities(self, select: str | None = None) -> None:
        select = select or self.editing_id
        self.lore_editor.setPlainText(self.engine.lore())
        self.lore_note.setText("")
        identities, errors = self.engine.identities()
        self.identity_list.blockSignals(True)
        self.identity_list.clear()
        chosen = None
        for identity in identities.values():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, identity.id)
            card = QWidget()
            card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            line = QHBoxLayout(card)
            line.setContentsMargins(10, 8, 10, 8)
            line.setSpacing(10)
            line.addWidget(avatar(identity.id, identity.display_name, 32, self.avatars.find("identity", identity.id)))
            line.addWidget(QLabel(identity.display_name, objectName="roomTitle"), 1)
            item.setSizeHint(QSize(0, card.sizeHint().height()))
            self.identity_list.addItem(item)
            self.identity_list.setItemWidget(item, card)
            if identity.id == select or chosen is None:
                chosen = item
        self.identity_list.blockSignals(False)
        if chosen is not None:
            self.identity_list.setCurrentItem(chosen)
            self.edit_identity(chosen.data(Qt.ItemDataRole.UserRole))
        else:
            self.edit_identity(None)
        if errors:
            self.identity_note.setText("\n".join(f"{name}: {error}" for name, error in errors.items()))

    def edit_identity(self, identity_id: str | None) -> None:
        """Show the files of an identity in the editor."""
        self.editing_id = identity_id
        self.identity_editor.setEnabled(identity_id is not None)
        self.identity_note.setText("")
        if identity_id is None:
            self.chat_summary.setText("Make a new identity on the left.")
            return
        directory = self.engine.config.identities_dir / identity_id
        try:
            identity = load_identity(directory)
        except (IdentityError, TranscriptError, ValueError) as error:
            self.identity_note.setText(str(error))
            return
        settings = editing.read_settings(directory)
        self.edit_name.setText(identity.display_name)
        self.edit_personality.setPlainText(identity.personality)
        self.edit_model.setText(str(settings.get("model", "")))
        self.edit_temperature.setText(str(settings.get("temperature", "")))
        self.edit_mode.setCurrentIndex(max(0, self.edit_mode.findData(settings.get("mode", ""))))
        speakers = list(dict.fromkeys(message.speaker for message in identity.transcript))
        self.edit_speaker.clear()
        self.edit_speaker.addItems(speakers)
        self.edit_speaker.setEnabled(bool(speakers))
        if identity.speaker:
            self.edit_speaker.setCurrentText(identity.speaker)
            lines = [f"{identity.style.message_count} messages from {identity.speaker} in chat.md."]
            lines += [f"- {line}" for line in identity.style.describe()]
            self.chat_summary.setText("\n".join(lines))
        else:
            self.chat_summary.setText("No chat.md yet. The identity writes from its personality only.")

    def save_identity(self) -> None:
        if self.editing_id is None:
            return
        directory = self.engine.config.identities_dir / self.editing_id
        temperature = self.edit_temperature.text().strip()
        try:
            value = float(temperature) if temperature else None
        except ValueError:
            self.identity_note.setText("Write the temperature as a number, for example 0.7, or leave it empty.")
            return
        try:
            editing.save_personality(directory, self.edit_personality.toPlainText())
        except editing.EditError as error:
            self.identity_note.setText(str(error).capitalize() + ".")
            return
        editing.save_settings(directory, {
            "display_name": self.edit_name.text().strip(),
            "speaker": self.edit_speaker.currentText() if self.edit_speaker.isEnabled() else None,
            "model": self.edit_model.text().strip(),
            "temperature": value,
            "mode": self.edit_mode.currentData(),
        })
        self.reload_rooms()
        self.refresh_identities(self.editing_id)
        self.identity_note.setText("Saved.")

    def ask_for_name(self) -> str | None:
        name, ok = QInputDialog.getText(self, "New identity", "Name")
        return name if ok and name.strip() else None

    def ask_for_speaker(self, labels: list[str], preselect: int) -> int | None:
        label, ok = QInputDialog.getItem(self, "Import a chat", "Which name is this person?", labels, preselect, False)
        return labels.index(label) if ok else None

    def ask_to_confirm(self, question: str) -> bool:
        return QMessageBox.question(self, "mimikr", question) == QMessageBox.StandardButton.Yes

    def ask_for_export(self) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(self, "Import a chat", str(Path.home() / "Downloads"),
                                              "Chat exports (*.txt *.json *.md);;All files (*)")
        return Path(path) if path else None

    def new_identity(self) -> None:
        name = self.ask_name()
        if name is None:
            return
        try:
            directory = editing.create_identity(self.engine.config.identities_dir, name)
        except editing.EditError as error:
            QMessageBox.warning(self, "mimikr", str(error).capitalize() + ".")
            return
        self.show_identities(select=directory.name)

    def import_chat(self, identity_id: str, path: Path | None = None) -> None:
        """Read an export or a chat.md file, ask which name is the person, and write chat.md."""
        path = path or self.pick_export()
        if path is None:
            return
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            self.identity_note.setText(f"Cannot read {path.name}: {error}")
            return
        try:
            _, messages = read_export(text)
        except ExportError as error:
            try:
                messages = parse_transcript(text)
            except TranscriptError:
                messages = []
            if not messages:
                self.identity_note.setText(str(error).capitalize() + ".")
                return
        counts: dict[str, int] = {}
        for message in messages:
            counts[message.speaker] = counts.get(message.speaker, 0) + 1
        names = sorted(counts, key=lambda name: -counts[name])
        wanted = self.edit_name.text().strip().casefold()
        preselect = next((index for index, name in enumerate(names) if name.casefold() == wanted), 0)
        choice = self.pick_speaker(
            [f"{name} ({counts[name]} {'message' if counts[name] == 1 else 'messages'})" for name in names], preselect)
        if choice is None:
            return
        directory = self.engine.config.identities_dir / identity_id
        replace_chat = False
        if (directory / "chat.md").exists():
            if not self.confirm(f"Write over the chat.md of {self.edit_name.text()}?"):
                return
            replace_chat = True
        editing.save_chat(directory, messages, names[choice], replace=replace_chat)
        self.refresh_identities(identity_id)
        self.identity_note.setText(f"Imported {len(messages)} messages from {path.name}.")

    # Replies

    def set_reply(self, message_id: str | None) -> None:
        """Show which message the next message replies to, or hide the bar."""
        self.replying_to = message_id
        quote = None
        if message_id and self.room is not None:
            quote = quote_of(self.room, RoomMessage(author=USER, name="You", text="", reply_to=message_id))
        self.reply_label.setText(f"Reply to {quote}" if quote else "")
        self.reply_bar.setVisible(bool(quote))
        if quote:
            self.composer.setFocus()
        else:
            self.replying_to = None

    # Topic and lore

    def ask_for_topic(self, old: str) -> str | None:
        text, ok = QInputDialog.getText(self, "Topic", "What happens in the room now?", text=old)
        return text if ok else None

    def change_topic(self) -> None:
        if self.room is None or self.busy:
            return
        topic = self.ask_topic(self.room.topic)
        if topic is None:
            return
        room = self.engine.store.get(self.room.id)
        self.engine.set_topic(room, topic)
        self.room = room
        self.show_room(room)

    def save_lore(self) -> None:
        self.engine.save_lore(self.lore_editor.toPlainText())
        self.lore_note.setText("Saved. Each identity knows it from the next reply.")

    # Message actions

    def ask_for_text(self, old: str) -> str | None:
        text, ok = QInputDialog.getMultiLineText(self, "Edit the message", "Text", old)
        return text if ok else None

    def message_menu(self, message_id: str, where) -> None:
        if self.room is None:
            return
        room = self.engine.store.get(self.room.id)
        try:
            message = self.engine.find_message(room, message_id)
        except EngineError:
            return
        last = self.engine.last_turn(room)
        menu = QMenu(self)
        menu.addAction("Reply", lambda: self.message_action("reply", message_id))
        menu.addAction("Copy", lambda: self.message_action("copy", message_id))
        menu.addAction("Edit...", lambda: self.message_action("edit", message_id)).setEnabled(not self.busy)
        if message.author in room.members:
            label = "Remove the like" if message.liked else "Like this reply"
            menu.addAction(label, lambda: self.message_action("like", message_id)).setEnabled(not self.busy)
        if last and message_id in [m.id for m in last[1]]:
            menu.addAction("Write again", lambda: self.message_action("regenerate", message_id)).setEnabled(
                not self.busy)
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.message_action("delete", message_id)).setEnabled(not self.busy)
        menu.exec(where)

    def message_action(self, action: str, message_id: str) -> None:
        """Do an action of the menu of a message: copy, edit, like, regenerate or delete."""
        if self.room is None:
            return
        room = self.engine.store.get(self.room.id)
        message = self.engine.find_message(room, message_id)
        if action == "reply":
            self.set_reply(message_id)
            return
        if action == "copy":
            QGuiApplication.clipboard().setText(message.text)
            self.set_status("Copied the message.")
            return
        if self.busy:
            return
        if action == "edit":
            text = self.ask_text(message.text)
            if text is None or not text.strip():
                return
            self.engine.edit_message(room, message_id, text)
        elif action == "like":
            self.engine.set_liked(room, message_id, not message.liked)
        elif action == "delete":
            self.engine.delete_message(room, message_id)
        elif action == "regenerate":
            member = self.engine.remove_last_turn(room)
            self.room = room
            self.show_room(room)
            members = iter([member])
            self.start(lambda _room: next(members, None))
            return
        self.room = room
        self.show_room(room)

    # Export

    def room_text(self) -> str:
        identities, _ = self.engine.identities()
        names = {USER: "You"} | {key: value.display_name for key, value in identities.items()}
        return room_as_text(self.engine.store.get(self.room.id), names)

    def ask_for_save_path(self, suggested: str) -> Path | None:
        start = Path.home() / "Documents" / suggested
        path, _ = QFileDialog.getSaveFileName(self, "Export the room", str(start), "Text (*.txt)")
        return Path(path) if path else None

    def export_menu(self) -> None:
        if self.room is None:
            return
        menu = QMenu(self)
        menu.addAction("Save as text file...", self.export_to_file)
        menu.addAction("Copy as text", self.copy_as_text)
        menu.exec(self.export_button.mapToGlobal(self.export_button.rect().bottomLeft()))

    def export_to_file(self) -> None:
        if self.room is None:
            return
        path = self.pick_save_path(file_name(self.room))
        if path is None:
            return
        if path.suffix == "":
            path = path.with_suffix(".txt")
        try:
            path.write_text(self.room_text(), encoding="utf-8")
        except OSError as error:
            self.set_status(f"Cannot write {path}: {error.strerror}", error=True)
            return
        self.set_status(f"Exported to {path}")

    def copy_as_text(self) -> None:
        if self.room is None:
            return
        QGuiApplication.clipboard().setText(self.room_text())
        self.set_status("Copied the room as text.")

    # Local servers

    def start_local_servers(self) -> None:
        """Start the llama.cpp servers of the settings page, in a worker thread, and use them."""
        if self.local_servers:
            return
        trial = replace(self.engine.config)
        self.settings.apply_local(trial)
        executable = trial.llama_server or find_llama_server()
        log_dir = self.engine.config.data_dir / "logs"
        planned = []
        if trial.chat_gguf:
            planned.append(LocalServer("chat", executable, trial.chat_gguf, trial.chat_port,
                                       self.engine.config.model, log_dir, trial.context_size))
        if trial.embedding_gguf:
            planned.append(LocalServer("embedding", executable, trial.embedding_gguf, trial.embedding_port,
                                       self.engine.config.embedding_model, log_dir, trial.context_size,
                                       embeddings=True))
        if not planned:
            self.settings.server_status.setText("Choose a chat model file, an embedding model file, or both.")
            return
        self.local_servers = planned
        self.settings.start_button.setEnabled(False)
        self.settings.stop_button.setEnabled(True)
        self.settings.server_status.setText("Starting. A large model takes some seconds to load...")

        def work() -> None:
            try:
                for server in planned:
                    server.start()
                for server in planned:
                    server.wait_until_ready()
                self.bridge.servers.emit("")
            except ServerError as error:
                self.bridge.servers.emit(str(error))

        threading.Thread(target=work, daemon=True).start()

    def on_servers(self, error: str) -> None:
        if error:
            self.stop_local_servers()
            self.settings.server_status.setText(f"Fault: {error}.")
            return
        config = self.engine.config
        lines = []
        for server in self.local_servers:
            if server.name == "chat":
                config.base_url = server.url
                self.settings.base_url.setText(server.url)
            else:
                config.embedding_url = server.url
                self.settings.embedding_url.setText(server.url)
            lines.append(f"The {server.name} server runs at {server.url}.")
        if self.reconnect:
            self.reconnect(config)
        self.settings.server_status.setText(" ".join(lines) + " mimikr uses it now.")

    def stop_local_servers(self) -> None:
        for server in self.local_servers:
            server.stop()
        self.local_servers = []
        self.settings.start_button.setEnabled(True)
        self.settings.stop_button.setEnabled(False)
        self.settings.server_status.setText("Stopped.")

    def closeEvent(self, event) -> None:
        for server in self.local_servers:
            server.stop()
        super().closeEvent(event)

    # Pictures

    def ask_for_image(self) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", str(Path.home()), IMAGE_FILTER)
        return Path(path) if path else None

    def choose_picture(self, kind: str, key: str) -> None:
        source = self.pick_image()
        if source is None:
            return
        try:
            save_picture(source, self.avatars.path_for(kind, key))
        except ValueError as error:
            QMessageBox.warning(self, "mimikr", str(error))
            return
        self.pictures_changed()

    def remove_picture(self, kind: str, key: str) -> None:
        self.avatars.remove(kind, key)
        self.pictures_changed()

    def pictures_changed(self) -> None:
        self.reload_rooms()
        if self.room is not None:
            self.show_room(self.room)
        self.refresh_pictures()

    def refresh_pictures(self) -> None:
        """Fill the Pictures card of the settings: one row for each identity."""
        layout = self.settings.pictures
        while layout.count():
            detach(layout.takeAt(0).widget())
        identities, _ = self.engine.identities()
        if not identities:
            layout.addWidget(QLabel("No identities found.", objectName="hint"))
        for identity in identities.values():
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(10)
            line.addWidget(avatar(identity.id, identity.display_name, 32,
                                  self.avatars.find("identity", identity.id)))
            line.addWidget(QLabel(identity.display_name), 1)
            choose = QPushButton("Choose...")
            choose.clicked.connect(lambda _checked, key=identity.id: self.choose_picture("identity", key))
            remove = QPushButton("Remove")
            remove.setEnabled(self.avatars.path_for("identity", identity.id).is_file())
            remove.clicked.connect(lambda _checked, key=identity.id: self.remove_picture("identity", key))
            line.addWidget(choose)
            line.addWidget(remove)
            layout.addWidget(row)

    def room_picture_menu(self) -> None:
        if self.room is None:
            return
        menu = QMenu(self)
        menu.addAction("Choose picture...", lambda: self.choose_picture("room", self.room.id))
        remove = menu.addAction("Remove picture", lambda: self.remove_picture("room", self.room.id))
        remove.setEnabled(self.avatars.path_for("room", self.room.id).is_file())
        menu.exec(self.room_picture.mapToGlobal(self.room_picture.rect().bottomLeft()))

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
        identities, _ = self.engine.identities()
        names = {key: value.display_name for key, value in identities.items()}
        query = self.search.text().strip()
        for room, hits in search_rooms(self.engine.store.list(), query, names):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, room.id)
            card = self.room_card(room, f"{hits} {'message' if hits == 1 else 'messages'}" if hits else None)
            item.setSizeHint(QSize(0, card.sizeHint().height()))
            self.rooms.addItem(item)
            self.rooms.setItemWidget(item, card)
            if room.id == current:
                self.rooms.setCurrentItem(item)
        self.rooms.blockSignals(False)

    def room_card(self, room: Room, note: str | None = None) -> QWidget:
        """Return the entry of a room in the list: a round picture, the name and the members."""
        card = QWidget()
        card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        line = QHBoxLayout(card)
        line.setContentsMargins(10, 8, 10, 8)
        line.setSpacing(10)
        first = room.members[0] if room.members else room.id
        picture = self.avatars.find("room", room.id) or (self.avatars.find("identity", first) if room.members else None)
        line.addWidget(avatar(first, self.names([first]) or room.name, 32, picture))
        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel(room.name, objectName="roomTitle")
        members = QLabel(note or self.names(room.members), objectName="roomMembers")
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
        self.identities_button.setChecked(False)
        if room_id is None:
            self.room = None
            self.pages.setCurrentIndex(EMPTY_PAGE)
            return
        self.room = self.engine.store.get(room_id)
        self.show_room(self.room)
        self.set_status("")
        self.pages.setCurrentIndex(ROOM_PAGE)
        self.composer.setFocus()

    def show_room(self, room: Room) -> None:
        """Draw the header and the messages of the room again."""
        if self.replying_to and not any(m.id == self.replying_to for m in room.messages):
            self.set_reply(None)
        self.title.setText(room.name)
        self.subtitle.setText("With " + self.names(room.members))
        self.topic_label.setText(f"Topic: {room.topic}" if room.topic else "")
        self.topic_label.setVisible(bool(room.topic))
        while self.room_picture_holder.count():
            detach(self.room_picture_holder.takeAt(0).widget())
        first = room.members[0] if room.members else room.id
        picture = self.avatars.find("room", room.id) or (self.avatars.find("identity", first) if room.members else None)
        # The same picture as the card of the room in the list.
        self.room_picture_holder.addWidget(avatar(first, self.names([first]) or room.name, 36, picture))
        self.view.clear()
        query = self.search.text().strip()
        first = None
        for message in room.messages:
            self.view.add(message, quote_of(room, message))
            if query and matches(message.text, query):
                bubble = self.view.bubble(message.id)
                bubble.setProperty("match", True)
                first = first or bubble
        if first is not None:
            self.view.ensureWidgetVisible(first)

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
            room = self.engine.create_room(dialog.name.text(), dialog.selected(), dialog.topic.text())
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
        self.avatars.remove("room", self.room.id)
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
        message = self.engine.post_user_message(self.room, text, reply_to=self.replying_to)
        self.view.add(message, quote_of(self.room, message))
        self.set_reply(None)
        # The author of the message that the user replies to answers first.
        answered = next((m.author for m in self.room.messages if m.id == message.reply_to), None)
        order = sorted(self.room.members, key=lambda member: member != answered)
        members = iter(order)
        self.start(lambda room: next(members, None))

    def next_speaker(self) -> None:
        if self.room is None or self.busy:
            return
        members = iter([self.engine.next_speaker(self.room)])
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
            return self.engine.next_speaker(room)

        self.start(next_member)

    def start(self, next_member: Callable[[Room], str | None]) -> None:
        """Let members write in a worker thread, until next_member gives None or the user stops."""
        room = self.room
        self.stop_event = threading.Event()
        stop = self.stop_event
        self.set_busy(True)
        self.set_status("")

        realistic = self.engine.config.realistic_timing

        def wait(seconds: float) -> None:
            if seconds > 0 and stop.wait(seconds):
                raise Stopped

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

                    started = time.monotonic()
                    # With realistic timing, the text does not show while the
                    # model writes. A person does not see a message before it is sent.
                    messages = self.engine.speak(room, member, on_text=None if realistic else on_text)
                    for number, message in enumerate(messages):
                        if realistic:
                            spent = time.monotonic() - started if number == 0 else 0.0
                            wait(typing_seconds(message.text) - spent)
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
            # A stop during a pause leaves saved messages that the window did not show yet.
            if len(self.view.texts()) != len(self.room.messages):
                self.show_room(self.room)
            if self.status.objectName() != "error" and self.status.text() != "Stopped.":
                self.set_status("")


def run(config: Config) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("mimikr")
    chat = ChatClient(config.base_url, config.api_key, sampling=sampling(config))
    embedding_client = ChatClient(embedding_base_url(config), config.api_key)

    def embed(texts: list[str]) -> list[list[float]]:
        return embedding_client.embed(texts, config.embedding_model)

    engine = RoomEngine(config, chat, embed)

    def reconnect(new: Config) -> None:
        nonlocal embedding_client
        engine.completer = ChatClient(new.base_url, new.api_key, sampling=sampling(new))
        embedding_client = ChatClient(embedding_base_url(new), new.api_key)

    window = MainWindow(engine, reconnect=reconnect)
    window.show()
    if config.start_servers and (config.chat_gguf or config.embedding_gguf):
        window.start_local_servers()
    return application.exec()

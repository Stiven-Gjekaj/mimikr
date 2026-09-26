"""Make and change identities. The identity editor of the window calls these functions.

mimikr writes the files of an identity only here, and only when the user saves
in the editor or imports a chat into an identity.
"""

import json
import re
import tomllib
from pathlib import Path

from mimikr.importers import write_transcript
from mimikr.transcript import Message

# The keys of identity.toml, in the order of the file.
SETTING_KEYS = ("display_name", "speaker", "model", "temperature", "mode")


class EditError(ValueError):
    pass


def directory_name(display_name: str) -> str:
    """Make the name of a directory from a display name: small letters, digits and hyphens."""
    name = re.sub(r"[^a-z0-9]+", "-", display_name.strip().lower()).strip("-")
    if not name:
        raise EditError("the name needs a letter or a digit")
    return name


def create_identity(root: Path, display_name: str, personality: str = "") -> Path:
    """Make the directory of a new identity, with personality.md and identity.toml."""
    directory = root / directory_name(display_name)
    if directory.exists():
        raise EditError(f"an identity is already in {directory}")
    directory.mkdir(parents=True)
    text = personality.strip() or f"{display_name.strip()} is a person. Write a short description here."
    (directory / "personality.md").write_text(text + "\n", encoding="utf-8")
    save_settings(directory, {"display_name": display_name.strip()})
    return directory


def read_settings(directory: Path) -> dict:
    path = directory / "identity.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def save_settings(directory: Path, changes: dict) -> None:
    """Change keys of identity.toml. A value of None or "" removes the key. Other keys stay."""
    settings = read_settings(directory)
    for key, value in changes.items():
        if value is None or value == "":
            settings.pop(key, None)
        else:
            settings[key] = value
    lines = []
    ordered = [key for key in SETTING_KEYS if key in settings] + [key for key in settings if key not in SETTING_KEYS]
    for key in ordered:
        value = settings[key]
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (int, float)):
            text = repr(value)
        else:
            text = json.dumps(str(value), ensure_ascii=False)
        lines.append(f"{key} = {text}")
    (directory / "identity.toml").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def save_personality(directory: Path, text: str) -> None:
    if not text.strip():
        raise EditError("the personality needs text")
    (directory / "personality.md").write_text(text.strip() + "\n", encoding="utf-8")


def save_chat(directory: Path, messages: list[Message], speaker: str, replace: bool = False) -> None:
    """Write the messages as chat.md, and set the speaker. Refuse to write over chat.md unless replace is true."""
    path = directory / "chat.md"
    if path.exists() and not replace:
        raise EditError(f"{path} exists")
    if not any(message.speaker == speaker for message in messages):
        raise EditError(f"no message is from {speaker!r}")
    path.write_text(write_transcript(messages), encoding="utf-8")
    save_settings(directory, {"speaker": speaker})

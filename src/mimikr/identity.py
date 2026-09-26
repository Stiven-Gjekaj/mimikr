"""Load an identity from its directory.

An identity directory holds these files:

- `personality.md`: a short description of the person. This file is necessary.
- `chat.md`: a transcript of messages from the person. This file is optional.
- `identity.toml`: optional settings. The keys are `display_name`, `speaker`,
  `model` and `temperature`.

The `speaker` is the name of the person in `chat.md`.
If `speaker` is not set, the loader uses the display name.
If `display_name` is not set, the loader uses the name of the directory.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from mimikr.style import StyleProfile, build_profile
from mimikr.transcript import Message, parse_transcript, speakers


class IdentityError(ValueError):
    pass


@dataclass
class Identity:
    id: str
    display_name: str
    personality: str
    speaker: str | None = None
    transcript: list[Message] = field(default_factory=list)
    style: StyleProfile = field(default_factory=StyleProfile)
    model: str | None = None
    temperature: float | None = None


def load_identity(directory: Path) -> Identity:
    personality_file = directory / "personality.md"
    if not personality_file.is_file():
        raise IdentityError(f"{directory}: personality.md is missing")

    settings: dict = {}
    settings_file = directory / "identity.toml"
    if settings_file.is_file():
        settings = tomllib.loads(settings_file.read_text(encoding="utf-8"))

    display_name = settings.get("display_name") or directory.name
    identity = Identity(
        id=directory.name,
        display_name=display_name,
        personality=personality_file.read_text(encoding="utf-8").strip(),
        model=settings.get("model"),
        temperature=settings.get("temperature"),
    )

    chat_file = directory / "chat.md"
    if chat_file.is_file():
        transcript = parse_transcript(chat_file.read_text(encoding="utf-8"))
        wanted = (settings.get("speaker") or display_name).casefold()
        match = [name for name in speakers(transcript) if name.casefold() == wanted]
        if transcript and not match:
            names = ", ".join(speakers(transcript))
            raise IdentityError(
                f"{chat_file}: no speaker is named {wanted!r}. The speakers are: {names}."
                " Set 'speaker' in identity.toml."
            )
        if match:
            identity.speaker = match[0]
            identity.transcript = transcript
            identity.style = build_profile(transcript, identity.speaker)
    return identity


def list_identities(root: Path) -> tuple[dict[str, Identity], dict[str, str]]:
    """Load each identity under the root.

    Return the identities and the errors. A fault in one identity does not stop the others.
    The loader skips a directory that has no personality.md.
    """
    identities: dict[str, Identity] = {}
    errors: dict[str, str] = {}
    if not root.is_dir():
        return identities, errors
    for directory in sorted(root.iterdir()):
        if not (directory / "personality.md").is_file():
            continue
        try:
            identities[directory.name] = load_identity(directory)
        except (IdentityError, ValueError) as error:
            errors[directory.name] = str(error)
    return identities, errors

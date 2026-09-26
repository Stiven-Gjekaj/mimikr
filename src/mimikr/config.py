"""Load the settings of mimikr.

The order of priority, from high to low:

1. Environment variables, for example `MIMIKR_MODEL`.
2. The file `mimikr.toml` in the home of mimikr.
3. The defaults in this file.

The home of mimikr is `MIMIKR_HOME` if it is set. In the macOS application it
is `~/Documents/mimikr`, because a program that starts from the Dock has no
useful working directory. Otherwise it is the working directory.

A relative folder in the settings is relative to the directory of mimikr.toml.
"""

import json
import os
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    # The defaults point to Ollama. LM Studio uses http://localhost:1234/v1.
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "local"
    model: str = "llama3.1"
    temperature: float = 0.8
    # Penalties for words that the reply already has. They make the model repeat
    # itself less. Each is a standard option of the OpenAI API, from -2 to 2.
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    # The maximum number of characters of the room that go to the model. Older
    # messages stay in the room, but the model does not see them.
    history_budget: int = 12000
    # Remove from a reply what the person clearly never does: capitals at the
    # start, a period at the end, emoji. See style.enforce.
    enforce_style: bool = True
    # Drop a message that repeats one of the last messages of the identity.
    avoid_repeats: bool = True
    # How a room chooses the next speaker: "smart" or "rotate". See engine.next_speaker.
    turn_taking: str = "smart"
    # Send each reply after about the time that a person takes to write it.
    realistic_timing: bool = True
    # How the model writes: "continue" gives a chat log to the model to
    # continue, and "chat" sends chat messages to an instruct model. In P4,
    # "continue" scored 0.92 for style and "chat" 0.71. See docs/milestones.md.
    mode: str = "continue"
    # How the prompt chooses examples from the transcript: "recent" takes the
    # end of the transcript, and "similar" takes the exchanges most similar to
    # the current message. "similar" needs the embedding model.
    examples: str = "recent"
    # The model that `mimikr eval` uses to compare the meaning of two replies.
    embedding_model: str = "nomic-embed-text"
    # The server of the embedding model. Empty means the server in base_url.
    # llama.cpp serves one model on each server, so it needs a second address.
    embedding_url: str = ""
    # llama.cpp servers that the window can start. An empty llama_server means
    # the llama-server that the system finds.
    llama_server: str = ""
    chat_gguf: str = ""
    embedding_gguf: str = ""
    chat_port: int = 8080
    embedding_port: int = 8081
    context_size: int = 8192
    start_servers: bool = False
    # The look of the window. theme is "system", "light" or "dark". accent is a
    # name from theme.ACCENTS or a "#rrggbb" color.
    theme: str = "system"
    accent: str = "violet"
    font_size: int = 14
    identities_dir: Path = Path("identities")
    data_dir: Path = Path("data")


def app_home(environ: dict[str, str] | None = None) -> Path:
    environ = os.environ if environ is None else environ
    if environ.get("MIMIKR_HOME"):
        return Path(environ["MIMIKR_HOME"]).expanduser()
    if getattr(sys, "frozen", False):
        return Path.home() / "Documents" / "mimikr"
    return Path.cwd()


def config_file(environ: dict[str, str] | None = None) -> Path:
    return app_home(environ) / "mimikr.toml"


def load_config(path: Path | None = None, environ: dict[str, str] | None = None) -> Config:
    environ = os.environ if environ is None else environ
    path = path if path is not None else config_file(environ)
    values: dict[str, object] = {}
    if path.is_file():
        values.update(tomllib.loads(path.read_text(encoding="utf-8")))
    for item in fields(Config):
        key = f"MIMIKR_{item.name.upper()}"
        if key in environ:
            values[item.name] = environ[key]

    config = Config()
    for item in fields(Config):
        if item.name not in values:
            continue
        setattr(config, item.name, convert(getattr(config, item.name), values[item.name]))
    for name in ("identities_dir", "data_dir"):
        folder = getattr(config, name).expanduser()
        setattr(config, name, folder if folder.is_absolute() else path.parent / folder)
    return config


def convert(default: object, value: object) -> object:
    """Give the value the type of the default. An environment variable is always text."""
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off", ""):
            return False
        raise ValueError(f"{value!r} is not true or false")
    if isinstance(default, Path):
        return Path(value)
    return type(default)(value)


def embedding_base_url(config: Config) -> str:
    return config.embedding_url or config.base_url


def save_config(config: Config, path: Path = Path("mimikr.toml")) -> None:
    """Write each setting to the file. The settings page of the window calls this.

    The file gets all the settings, so that a reader sees each value in one place.
    An environment variable still has priority when mimikr starts.
    """
    lines = ["# The settings of mimikr. The settings page of the window writes this file.", ""]
    for item in fields(Config):
        value = getattr(config, item.name)
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (Path, str)):
            # A JSON string is also a valid TOML basic string.
            text = json.dumps(str(value), ensure_ascii=False)
        else:
            text = repr(value)
        lines.append(f"{item.name} = {text}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def sampling(config: Config) -> dict:
    """Return the options of the settings that go with each request for text."""
    options = {"frequency_penalty": config.frequency_penalty, "presence_penalty": config.presence_penalty}
    return {key: value for key, value in options.items() if value}

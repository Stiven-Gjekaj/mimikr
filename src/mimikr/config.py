"""Load the settings of mimikr.

The order of priority, from high to low:

1. Environment variables, for example `MIMIKR_MODEL`.
2. The file `mimikr.toml` in the working directory.
3. The defaults in this file.
"""

import json
import os
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
    # How the model writes: "chat" sends chat messages to an instruct model, and
    # "continue" gives a chat log to a base model to continue.
    mode: str = "chat"
    # How the prompt chooses examples from the transcript: "recent" takes the
    # end of the transcript, and "similar" takes the exchanges most similar to
    # the current message. "similar" needs the embedding model.
    examples: str = "recent"
    # The model that `mimikr eval` uses to compare the meaning of two replies.
    embedding_model: str = "nomic-embed-text"
    # The server of the embedding model. Empty means the server in base_url.
    # llama.cpp serves one model on each server, so it needs a second address.
    embedding_url: str = ""
    # The look of the window. theme is "system", "light" or "dark". accent is a
    # name from theme.ACCENTS or a "#rrggbb" color.
    theme: str = "system"
    accent: str = "violet"
    font_size: int = 14
    identities_dir: Path = Path("identities")
    data_dir: Path = Path("data")


def load_config(path: Path = Path("mimikr.toml"), environ: dict[str, str] | None = None) -> Config:
    environ = os.environ if environ is None else environ
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
        default = getattr(config, item.name)
        value = values[item.name]
        setattr(config, item.name, type(default)(value) if not isinstance(default, Path) else Path(value))
    return config


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
        if isinstance(value, (Path, str)):
            # A JSON string is also a valid TOML basic string.
            text = json.dumps(str(value), ensure_ascii=False)
        else:
            text = repr(value)
        lines.append(f"{item.name} = {text}")
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)

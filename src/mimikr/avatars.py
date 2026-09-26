"""Find and keep the pictures of identities and rooms.

A picture that the user chooses in the window goes to `<data_dir>/avatars/`.
The window never writes into the directory of an identity. A person can also
put `avatar.png` or `avatar.jpg` into the directory of an identity by hand. The
picture in `data_dir` has priority.
"""

from pathlib import Path

KINDS = ("identity", "room")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class AvatarStore:
    def __init__(self, data_dir: Path, identities_dir: Path):
        self.directory = data_dir / "avatars"
        self.identities_dir = identities_dir

    def path_for(self, kind: str, key: str) -> Path:
        """Return the file that the window writes for a picture. It is always a PNG file."""
        if kind not in KINDS:
            raise ValueError(f"the kind is {kind!r}. Use 'identity' or 'room'")
        if not key or key.startswith(".") or any(part in key for part in ("/", "\\", "\0")):
            raise ValueError(f"{key!r} cannot be the name of a picture")
        return self.directory / f"{kind}-{key}.png"

    def find(self, kind: str, key: str) -> Path | None:
        """Return the picture of an identity or a room, or None."""
        chosen = self.path_for(kind, key)
        if chosen.is_file():
            return chosen
        if kind == "identity":
            for extension in EXTENSIONS:
                by_hand = self.identities_dir / key / f"avatar{extension}"
                if by_hand.is_file():
                    return by_hand
        return None

    def remove(self, kind: str, key: str) -> None:
        """Remove the picture that the window wrote. A picture in the directory of an identity stays."""
        self.path_for(kind, key).unlink(missing_ok=True)

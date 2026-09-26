#!/usr/bin/env python3
"""Build assets/window.png and assets/settings.png. Run it from the root of the repository:

    uv run python scripts/make-screenshots.py

The window uses the invented identities in examples/identities, and a stand-in
model with fixed replies. No real person and no real model are in the images.
Qt draws with no screen, so the script opens no window.
"""

import os
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from mimikr.config import Config  # noqa: E402
from mimikr.engine import RoomEngine  # noqa: E402
from mimikr.gui import MainWindow  # noqa: E402

REPLIES = {
    "Sam": "lol\nwho is asking\nit is 2am",
    "June": "Hi! I am still awake too. How was your shift? Did the new cook set anything on fire again?",
}


class StandIn:
    """Reply with a fixed text for each identity."""

    def complete(self, messages, model, temperature):
        name = messages[0]["content"].split("You are ", 1)[1].split(".", 1)[0]
        return REPLIES[name]


def shoot(application: QApplication, out: str, theme: str, page: str) -> None:
    with tempfile.TemporaryDirectory() as data:
        config = Config(identities_dir=Path("examples/identities"), data_dir=Path(data), theme=theme)
        window = MainWindow(RoomEngine(config, StandIn()), config_path=Path(data) / "mimikr.toml")
        window.resize(1080, 700)
        window.engine.create_room("Kitchen crew", ["sam"])
        room = window.engine.create_room("Late night", ["june", "sam"])
        window.select_room(room.id)
        window.composer.setPlainText("anyone up?")
        window.send()
        while window.busy:
            application.processEvents()
            time.sleep(0.01)
        window.show()
        if page == "settings":
            window.show_settings()
        application.processEvents()
        # The central widget only: macOS draws the menu bar at the top of the screen.
        window.centralWidget().grab().save(out)
        print(f"written {out}")


application = QApplication([])
shoot(application, "assets/window.png", "dark", "room")
shoot(application, "assets/settings.png", "light", "settings")

"""The command line of mimikr.

- `mimikr` or `mimikr gui`: open the window.
- `mimikr check`: load each identity and show what the program found.
"""

import argparse
import sys

from mimikr.config import load_config
from mimikr.identity import list_identities


def check(config) -> int:
    identities, errors = list_identities(config.identities_dir)
    if not identities and not errors:
        print(f"No identities found in {config.identities_dir}/.")
        print("Make a directory for each identity, with a personality.md file in it.")
        return 1
    for identity in identities.values():
        print(f"{identity.id} ({identity.display_name})")
        if identity.speaker:
            print(f"  chat.md: {identity.style.message_count} messages from '{identity.speaker}'")
            for line in identity.style.describe():
                print(f"  - {line}")
        else:
            print("  chat.md: none")
    for name, error in errors.items():
        print(f"{name}: ERROR: {error}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mimikr")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="open the window (the default)")
    commands.add_parser("check", help="load the identities and show the results")
    arguments = parser.parse_args(argv)

    config = load_config()
    if arguments.command == "check":
        return check(config)
    from mimikr.gui import run

    return run(config)


if __name__ == "__main__":
    sys.exit(main())

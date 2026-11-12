"""Install the Fresh theme while preserving unrelated user settings."""

import json
from pathlib import Path
import sys
import tempfile
import os


def write_atomic(path, content):
    if path.exists() and path.read_text() == content:
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(home, theme_source):
    directory = Path(home) / ".config/fresh"
    themes = directory / "themes"
    themes.mkdir(parents=True, exist_ok=True)
    theme = Path(theme_source).read_text()
    name = json.loads(theme)["name"]
    config_path = directory / "config.json"
    settings = json.loads(config_path.read_text()) if config_path.exists() else {}
    settings["theme"] = name
    write_atomic(themes / "catppuccin-mocha.json", theme)
    write_atomic(config_path, json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    configure(*sys.argv[1:])

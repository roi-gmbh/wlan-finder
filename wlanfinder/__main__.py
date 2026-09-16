"""Startpunkt: `python -m wlanfinder` oder `wlan-finder`."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

from .config import Config
from .server import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="wlan-finder", description="WLAN Finder")
    parser.add_argument("--config", type=Path, default=None, help="Pfad zur config.toml")
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--demo", action="store_true", help="Mit Beispieldaten statt echter Hardware starten")
    args = parser.parse_args()

    config = Config.load(args.config)
    backend = None
    if args.demo:
        from .wifi import FakeBackend

        backend = FakeBackend()

    if not args.no_browser:
        # Verzögert, sonst klopft der Browser an, bevor der Server lauscht.
        url = f"http://{config.general.host}:{config.general.port}"
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    run(config, backend)


if __name__ == "__main__":
    main()

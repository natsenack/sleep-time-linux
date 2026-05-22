#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import gi


APP_ICON_NAME = "power-timer"
APP_NAME = "Power Timer"


def _load_indicator_namespace() -> bool:
    try:
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3, Gtk  # noqa: F401
        return True
    except (ImportError, ValueError):
        pass

    try:
        gi.require_version("Gtk", "3.0")
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3, Gtk  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


if not _load_indicator_namespace():
    sys.exit(1)

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ImportError, ValueError):
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


def _resolve_launcher_command() -> Optional[list[str]]:
    source_launcher = Path(__file__).resolve().with_name("launch.sh")
    if source_launcher.exists():
        if os.access(source_launcher, os.X_OK):
            return [str(source_launcher)]

        bash_path = shutil.which("bash")
        if bash_path is not None:
            return [bash_path, str(source_launcher)]

    launcher_path = shutil.which("power-timer")
    if launcher_path is not None:
        return [launcher_path]

    return None


def _run_launcher(arguments: list[str]) -> None:
    try:
        subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return


def _create_menu() -> Gtk.Menu:
    menu = Gtk.Menu()

    open_item = Gtk.MenuItem.new_with_label("Afficher Power Timer")
    open_item.connect("activate", lambda *_args: _launch_show())
    menu.append(open_item)

    quit_item = Gtk.MenuItem.new_with_label("Quitter Power Timer")
    quit_item.connect("activate", lambda *_args: _launch_quit())
    menu.append(quit_item)

    menu.show_all()
    return menu


def _launch_show() -> None:
    launcher_command = _resolve_launcher_command()
    if launcher_command is None:
        return
    _run_launcher([*launcher_command, "--show-window"])


def _launch_quit() -> None:
    launcher_command = _resolve_launcher_command()
    if launcher_command is None:
        return
    _run_launcher([*launcher_command, "--quit"])


def _configure_icon_theme() -> None:
    icon_directory = Path(__file__).resolve().parent / "data" / "icons"
    if not icon_directory.exists():
        icon_directory = Path("/usr/share/icons/hicolor/256x256/apps")

    if icon_directory.exists():
        Gtk.IconTheme.get_default().append_search_path(str(icon_directory))


def main() -> int:
    _configure_icon_theme()

    indicator = AppIndicator.Indicator.new(
        "power-timer-tray",
        APP_ICON_NAME,
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    indicator.set_icon_full(APP_ICON_NAME, APP_NAME)
    indicator.set_menu(_create_menu())

    Gtk.main()
    return 0


if __name__ == "__main__":
    if any(argument == "--probe" for argument in sys.argv[1:]):
        raise SystemExit(0 if _load_indicator_namespace() else 1)
    raise SystemExit(main())
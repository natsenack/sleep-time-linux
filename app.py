#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import gi

try:
    from setproctitle import setproctitle
except ImportError:  # pragma: no cover - optional dependency
    setproctitle = None

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gdk, Gtk


APP_ID_BASE = "io.github.powertimer.PowerTimer"
APP_NAME = "Power Timer"
APP_VERSION = "1.0.0"
APP_PROCESS_NAME = "power-timer"

ROOT_REQUEST_ENV = "POWER_TIMER_ROOT_REQUEST"
ROOT_INSTANCE_ENV = "POWER_TIMER_ROOT_INSTANCE"
AUTO_START_ENV = "POWER_TIMER_AUTO_START"
INITIAL_MODE_ENV = "POWER_TIMER_INITIAL_MODE"
INITIAL_DURATION_ENV = "POWER_TIMER_INITIAL_DURATION"
FORCE_NON_UNIQUE_ENV = "POWER_TIMER_FORCE_NON_UNIQUE"
START_HIDDEN_ENV = "POWER_TIMER_START_HIDDEN"
ORIGIN_PID_ENV = "POWER_TIMER_ORIGIN_PID"


def is_root_instance() -> bool:
    if os.environ.get(ROOT_INSTANCE_ENV) == "1":
        return True
    return hasattr(os, "geteuid") and os.geteuid() == 0


def parse_positive_int_env(name: str) -> Optional[int]:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return None
    return parsed_value if parsed_value > 0 else None


APP_ID = APP_ID_BASE

SYSTEM_SHUTDOWN_CANDIDATES = ("/sbin/shutdown", "/usr/sbin/shutdown", "shutdown")
SYSTEM_SYSTEMCTL_CANDIDATES = ("/bin/systemctl", "/usr/bin/systemctl", "systemctl")
SYSTEM_SUDO_CANDIDATES = ("/usr/bin/sudo", "/bin/sudo", "sudo")
WINDOW_COMPACT_SIZE = (560, 580)


@dataclass(frozen=True)
class ModeSpec:
    key: str
    label: str
    subtitle: str
    icon_name: str
    system_scheduled: bool


MODE_SPECS: dict[str, ModeSpec] = {
    "shutdown": ModeSpec(
        key="shutdown",
        label="Éteindre",
        subtitle="systemctl poweroff à l'échéance",
        icon_name="system-shutdown-symbolic",
        system_scheduled=False,
    ),
    "reboot": ModeSpec(
        key="reboot",
        label="Redém.",
        subtitle="systemctl reboot à l'échéance",
        icon_name="view-refresh-symbolic",
        system_scheduled=False,
    ),
    "suspend": ModeSpec(
        key="suspend",
        label="Veille",
        subtitle="systemctl suspend",
        icon_name="system-suspend-symbolic",
        system_scheduled=False,
    ),
    "hibernate": ModeSpec(
        key="hibernate",
        label="Hiberner",
        subtitle="systemctl hibernate",
        icon_name="weather-clear-night-symbolic",
        system_scheduled=False,
    ),
    "hybrid": ModeSpec(
        key="hybrid",
        label="Hybride",
        subtitle="systemctl hybrid-sleep",
        icon_name="media-playback-pause-symbolic",
        system_scheduled=False,
    ),
}

MODE_ORDER = ("shutdown", "reboot", "suspend", "hibernate", "hybrid")
QUICK_DURATION_MINUTES = (15, 30, 60, 120, 180, 240, 300, 360)


def configure_application_identity() -> None:
    GLib.set_prgname(APP_PROCESS_NAME)
    GLib.set_application_name(APP_NAME)
    if setproctitle is not None:
        try:
            setproctitle(APP_PROCESS_NAME)
        except (OSError, ValueError, AttributeError):
            pass

APP_CSS = b"""
window.power-timer-window {
    background-color: @window_bg_color;
    background-image: radial-gradient(circle at top, alpha(@accent_bg_color, 0.14), transparent 36%);
}

.power-shell {
    padding: 10px;
}

.power-card {
    padding: 12px;
    border-radius: 16px;
}

.countdown-label {
    font-size: 36px;
    font-weight: 800;
    letter-spacing: -0.04em;
}

.mode-pill {
    min-height: 48px;
    padding: 6px 8px;
    border-radius: 16px;
}

.mode-pill image {
    margin-bottom: 0;
}

.mode-pill .heading {
    font-size: 0.82em;
    font-weight: 600;
}

.mode-pill:checked {
    background-color: alpha(@accent_bg_color, 0.18);
    border-color: @accent_bg_color;
}

.quick-button {
    border-radius: 999px;
    padding: 4px 10px;
}

.power-progress {
    min-height: 12px;
}

.status-label {
    font-weight: 600;
}

.header-tool-button {
    min-width: 36px;
    min-height: 36px;
    padding: 0;
    border-radius: 999px;
}

.header-tool-button image {
    margin: 0;
}

.header-root-button {
    min-height: 36px;
    padding: 0 12px;
    border-radius: 999px;
    background-color: alpha(@accent_bg_color, 0.14);
    border: 1px solid alpha(@accent_bg_color, 0.28);
    font-weight: 600;
}

.header-root-button:hover {
    background-color: alpha(@accent_bg_color, 0.2);
}

.header-root-button image {
    margin: 0;
}

.header-root-button .label {
    font-weight: 600;
}
"""


def resolve_executable(candidates: tuple[str, ...]) -> Optional[str]:
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.access(candidate, os.X_OK):
                return candidate
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def format_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def format_human_delay(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"

    total_minutes, remainder = divmod(seconds, 60)
    if total_minutes < 60:
        if remainder == 0:
            return "1 min" if total_minutes == 1 else f"{total_minutes} min"
        return f"{total_minutes} min {remainder:02d} s"

    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0 and remainder == 0:
        return "1 h" if hours == 1 else f"{hours} h"
    if minutes == 0:
        return f"{hours} h"
    return f"{hours} h {minutes:02d} min"


@dataclass
class TimerSession:
    mode_key: str
    duration_minutes: int
    total_seconds: int
    deadline: float
    system_scheduled: bool
    warning_5_sent: bool = False
    warning_1_sent: bool = False


class PowerTimerWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        initial_mode: Optional[str] = None,
        initial_duration_minutes: Optional[int] = None,
        auto_start_requested: bool = False,
    ) -> None:
        super().__init__(application=app)
        self._root_instance = is_root_instance()
        self._initial_mode = initial_mode if initial_mode in MODE_ORDER else None
        self._initial_duration_minutes = initial_duration_minutes if initial_duration_minutes is not None and initial_duration_minutes > 0 else None
        self._auto_start_requested = auto_start_requested
        self.set_title(APP_NAME + (" (root)" if self._root_instance else ""))
        self.set_default_size(*WINDOW_COMPACT_SIZE)
        self.set_resizable(True)
        self.add_css_class("power-timer-window")

        # Note: _shutdown_path est résolu mais pas utilisé; les commandes d'arrêt utilisent systemctl
        self._shutdown_path = resolve_executable(SYSTEM_SHUTDOWN_CANDIDATES)
        self._systemctl_path = resolve_executable(SYSTEM_SYSTEMCTL_CANDIDATES)
        self._sudo_path = resolve_executable(SYSTEM_SUDO_CANDIDATES) if not self._is_root() else None
        self._passwordless_sudo_available = self._can_use_passwordless_sudo()
        self._permission_allowed = self._is_root() or self._passwordless_sudo_available
        self._mode_hardware_supported: dict[str, bool] = {key: False for key in MODE_ORDER}

        self._mode_buttons: dict[str, Gtk.ToggleButton] = {}
        self._quick_buttons: list[Gtk.Button] = []
        self._selected_mode = "shutdown"
        self._active_session: Optional[TimerSession] = None
        self._tick_source_id: Optional[int] = None
        self._updating_mode_buttons = False
        self._root_button: Optional[Gtk.Button] = None
        self._state_poll_source_id: Optional[int] = None
        self._root_transition_signal_source_id: Optional[int] = None
        self._root_transition_hidden = False

        self.connect("close-request", self._on_close_request)

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        self._build_ui()
        self._refresh_mode_support()
        if self._initial_mode is not None and self._mode_hardware_supported.get(self._initial_mode, False):
            self._selected_mode = self._initial_mode
        else:
            self._selected_mode = self._choose_initial_mode()

        if self._initial_duration_minutes is not None:
            self.duration_spin.set_value(self._initial_duration_minutes)

        self._sync_mode_buttons(self._selected_mode)
        self._update_idle_preview()

        self._state_poll_source_id = GLib.timeout_add_seconds(1, self._monitor_window_state)

        if not self._root_instance:
            self._root_transition_signal_source_id = GLib.unix_signal_add(
                GLib.PRIORITY_DEFAULT,
                signal.SIGUSR1,
                self._on_root_transition_signal,
            )

        if self._auto_start_requested:
            GLib.idle_add(self._auto_start_after_activation)

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_header_bar())

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.add_css_class("power-shell")

        clamp = Adw.Clamp()
        clamp.set_maximum_size(560)
        clamp.set_tightening_threshold(500)
        page.append(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        clamp.set_child(content)

        toolbar_view.set_content(page)
        self._toast_overlay.set_child(toolbar_view)

        summary_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        summary_card.add_css_class("card")
        summary_card.add_css_class("power-card")

        summary_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        summary_top.set_valign(Gtk.Align.CENTER)

        self.mode_icon = Gtk.Image.new_from_icon_name("system-shutdown-symbolic")
        self.mode_icon.set_pixel_size(34)
        summary_top.append(self.mode_icon)

        summary_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.mode_label = Gtk.Label(label="Mode sélectionné")
        self.mode_label.add_css_class("title-3")
        self.mode_label.set_xalign(0.0)
        self.mode_hint_label = Gtk.Label(label="")
        self.mode_hint_label.add_css_class("dim-label")
        self.mode_hint_label.set_xalign(0.0)
        summary_text.append(self.mode_label)
        summary_text.append(self.mode_hint_label)
        summary_top.append(summary_text)

        summary_card.append(summary_top)

        self.countdown_label = Gtk.Label(label="00:00")
        self.countdown_label.add_css_class("countdown-label")
        self.countdown_label.set_halign(Gtk.Align.CENTER)
        self.countdown_label.set_xalign(0.5)
        summary_card.append(self.countdown_label)

        self.summary_label = Gtk.Label(label="Aucune action programmée.")
        self.summary_label.set_wrap(True)
        self.summary_label.set_justify(Gtk.Justification.CENTER)
        self.summary_label.set_xalign(0.5)
        summary_card.append(self.summary_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("power-progress")
        self.progress_bar.set_show_text(False)
        self.progress_bar.set_fraction(0.0)
        summary_card.append(self.progress_bar)

        self.status_label = Gtk.Label(label="Prêt à démarrer.")
        self.status_label.add_css_class("status-label")
        self.status_label.set_wrap(True)
        self.status_label.set_justify(Gtk.Justification.CENTER)
        self.status_label.set_xalign(0.5)
        summary_card.append(self.status_label)

        self.note_label = Gtk.Label(label="")
        self.note_label.add_css_class("dim-label")
        self.note_label.set_wrap(True)
        self.note_label.set_justify(Gtk.Justification.CENTER)
        self.note_label.set_xalign(0.5)
        summary_card.append(self.note_label)

        content.append(summary_card)

        config_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        config_card.add_css_class("card")
        config_card.add_css_class("power-card")

        duration_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        duration_title = Gtk.Label(label="Durée")
        duration_title.add_css_class("title-4")
        duration_title.set_xalign(0.0)
        duration_header.append(duration_title)

        duration_help = Gtk.Label(label="Saisissez un nombre entier de minutes.")
        duration_help.add_css_class("dim-label")
        duration_help.set_wrap(True)
        duration_help.set_xalign(0.0)
        duration_header.append(duration_help)
        config_card.append(duration_header)

        duration_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.duration_spin = Gtk.SpinButton()
        adjustment = Gtk.Adjustment()
        adjustment.set_lower(0)
        adjustment.set_upper(10080)
        adjustment.set_step_increment(1)
        adjustment.set_page_increment(15)
        adjustment.set_page_size(0)
        adjustment.set_value(30)
        self.duration_spin.set_adjustment(adjustment)
        self.duration_spin.set_digits(0)
        self.duration_spin.set_numeric(True)
        self.duration_spin.set_width_chars(5)
        self.duration_spin.set_value(30)
        self.duration_spin.connect("value-changed", self._on_duration_changed)
        duration_row.append(self.duration_spin)

        quick_grid = Gtk.Grid()
        quick_grid.set_hexpand(True)
        quick_grid.set_column_homogeneous(True)
        quick_grid.set_row_spacing(6)
        quick_grid.set_column_spacing(6)

        for index, minutes in enumerate(QUICK_DURATION_MINUTES):
            label = format_human_delay(minutes * 60)
            button = Gtk.Button(label=label)
            button.add_css_class("quick-button")
            button.add_css_class("pill")
            button.set_hexpand(True)
            button.connect("clicked", self._set_duration_from_quick_button, minutes)
            quick_grid.attach(button, index % 4, index // 4, 1, 1)
            self._quick_buttons.append(button)
        duration_row.append(quick_grid)
        config_card.append(duration_row)

        mode_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        mode_title = Gtk.Label(label="Mode")
        mode_title.add_css_class("title-4")
        mode_title.set_xalign(0.0)
        mode_header.append(mode_title)

        mode_help = Gtk.Label(label="Les modes restent sélectionnables. Si les droits manquent, Démarrer peut relancer l'application en root.")
        mode_help.add_css_class("dim-label")
        mode_help.set_wrap(True)
        mode_help.set_xalign(0.0)
        mode_header.append(mode_help)
        config_card.append(mode_header)

        mode_grid = Gtk.Grid()
        mode_grid.set_row_spacing(6)
        mode_grid.set_column_spacing(6)
        mode_grid.set_column_homogeneous(True)
        mode_grid.set_hexpand(True)

        mode_positions = {
            "shutdown": (0, 0, 1, 1),
            "reboot": (1, 0, 1, 1),
            "suspend": (2, 0, 1, 1),
            "hibernate": (0, 1, 1, 1),
            "hybrid": (1, 1, 2, 1),
        }

        for key in MODE_ORDER:
            button = self._create_mode_button(MODE_SPECS[key])
            self._mode_buttons[key] = button
            column, row, width, height = mode_positions[key]
            mode_grid.attach(button, column, row, width, height)

        config_card.append(mode_grid)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_halign(Gtk.Align.CENTER)

        self.start_button = Gtk.Button(label="Démarrer")
        self.start_button.add_css_class("suggested-action")
        self.start_button.add_css_class("pill")
        self.start_button.connect("clicked", self._on_start_clicked)
        action_row.append(self.start_button)

        self.cancel_button = Gtk.Button(label="Annuler")
        self.cancel_button.add_css_class("destructive-action")
        self.cancel_button.add_css_class("pill")
        self.cancel_button.set_sensitive(False)
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        action_row.append(self.cancel_button)

        config_card.append(action_row)

        permissions_note = Gtk.Label(
            label="Les commandes système utilisent sudo sans mot de passe, ou un lancement direct en root."
        )
        permissions_note.add_css_class("dim-label")
        permissions_note.set_wrap(True)
        permissions_note.set_justify(Gtk.Justification.CENTER)
        permissions_note.set_xalign(0.5)
        config_card.append(permissions_note)

        content.append(config_card)

    def _build_header_bar(self) -> Adw.HeaderBar:
        header_bar = Adw.HeaderBar()
        header_bar.set_hexpand(True)
        header_bar.set_show_start_title_buttons(False)
        header_bar.set_show_end_title_buttons(True)

        title = Adw.WindowTitle()
        title.set_title(APP_NAME)
        title.set_subtitle("Mode root actif" if self._root_instance else "Sélectionnez un mode et une durée")
        header_bar.set_title_widget(title)

        root_button = self._create_header_tool_button(
            "security-high-symbolic",
            "Ouvrir une instance root",
            self._on_root_clicked,
            label_text="Root actif" if self._root_instance else "Root",
        )
        self._root_button = root_button
        root_button.add_css_class("header-root-button")
        root_button.set_sensitive(not self._root_instance)
        if self._root_instance:
            root_button.set_tooltip_text("Vous êtes déjà dans l'instance root")
        header_bar.pack_start(root_button)

        menu_button = Gtk.MenuButton()
        menu_button.add_css_class("flat")
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Menu de l'application")
        menu_button.set_menu_model(self._build_app_menu())
        header_bar.pack_start(menu_button)

        return header_bar

    def _create_header_tool_button(
        self,
        icon_name: str,
        tooltip_text: str,
        callback,
        label_text: Optional[str] = None,
    ) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("flat")
        button.add_css_class("header-tool-button")
        button.set_tooltip_text(tooltip_text)

        if label_text is None:
            button.set_child(Gtk.Image.new_from_icon_name(icon_name))
        else:
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            content.set_halign(Gtk.Align.CENTER)

            icon = Gtk.Image.new_from_icon_name(icon_name)
            content.append(icon)

            label = Gtk.Label(label=label_text)
            label.set_xalign(0.0)
            content.append(label)

            button.set_child(content)

        button.connect("clicked", callback)
        return button

    def _build_app_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Revenir à la taille compacte", "app.restore-window")
        menu.append("Maximiser", "app.maximize-window")
        menu.append("Plein écran", "app.fullscreen-window")
        menu.append("À propos", "app.about")
        menu.append("Quitter", "app.quit")
        return menu

    def _restore_compact_window_size(self, _button: Gtk.Button) -> None:
        self.unfullscreen()
        self.unmaximize()
        self.set_default_size(*WINDOW_COMPACT_SIZE)

    def _maximize_window(self, _button: Gtk.Button) -> None:
        self.unfullscreen()
        self.maximize()

    def _enter_fullscreen(self, _button: Gtk.Button) -> None:
        self.fullscreen()

    def _request_root_instance(self, mode_key: str, duration_minutes: int, auto_start: bool) -> bool:
        app = self.get_application()
        if not isinstance(app, PowerTimerApplication):
            return False
        return app.launch_root_instance(mode_key, duration_minutes, auto_start)

    def _on_root_clicked(self, _button: Gtk.Button) -> None:
        if self._root_instance:
            return

        if self._request_root_instance(self._selected_mode, int(self.duration_spin.get_value()), auto_start=False):
            self._show_toast("Demande d'authentification root envoyée.")
            self.status_label.set_label("Demande d'authentification root envoyée.")
        else:
            self._show_error("Impossible d'ouvrir la demande root.")

    def _on_root_transition_signal(self) -> bool:
        if self._root_transition_hidden:
            self.present()
            self._root_transition_hidden = False
        elif self.get_visible():
            self.set_visible(False)
            self._root_transition_hidden = True
        return True

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self._root_instance:
            return False

        app = self.get_application()
        if isinstance(app, PowerTimerApplication) and app.has_tray_helper():
            self.set_visible(False)
            return True

        return False

    def _monitor_window_state(self) -> bool:
        if self._root_instance:
            return True

        app = self.get_application()
        if not isinstance(app, PowerTimerApplication) or not app.has_tray_helper():
            return True

        if not self.get_visible():
            return True

        surface = self.get_surface()
        if surface is None:
            return True

        try:
            state = surface.get_state()
        except Exception:
            return True

        if state & Gdk.ToplevelState.MINIMIZED:
            self.set_visible(False)

        return True

    def _auto_start_after_activation(self) -> bool:
        if not self._auto_start_requested:
            return False

        self._auto_start_requested = False
        if self._mode_hardware_supported.get(self._selected_mode, False) and int(self.duration_spin.get_value()) > 0:
            self._on_start_clicked(self.start_button)
        else:
            self._show_error("Le démarrage automatique est impossible avec l'état initial actuel.")
        return False

    def _create_mode_button(self, spec: ModeSpec) -> Gtk.ToggleButton:
        button = Gtk.ToggleButton()
        button.add_css_class("mode-pill")
        button.add_css_class("pill")
        button.set_hexpand(True)
        button.set_halign(Gtk.Align.FILL)
        button.set_tooltip_text(spec.subtitle)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        layout.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name(spec.icon_name)
        icon.set_pixel_size(16)
        layout.append(icon)

        title = Gtk.Label(label=spec.label)
        title.add_css_class("heading")
        title.set_xalign(0.5)
        layout.append(title)

        button.set_child(layout)
        button.connect("toggled", self._on_mode_toggled, spec.key)
        return button

    def _refresh_mode_support(self) -> None:
        power_state_tokens: set[str] = set()
        try:
            power_state_tokens = set(Path("/sys/power/state").read_text(encoding="utf-8").split())
        except OSError:
            power_state_tokens = set()

        suspend_supported = "mem" in power_state_tokens or "freeze" in power_state_tokens
        hibernate_supported = "disk" in power_state_tokens
        hybrid_supported = suspend_supported and hibernate_supported
        self._permission_allowed = self._is_root() or self._passwordless_sudo_available

        self._mode_hardware_supported = {
            "shutdown": self._systemctl_path is not None,
            "reboot": self._systemctl_path is not None,
            "suspend": self._systemctl_path is not None and suspend_supported,
            "hibernate": self._systemctl_path is not None and hibernate_supported,
            "hybrid": self._systemctl_path is not None and hybrid_supported,
        }

        for key, button in self._mode_buttons.items():
            button.set_sensitive(self._active_session is None)

        note_parts: list[str] = []
        if not self._permission_allowed:
            if any(self._mode_hardware_supported.values()):
                note_parts.append("L'authentification root est requise pour lancer une action système. Utilisez le bouton Root du header ou cliquez sur Démarrer.")
            else:
                note_parts.append("Aucune action système utilisable n'est disponible sur cette machine.")
        if self._systemctl_path is None:
            note_parts.append("systemctl est introuvable.")
        if not suspend_supported:
            note_parts.append("La veille n'est pas signalée par le noyau.")
        if not hibernate_supported:
            note_parts.append("La veille prolongée n'est pas prise en charge sur cette machine.")
        if not hybrid_supported:
            note_parts.append("La veille hybride n'est pas prise en charge sur cette machine.")

        self.note_label.set_label("  •  ".join(note_parts))
        self.note_label.set_visible(bool(note_parts))

        if not self._mode_hardware_supported.get(self._selected_mode, False):
            self._selected_mode = self._choose_initial_mode()
            self._sync_mode_buttons(self._selected_mode)

        self._update_start_button_state()

    def _choose_initial_mode(self) -> str:
        for key in MODE_ORDER:
            if self._mode_hardware_supported.get(key, False):
                return key
        return MODE_ORDER[0]

    def _on_mode_toggled(self, button: Gtk.ToggleButton, mode_key: str) -> None:
        if self._updating_mode_buttons or self._active_session is not None:
            return

        if not button.get_active():
            if mode_key == self._selected_mode:
                self._updating_mode_buttons = True
                button.set_active(True)
                self._updating_mode_buttons = False
            return

        self._selected_mode = mode_key
        self._sync_mode_buttons(mode_key)
        self._update_idle_preview()
        self._update_start_button_state()

    def _sync_mode_buttons(self, selected_key: str) -> None:
        self._updating_mode_buttons = True
        for key, button in self._mode_buttons.items():
            button.set_active(key == selected_key)
            button.set_sensitive(self._active_session is None)
        self._updating_mode_buttons = False
        self._update_mode_summary()

    def _set_duration_from_quick_button(self, _button: Gtk.Button, minutes: int) -> None:
        if self._active_session is not None:
            return
        self.duration_spin.set_value(minutes)
        self._update_idle_preview()
        self._update_start_button_state()

    def _on_duration_changed(self, _spin_button: Gtk.SpinButton) -> None:
        if self._active_session is None:
            self._update_idle_preview()
            self._update_start_button_state()

    def _update_mode_summary(self) -> None:
        spec = MODE_SPECS[self._selected_mode]
        self.mode_icon.set_from_icon_name(spec.icon_name)
        self.mode_label.set_label(spec.label)
        self.mode_hint_label.set_label(spec.subtitle)

    def _update_idle_preview(self) -> None:
        self._update_mode_summary()

        duration_minutes = int(self.duration_spin.get_value())
        if duration_minutes <= 0:
            self.countdown_label.set_label("00:00")
            self.summary_label.set_label("La durée doit être supérieure à zéro.")
            self.status_label.set_label("Prêt à démarrer.")
            self.progress_bar.set_fraction(0.0)
            return

        total_seconds = duration_minutes * 60
        self.countdown_label.set_label(format_mmss(total_seconds))
        spec = MODE_SPECS[self._selected_mode]
        self.summary_label.set_label(f"{spec.label} dans {format_human_delay(total_seconds)}")
        self.status_label.set_label("Prêt à démarrer.")
        self.progress_bar.set_fraction(0.0)

    def _update_running_preview(self, remaining_seconds: int, total_seconds: int) -> None:
        remaining_seconds = max(0, remaining_seconds)
        total_seconds = max(1, total_seconds)
        spec = MODE_SPECS[self._active_session.mode_key] if self._active_session else MODE_SPECS[self._selected_mode]
        self.countdown_label.set_label(format_mmss(remaining_seconds))
        self.summary_label.set_label(f"{spec.label} dans {format_human_delay(remaining_seconds)}")
        elapsed_fraction = 1.0 - (remaining_seconds / total_seconds)
        self.progress_bar.set_fraction(max(0.0, min(1.0, elapsed_fraction)))

    def _update_start_button_state(self) -> None:
        duration_minutes = int(self.duration_spin.get_value())
        has_active_session = self._active_session is not None
        
        if has_active_session:
            self.start_button.set_sensitive(False)
            self.cancel_button.set_sensitive(True)
            return

        can_start = duration_minutes > 0 and self._mode_hardware_supported.get(self._selected_mode, False)
        self.start_button.set_sensitive(can_start)
        self.cancel_button.set_sensitive(False)

    def _set_running_state(self, running: bool) -> None:
        self.duration_spin.set_sensitive(not running)
        for button in self._quick_buttons:
            button.set_sensitive(not running)
        for key, button in self._mode_buttons.items():
            button.set_sensitive(not running)
        if self._root_button is not None:
            self._root_button.set_sensitive((not running) and (not self._root_instance))
        self._update_start_button_state()

    def _on_start_clicked(self, _button: Gtk.Button) -> None:
        if self._active_session is not None:
            self._show_error("Une action est déjà en cours. Annulez-la d'abord.")
            return

        duration_minutes = int(self.duration_spin.get_value())
        if duration_minutes <= 0:
            self._show_error("La durée doit être supérieure à zéro.")
            return

        hardware_supported = self._mode_hardware_supported.get(self._selected_mode, False)
        if not hardware_supported:
            self._show_error("Le mode sélectionné n'est pas disponible sur cette machine.")
            return

        if not self._permission_allowed:
            if self._request_root_instance(self._selected_mode, duration_minutes, auto_start=True):
                self._show_toast("Demande d'authentification root envoyée.")
                self.status_label.set_label("Demande d'authentification root envoyée.")
            else:
                self._show_error("Impossible de demander l'élévation root.")
            return

        total_seconds = duration_minutes * 60
        session = TimerSession(
            mode_key=self._selected_mode,
            duration_minutes=duration_minutes,
            total_seconds=total_seconds,
            deadline=time.monotonic() + total_seconds,
            system_scheduled=MODE_SPECS[self._selected_mode].system_scheduled,
        )

        if session.system_scheduled:
            scheduled_command = self._build_scheduled_command(session.duration_minutes, session.mode_key)
            ok, error_text = self._run_command(scheduled_command)
            if not ok:
                self._show_error(self._friendly_command_error(session.mode_key, error_text))
                return

        self._active_session = session
        self._set_running_state(True)
        self._update_running_preview(total_seconds, total_seconds)
        self.status_label.set_label(self._running_status_text(session.mode_key, total_seconds))
        self._show_toast(f"{MODE_SPECS[session.mode_key].label} programmée dans {format_human_delay(total_seconds)}.")

        if self._tick_source_id is None:
            self._tick_source_id = GLib.timeout_add_seconds(1, self._on_tick)

    def _on_cancel_clicked(self, _button: Gtk.Button) -> None:
        if self._active_session is None:
            self._show_error("Aucune action n'est en cours à annuler.")
            return

        session = self._active_session
        if session.system_scheduled:
            cancel_command = self._build_cancel_command()
            ok, error_text = self._run_command(cancel_command)
            if not ok:
                self._show_error(self._friendly_cancel_error(error_text))
                return

        self._finish_active_session("Minuteur annulé.", "Minuteur annulé.")

    def _on_tick(self) -> bool:
        session = self._active_session
        if session is None:
            self._tick_source_id = None
            return False

        remaining_seconds = max(0, math.ceil(session.deadline - time.monotonic()))
        self._update_running_preview(remaining_seconds, session.total_seconds)
        self._maybe_send_notifications(session, remaining_seconds)

        if remaining_seconds > 0:
            self.status_label.set_label(self._running_status_text(session.mode_key, remaining_seconds))
            return True

        if session.system_scheduled:
            self._finish_active_session(
                f"{MODE_SPECS[session.mode_key].label} transmise au système.",
                f"{MODE_SPECS[session.mode_key].label} déclenchée.",
            )
            return False

        ok, error_text = self._run_command(self._build_immediate_command(session.mode_key))
        if not ok:
            self._abort_active_session(self._friendly_command_error(session.mode_key, error_text))
            return False

        self._finish_active_session(
            f"{MODE_SPECS[session.mode_key].label} envoyée.",
            f"{MODE_SPECS[session.mode_key].label} exécutée.",
        )
        return False

    def _maybe_send_notifications(self, session: TimerSession, remaining_seconds: int) -> None:
        if not session.warning_5_sent and session.total_seconds > 300 and remaining_seconds <= 300:
            session.warning_5_sent = True
            self._send_notification(
                "Power Timer",
                f"{MODE_SPECS[session.mode_key].label} dans 5 minutes.",
                "power-timer-warning-5",
            )
        if not session.warning_1_sent and session.total_seconds > 60 and remaining_seconds <= 60:
            session.warning_1_sent = True
            self._send_notification(
                "Power Timer",
                f"{MODE_SPECS[session.mode_key].label} dans 1 minute.",
                "power-timer-warning-1",
            )

    def _running_status_text(self, mode_key: str, remaining_seconds: int) -> str:
        label = MODE_SPECS[mode_key].label
        delay = format_human_delay(max(0, remaining_seconds))
        if self._active_session and self._active_session.system_scheduled:
            return f"{label} déjà programmée par le système. Annulation possible tant que le minuteur est actif."
        return f"{label} dans {delay}."

    def _finish_active_session(self, status_text: str, toast_text: str) -> None:
        self._stop_tick()
        self._active_session = None
        self._set_running_state(False)
        self._update_idle_preview()
        self.status_label.set_label(status_text)
        self._show_toast(toast_text)

    def _abort_active_session(self, error_text: str) -> None:
        self._stop_tick()
        self._active_session = None
        self._set_running_state(False)
        self._update_idle_preview()
        self._show_error(error_text)

    def _stop_tick(self) -> None:
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None

    def _build_scheduled_command(self, duration_minutes: int, mode_key: str) -> list[str]:
        prefix = self._privileged_prefix()
        if prefix is None:
            raise RuntimeError("sudo n'est pas disponible.")

        shutdown_path = self._shutdown_path or "shutdown"
        if mode_key == "shutdown":
            return [*prefix, shutdown_path, "--check-inhibitors=no", "-h", f"+{duration_minutes}"]
        if mode_key == "reboot":
            return [*prefix, shutdown_path, "--check-inhibitors=no", "-r", f"+{duration_minutes}"]
        raise ValueError(f"Mode de commande système inattendu: {mode_key}")

    def _build_immediate_command(self, mode_key: str) -> list[str]:
        prefix = self._privileged_prefix()
        if prefix is None:
            raise RuntimeError("sudo n'est pas disponible.")

        systemctl_path = self._systemctl_path or "systemctl"
        if mode_key == "shutdown":
            return [*prefix, systemctl_path, "--check-inhibitors=no", "poweroff"]
        if mode_key == "reboot":
            return [*prefix, systemctl_path, "--check-inhibitors=no", "reboot"]
        if mode_key == "suspend":
            return [*prefix, systemctl_path, "--check-inhibitors=no", "suspend"]
        if mode_key == "hibernate":
            return [*prefix, systemctl_path, "--check-inhibitors=no", "hibernate"]
        if mode_key == "hybrid":
            return [*prefix, systemctl_path, "--check-inhibitors=no", "hybrid-sleep"]
        raise ValueError(f"Mode d'action immédiate inattendu: {mode_key}")

    def _build_cancel_command(self) -> list[str]:
        prefix = self._privileged_prefix()
        if prefix is None:
            raise RuntimeError("sudo n'est pas disponible.")
        shutdown_path = self._shutdown_path or "shutdown"
        return [*prefix, shutdown_path, "-c"]

    def _privileged_prefix(self) -> Optional[list[str]]:
        if self._is_root():
            return []
        if self._passwordless_sudo_available and self._sudo_path is not None:
            return [self._sudo_path, "-n"]
        return None

    def _run_command(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            return False, str(exc)
        except OSError as exc:
            return False, str(exc)

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"code de retour {result.returncode}"
            return False, message
        return True, ""

    def _friendly_command_error(self, mode_key: str, raw_error: str) -> str:
        error = raw_error.strip()
        lowered = error.lower()

        if "not found" in lowered or "no such file" in lowered:
            return f"La commande requise pour {MODE_SPECS[mode_key].label.lower()} est introuvable."
        if "password" in lowered or "permission denied" in lowered or "not allowed" in lowered:
            return "Permission refusée. Vérifiez les règles sudoers ou lancez l'application en root."
        if not error:
            return f"Le système a refusé {MODE_SPECS[mode_key].label.lower()}."
        return f"Le système a refusé {MODE_SPECS[mode_key].label.lower()}: {error}"

    def _friendly_cancel_error(self, raw_error: str) -> str:
        error = raw_error.strip()
        if not error:
            return "Impossible d'annuler la commande système."
        lowered = error.lower()
        if "password" in lowered or "permission denied" in lowered:
            return "Annulation refusée. Vérifiez sudoers ou exécutez l'application en root."
        return f"Impossible d'annuler la commande système: {error}"

    def _show_error(self, message: str) -> None:
        self.status_label.set_label(message)
        toast = Adw.Toast.new(message)
        toast.set_timeout(5)
        self._toast_overlay.add_toast(toast)

    def _show_toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self._toast_overlay.add_toast(toast)

    def _send_notification(self, title: str, body: str, notification_id: str) -> None:
        app = self.get_application()
        if not isinstance(app, Gio.Application):
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        app.send_notification(notification_id, notification)

    def _is_root(self) -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def _can_use_passwordless_sudo(self) -> bool:
        if self._is_root():
            return True
        if self._sudo_path is None:
            return False

        try:
            result = subprocess.run(
                [self._sudo_path, "-n", "true"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False

        return result.returncode == 0


class PowerTimerApplication(Adw.Application):
    def __init__(self) -> None:
        self._root_instance_requested = os.environ.get(ROOT_INSTANCE_ENV) == "1"
        self._force_non_unique = os.environ.get(FORCE_NON_UNIQUE_ENV) == "1"
        self._start_hidden = os.environ.get(START_HIDDEN_ENV) == "1"
        self._show_window_requested = False
        self._origin_pid = parse_positive_int_env(ORIGIN_PID_ENV)
        self._initial_mode = os.environ.get(INITIAL_MODE_ENV)
        self._initial_duration_minutes = parse_positive_int_env(INITIAL_DURATION_ENV)
        self._auto_start_requested = os.environ.get(AUTO_START_ENV) == "1"
        application_flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if self._root_instance_requested or self._force_non_unique:
            application_flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=application_flags)
        self._css_provider = Gtk.CssProvider()
        self._css_installed = False
        self._tray_helper_process: Optional[subprocess.Popen] = None
        self.add_main_option("quit", ord("q"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Quitter l'application", None)
        self.add_main_option("show-window", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Afficher la fenêtre principale", None)
        self._install_actions()
        self.set_accels_for_action("app.about", ["F1"])
        self.set_accels_for_action("app.fullscreen-window", ["F11"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()

        if options.lookup_value("quit", None) is not None:
            self._stop_tray_helper()
            self.quit()
            command_line.set_exit_status(0)
            return 0

        self._show_window_requested = options.lookup_value("show-window", None) is not None

        self.activate()
        command_line.set_exit_status(0)
        return 0

    def do_activate(self) -> None:
        self._install_css()

        window = self.get_active_window()
        if not isinstance(window, PowerTimerWindow):
            window = PowerTimerWindow(
                self,
                initial_mode=self._initial_mode,
                initial_duration_minutes=self._initial_duration_minutes,
                auto_start_requested=self._auto_start_requested,
            )

        tray_started = False
        if not self._root_instance_requested:
            tray_started = self._ensure_tray_helper()

        should_present = self._root_instance_requested or self._show_window_requested or not self._start_hidden or not tray_started
        if should_present:
            window.present()

        if self._root_instance_requested and self._origin_pid is not None:
            self._hide_origin_instance()

        self._show_window_requested = False

    def launch_root_instance(self, mode_key: str, duration_minutes: int, auto_start: bool) -> bool:
        launcher_command = self._resolve_launcher_command()
        if launcher_command is None:
            return False

        env = os.environ.copy()
        env[ROOT_REQUEST_ENV] = "1"
        env[ROOT_INSTANCE_ENV] = "1"
        env[INITIAL_MODE_ENV] = mode_key
        env[INITIAL_DURATION_ENV] = str(max(1, duration_minutes))
        env[ORIGIN_PID_ENV] = str(os.getpid())
        if auto_start:
            env[AUTO_START_ENV] = "1"
        else:
            env.pop(AUTO_START_ENV, None)

        try:
            subprocess.Popen(
                launcher_command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

        return True

    def _resolve_launcher_command(self) -> Optional[list[str]]:
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

    def _resolve_tray_helper_path(self) -> Optional[Path]:
        tray_helper = Path(__file__).resolve().with_name("tray_helper.py")
        if tray_helper.exists():
            return tray_helper
        return None

    def _hide_origin_instance(self) -> None:
        if self._origin_pid is None:
            return

        try:
            os.kill(self._origin_pid, signal.SIGUSR1)
        except (ProcessLookupError, OSError):
            pass

    def _ensure_tray_helper(self) -> bool:
        if self._tray_helper_process is not None and self._tray_helper_process.poll() is None:
            return True

        helper_path = self._resolve_tray_helper_path()
        if helper_path is None:
            return False

        try:
            probe = subprocess.run(
                [sys.executable, str(helper_path), "--probe"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False

        if probe.returncode != 0:
            return False

        try:
            self._tray_helper_process = subprocess.Popen(
                [sys.executable, str(helper_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._tray_helper_process = None
            return False

        return self._tray_helper_process is not None and self._tray_helper_process.poll() is None

    def has_tray_helper(self) -> bool:
        return self._tray_helper_process is not None and self._tray_helper_process.poll() is None

    def _stop_tray_helper(self) -> None:
        if self._tray_helper_process is None:
            return

        if self._tray_helper_process.poll() is None:
            self._tray_helper_process.terminate()
            try:
                self._tray_helper_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._tray_helper_process.kill()
                self._tray_helper_process.wait(timeout=1)

        self._tray_helper_process = None

    def _install_actions(self) -> None:
        restore_action = Gio.SimpleAction.new("restore-window", None)
        restore_action.connect("activate", self._on_restore_window_action)
        self.add_action(restore_action)

        maximize_action = Gio.SimpleAction.new("maximize-window", None)
        maximize_action.connect("activate", self._on_maximize_window_action)
        self.add_action(maximize_action)

        fullscreen_action = Gio.SimpleAction.new("fullscreen-window", None)
        fullscreen_action.connect("activate", self._on_fullscreen_window_action)
        self.add_action(fullscreen_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about_action)
        self.add_action(about_action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit_action)
        self.add_action(quit_action)

    def _on_about_action(self, _action: Gio.SimpleAction, _parameter: Optional[GLib.Variant]) -> None:
        window = self.get_active_window()
        about = Adw.AboutWindow()
        about.set_application_name(APP_NAME)
        about.set_application_icon("power-timer")
        about.set_version(APP_VERSION)
        about.set_developer_name("Power Timer Maintainers")
        if isinstance(window, Gtk.Window):
            about.set_transient_for(window)
        about.present()

    def _on_restore_window_action(self, _action: Gio.SimpleAction, _parameter: Optional[GLib.Variant]) -> None:
        window = self.get_active_window()
        if isinstance(window, PowerTimerWindow):
            window._restore_compact_window_size(None)

    def _on_maximize_window_action(self, _action: Gio.SimpleAction, _parameter: Optional[GLib.Variant]) -> None:
        window = self.get_active_window()
        if isinstance(window, PowerTimerWindow):
            window._maximize_window(None)

    def _on_fullscreen_window_action(self, _action: Gio.SimpleAction, _parameter: Optional[GLib.Variant]) -> None:
        window = self.get_active_window()
        if isinstance(window, PowerTimerWindow):
            window._enter_fullscreen(None)

    def _on_quit_action(self, _action: Gio.SimpleAction, _parameter: Optional[GLib.Variant]) -> None:
        self.quit()

    def do_shutdown(self) -> None:
        if self._root_instance_requested and self._origin_pid is not None:
            try:
                os.kill(self._origin_pid, signal.SIGUSR1)
            except (ProcessLookupError, OSError):
                pass

        self._stop_tray_helper()
        Gio.Application.do_shutdown(self)

    def _install_css(self) -> None:
        if self._css_installed:
            return

        self._css_provider.load_from_data(APP_CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._css_installed = True


def main() -> int:
    configure_application_identity()
    app = PowerTimerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
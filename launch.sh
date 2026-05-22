#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${POWER_TIMER_APP_PATH:-}" ]]; then
    APP_PATH="${POWER_TIMER_APP_PATH}"
else
    APP_PATH="${ROOT_DIR}/app.py"
    if [[ ! -f "${APP_PATH}" ]]; then
        APP_PATH="/usr/share/power-timer/app.py"
    fi
fi

REQUIRE_ROOT_AUTH=0
if [[ "${POWER_TIMER_ROOT_REQUEST:-0}" == "1" ]]; then
    REQUIRE_ROOT_AUTH=1
fi

if [[ "${POWER_TIMER_ROOT_INSTANCE:-0}" == "1" ]]; then
    REQUIRE_ROOT_AUTH=1
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "Aucun interpréteur Python n'a été trouvé." >&2
    exit 1
fi

POWER_TIMER_ENV_NAMES=(
    POWER_TIMER_ROOT_REQUEST
    POWER_TIMER_ROOT_INSTANCE
    POWER_TIMER_ORIGIN_PID
    POWER_TIMER_AUTO_START
    POWER_TIMER_INITIAL_MODE
    POWER_TIMER_INITIAL_DURATION
    POWER_TIMER_FORCE_NON_UNIQUE
    POWER_TIMER_START_HIDDEN
)

POWER_TIMER_ENV_ARGS=()
for env_name in "${POWER_TIMER_ENV_NAMES[@]}"; do
    if [[ -n "${!env_name:-}" ]]; then
        POWER_TIMER_ENV_ARGS+=("${env_name}=${!env_name}")
    fi
done

for argument in "$@"; do
    if [[ "${argument}" == "--quit" || "${argument}" == "--show-window" ]]; then
        exec "${PYTHON_BIN}" "${APP_PATH}" "$@"
    fi
done

launch_app() {
    exec "${PYTHON_BIN}" "${APP_PATH}" "$@"
}

launch_with_sudo_askpass() {
    if ! command -v sudo >/dev/null 2>&1 || ! command -v zenity >/dev/null 2>&1; then
        return 1
    fi

    local askpass_script
    askpass_script="$(mktemp "${TMPDIR:-/tmp}/power-timer-askpass.XXXXXX")"
    cat > "${askpass_script}" <<'EOF'
#!/usr/bin/env bash
zenity --password --title="Power Timer" --text="Saisissez le mot de passe root pour lancer Power Timer."
EOF
    chmod 700 "${askpass_script}"

    if SUDO_ASKPASS="${askpass_script}" sudo -A env \
        "${POWER_TIMER_ENV_ARGS[@]}" \
        DISPLAY="${DISPLAY:-}" \
        XAUTHORITY="${XAUTHORITY:-}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
        DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
        "${PYTHON_BIN}" "${APP_PATH}" "$@" >/dev/null 2>&1; then
        rm -f "${askpass_script}"
        exit 0
    fi

    rm -f "${askpass_script}"
    return 1
}

launch_with_root_auth() {
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
        launch_app "$@"
    fi

    if command -v pkexec >/dev/null 2>&1; then
        local pkexec_path
        pkexec_path="$(command -v pkexec)"
        if [[ -u "${pkexec_path}" ]]; then
            if pkexec env \
                "${POWER_TIMER_ENV_ARGS[@]}" \
                DISPLAY="${DISPLAY:-}" \
                XAUTHORITY="${XAUTHORITY:-}" \
                WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
                XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
                DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
                "${PYTHON_BIN}" "${APP_PATH}" "$@" >/dev/null 2>&1; then
                return 0
            fi

            return 1
        fi
    fi

    if launch_with_sudo_askpass "$@"; then
        return 0
    fi

    return 1
}

if [[ ${REQUIRE_ROOT_AUTH} -eq 1 ]]; then
    if launch_with_root_auth "$@"; then
        exit 0
    fi

    echo "Authentification root refusée ou indisponible." >&2
    exit 1
fi

launch_app "$@"
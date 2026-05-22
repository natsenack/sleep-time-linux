#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DEB="${ROOT_DIR}/build/power-timer_1.0.0_all.deb"
DEB_PATH="${1:-${DEFAULT_DEB}}"

SUDO_PREFIX=()
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_PREFIX=(sudo)
    else
        echo "sudo n'est pas disponible et le script n'est pas lancé en root." >&2
        exit 1
    fi
fi

if [[ ! -f "${DEB_PATH}" ]]; then
    echo "Fichier .deb introuvable: ${DEB_PATH}" >&2
    exit 1
fi

TEMP_DIR=""
STAGED_DEB_PATH="${DEB_PATH}"

stage_deb_for_apt() {
    TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/power-timer-deb.XXXXXX")"
    STAGED_DEB_PATH="${TEMP_DIR}/$(basename "${DEB_PATH}")"
    cp -f "${DEB_PATH}" "${STAGED_DEB_PATH}"
    chmod 644 "${STAGED_DEB_PATH}"
}

cleanup_staged_deb() {
    if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
        rm -rf "${TEMP_DIR}"
    fi
}

trap cleanup_staged_deb EXIT

install_deb() {
    if command -v apt >/dev/null 2>&1; then
        stage_deb_for_apt
        "${SUDO_PREFIX[@]}" apt install -y "${STAGED_DEB_PATH}"
        return 0
    fi

    if command -v dpkg >/dev/null 2>&1; then
        "${SUDO_PREFIX[@]}" dpkg -i "${DEB_PATH}"
        if command -v apt-get >/dev/null 2>&1; then
            "${SUDO_PREFIX[@]}" apt-get -f install -y
        fi
        return 0
    fi

    echo "Ni apt ni dpkg ne sont disponibles sur ce système." >&2
    exit 1
}

install_deb

cleanup_staged_deb

if command -v power-timer >/dev/null 2>&1; then
    exec power-timer
fi

echo "Le paquet a été installé, mais la commande power-timer n'a pas été trouvée." >&2
exit 1
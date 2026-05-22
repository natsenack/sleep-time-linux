#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_NAME="power-timer"
VERSION="1.0.0"
ARCH="all"
BUILD_DIR="${ROOT_DIR}/build"
STAGING_DIR="${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}"
DEB_PATH="${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"

if [[ ! -f "${ROOT_DIR}/app.py" ]]; then
    echo "app.py est introuvable" >&2
    exit 1
fi

if [[ ! -f "${ROOT_DIR}/tray_helper.py" ]]; then
    echo "tray_helper.py est introuvable" >&2
    exit 1
fi

if [[ ! -f "${ROOT_DIR}/data/power-timer.desktop" ]]; then
    echo "Le fichier desktop est introuvable" >&2
    exit 1
fi

if [[ ! -f "${ROOT_DIR}/data/icons/power-timer.png" ]]; then
    echo "L'icône est introuvable" >&2
    exit 1
fi

rm -rf "${STAGING_DIR}" "${DEB_PATH}"
mkdir -p \
    "${STAGING_DIR}/DEBIAN" \
    "${STAGING_DIR}/usr/bin" \
    "${STAGING_DIR}/usr/share/power-timer" \
    "${STAGING_DIR}/usr/share/applications" \
    "${STAGING_DIR}/usr/share/icons/hicolor/256x256/apps"

install -m 755 "${ROOT_DIR}/launch.sh" "${STAGING_DIR}/usr/bin/power-timer"
install -m 644 "${ROOT_DIR}/app.py" "${STAGING_DIR}/usr/share/power-timer/app.py"
install -m 644 "${ROOT_DIR}/tray_helper.py" "${STAGING_DIR}/usr/share/power-timer/tray_helper.py"
install -m 644 "${ROOT_DIR}/data/power-timer.desktop" "${STAGING_DIR}/usr/share/applications/power-timer.desktop"
install -m 644 "${ROOT_DIR}/data/icons/power-timer.png" "${STAGING_DIR}/usr/share/icons/hicolor/256x256/apps/power-timer.png"
install -m 755 "${ROOT_DIR}/debian/postinst" "${STAGING_DIR}/DEBIAN/postinst"

cat > "${STAGING_DIR}/DEBIAN/control" <<EOF
Package: power-timer
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: Power Timer Maintainers <maintainer@example.com>
Depends: python3, python3-gi, python3-setproctitle, zenity, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1
Description: GNOME timer for system power actions
 Power Timer is a GTK4 and libadwaita application for scheduling shutdown,
 restart, suspend, hibernate and hybrid sleep actions from a modern GNOME UI.
EOF

dpkg-deb --root-owner-group --build "${STAGING_DIR}" "${DEB_PATH}"
echo "Package generated: ${DEB_PATH}"

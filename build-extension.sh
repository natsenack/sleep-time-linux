#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_UUID="power-timer@natsenack.github.io"
BUILD_DIR="${ROOT_DIR}/build"
STAGING_DIR="${BUILD_DIR}/${EXTENSION_UUID}"
ZIP_PATH="${BUILD_DIR}/${EXTENSION_UUID}.zip"

rm -rf "${STAGING_DIR}" "${ZIP_PATH}"
mkdir -p "${STAGING_DIR}"

install -m 644 "${ROOT_DIR}/metadata.json" "${STAGING_DIR}/metadata.json"
install -m 644 "${ROOT_DIR}/extension.js" "${STAGING_DIR}/extension.js"

for optional_file in LICENSE prefs.js stylesheet.css; do
    if [[ -f "${ROOT_DIR}/${optional_file}" ]]; then
        install -m 644 "${ROOT_DIR}/${optional_file}" "${STAGING_DIR}/${optional_file}"
    fi
done

for optional_dir in schemas locale; do
    if [[ -d "${ROOT_DIR}/${optional_dir}" ]]; then
        cp -a "${ROOT_DIR}/${optional_dir}" "${STAGING_DIR}/"
    fi
done

(cd "${STAGING_DIR}" && zip -qr "${ZIP_PATH}" ./*)
echo "Extension package generated: ${ZIP_PATH}"
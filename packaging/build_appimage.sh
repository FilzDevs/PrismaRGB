#!/usr/bin/env bash
set -euo pipefail

# Build script for PrismaRGB-x86_64.AppImage
# Bundles Python, PySide6, psutil, and the native SMBus helper into a portable AppImage.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build/appimage"
APPDIR="${BUILD_DIR}/PrismaRGB.AppDir"

rm -rf "${BUILD_DIR}"
mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/scalable/apps"

echo "[1/4] Compiling native SMBus helper..."
if command -v gcc >/dev/null 2>&1; then
    gcc -O2 "${REPO_ROOT}/native/smbus_piix4_helper.c" -o "${REPO_ROOT}/native/smbus_piix4_helper"
fi

echo "[2/4] Building standalone binary with PyInstaller..."
python3 -m PyInstaller \
    --noconfirm \
    --clean \
    --onedir \
    --name prismargb \
    --distpath "${APPDIR}/usr/lib" \
    --workpath "${BUILD_DIR}/work" \
    --specpath "${BUILD_DIR}" \
    --add-data "${REPO_ROOT}/backend:backend" \
    --add-data "${REPO_ROOT}/ui:ui" \
    --add-data "${REPO_ROOT}/native:native" \
    --hidden-import PySide6.QtCore \
    --hidden-import PySide6.QtGui \
    --hidden-import PySide6.QtWidgets \
    --hidden-import psutil \
    "${REPO_ROOT}/main.py"

ln -sf ../lib/prismargb/prismargb "${APPDIR}/usr/bin/prismargb"

echo "[3/4] Creating AppDir metadata, desktop entry, and SVG icon..."
cat > "${APPDIR}/prismargb.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=PrismaRGB
Comment=Linux RGB Control & Hardware Monitoring Suite
Exec=prismargb
Icon=prismargb
Categories=Utility;System;Settings;
Terminal=false
EOF

cp "${APPDIR}/prismargb.desktop" "${APPDIR}/usr/share/applications/prismargb.desktop"

cat > "${APPDIR}/prismargb.svg" << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00F0FF"/>
      <stop offset="50%" stop-color="#7B2CBF"/>
      <stop offset="100%" stop-color="#FF007F"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#0B0F1C"/>
  <circle cx="64" cy="64" r="46" fill="none" stroke="url(#g1)" stroke-width="12"/>
  <circle cx="64" cy="64" r="22" fill="url(#g1)"/>
</svg>
EOF

cp "${APPDIR}/prismargb.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/prismargb.svg"

cat > "${APPDIR}/AppRun" << 'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/lib/prismargb/prismargb" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

echo "[4/4] Packaging PrismaRGB-x86_64.AppImage..."
APPIMAGETOOL="${BUILD_DIR}/appimagetool-x86_64.AppImage"
if ! command -v appimagetool >/dev/null 2>&1; then
    curl -fsSL -o "${APPIMAGETOOL}" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "${APPIMAGETOOL}"
    ARCH=x86_64 "${APPIMAGETOOL}" --appimage-extract-and-run "${APPDIR}" "${REPO_ROOT}/PrismaRGB-x86_64.AppImage"
else
    ARCH=x86_64 appimagetool "${APPDIR}" "${REPO_ROOT}/PrismaRGB-x86_64.AppImage"
fi

chmod +x "${REPO_ROOT}/PrismaRGB-x86_64.AppImage"
echo "Done: ${REPO_ROOT}/PrismaRGB-x86_64.AppImage"

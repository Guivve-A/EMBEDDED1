#!/bin/bash
# applab_f2_deploy.sh - Despliega F2 como App Lab app y arranca.
# El sketch/ de la app debe contener el .ino renombrado a sketch.ino MAS todos
# los modulos (.cpp/.h). Luego app start compila+flashea+corre.
set -u
SRCDIR=/home/arduino/ArduinoApps/face_security_f2
APPDIR=/home/arduino/ArduinoApps/facef2

echo "=== [0] limpiar intento previo ==="
arduino-app-cli app stop "${APPDIR}" >/dev/null 2>&1
rm -rf "${APPDIR}"

echo "=== [1] crear app facef2 ==="
arduino-app-cli app new facef2 -b led -d "EMBEBIDOS F2 laser+buzzer" -i "🚨" 2>&1 | head -5

echo "=== [2] poblar sketch/ (ino como sketch.ino + modulos) ==="
SKDIR="${APPDIR}/sketch"
mkdir -p "${SKDIR}"
# El .ino del App Lab debe llamarse sketch.ino (igual que el dir padre 'sketch').
cp "${SRCDIR}/face_security_f2.ino" "${SKDIR}/sketch.ino"
cp "${SRCDIR}"/*.cpp "${SKDIR}/" 2>/dev/null
cp "${SRCDIR}"/*.h   "${SKDIR}/" 2>/dev/null
echo "contenido sketch/:"
ls -1 "${SKDIR}/"

echo "=== [3] app start (compila+flashea+corre) ==="
arduino-app-cli app start "${APPDIR}" --verbose 2>&1 | tail -12
echo "=== estado ==="
arduino-app-cli app list 2>&1 | grep -iE 'facef2|NAME'

#!/bin/bash
# flash_via_remoteocd.sh - Flasheo OFICIAL con la herramienta del core (remoteocd),
# que internamente corre openocd con la receta flash_sketch.cfg (0x8100000 + magic).
# remoteocd usa adb contra el serial de la placa; adbd corre localmente, asi que
# el flasheo "contra si misma" deberia funcionar.
# Uso: flash_via_remoteocd.sh /ruta/al/<sketch>.ino.elf-zsk.bin
set -u
BIN="${1:?Uso: flash_via_remoteocd.sh <sketch.ino.elf-zsk.bin>}"
SERIAL="2892129533"
ZBASE="/home/arduino/.arduino15/packages/arduino/hardware/zephyr/0.55.2"
VARIANT="${ZBASE}/variants/arduino_uno_q_stm32u585xx"
CFG="${VARIANT}/flash_sketch.cfg"
RB=$(find /home/arduino/.arduino15 -name remoteocd -type f 2>/dev/null | head -1)
ADB=$(find /home/arduino/.arduino15 -path '*platform-tools*' -name adb -type f 2>/dev/null | head -1)
[ -z "${ADB}" ] && ADB="/usr/lib/android-sdk/platform-tools/adb"

echo ">> remoteocd = ${RB}"
echo ">> adb       = ${ADB}"
echo ">> cfg       = ${CFG}"
echo ">> bin       = ${BIN}"
"${RB}" upload --adb-path "${ADB}" -s "${SERIAL}" -f "${CFG}" --verbose "${BIN}" 2>&1
echo ">> remoteocd exit = $?"

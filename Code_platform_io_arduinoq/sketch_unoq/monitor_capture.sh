#!/bin/bash
# monitor_capture.sh - captura no interactiva del Serial del MCU del UNO Q.
# El Serial del sketch sale por /dev/ttyHS1, que es propiedad exclusiva de
# 'arduino-router'. La via SOPORTADA para leerlo es el monitor del App CLI:
#     arduino-app-cli monitor
# (se conecta al router; no requiere puerto). Aqui se ejecuta con timeout duro
# y se resetea el MCU a mitad para capturar el banner de boot.
# Uso: monitor_capture.sh [segundos]   (por defecto 12)
set -u
SECS="${1:-12}"
LOG="/tmp/uno_serial_$$.log"

# Monitor del MCU en segundo plano, con timeout duro.
timeout "${SECS}" arduino-app-cli monitor > "${LOG}" 2>&1 &
MON_PID=$!

# Da tiempo a que el monitor abra el canal, luego resetea para ver el boot.
sleep 3
arduino-reset > /dev/null 2>&1

# Espera a que el monitor termine por timeout.
wait "${MON_PID}" 2>/dev/null

echo "===== MCU SERIAL (${SECS}s, con reset) ====="
cat -v "${LOG}"
echo ""
echo "===== END MCU SERIAL ====="
rm -f "${LOG}"

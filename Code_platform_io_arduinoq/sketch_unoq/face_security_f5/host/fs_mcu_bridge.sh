#!/usr/bin/env bash
# ============================================================================
#  fs_mcu_bridge.sh  -  EMBEBIDOS_1 / Fase 5 v3  -  Puente host MCU<->python
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  Reemplaza a fs_mcu_event_watch.sh + fs_mcu_watch.sh con UN SOLO proceso.
#  Motivo: el monitor serie del MCU es EXCLUSIVO; dos 'arduino-app-cli monitor'
#  en paralelo (uno leyendo EVT, otro escribiendo RES/ARM) chocan. Aqui se
#  mantiene UNA sola sesion de monitor, bidireccional:
#
#    LECTURA  (MCU -> python): cada linea 'EVT:INTRUSION' -> escribe
#             ${APPDIR}/mcu_event.json (seq++). cloud_bridge.py lo lee y hace
#             POST /intrusion.
#    ESCRITURA(python -> MCU): vigila ${APPDIR}/mcu_request.json y reenvia su
#             campo 'cmd' (ARM/DISARM/RES:MATCH/RES:INTRUDER) al MCU por la
#             misma sesion (stdin del monitor, via FIFO).
#
#  El stdin del monitor llega al sketch (verificado: 'STATUS' devuelve estado);
#  el stdout del monitor trae lo que el sketch imprime por Serial.
#
#  USO (lado Linux del UNO Q, por ADB o SSH). APPDIR debe ser la carpeta que el
#  contenedor monta como /app (la de la app EN EJECUCION):
#    nohup bash fs_mcu_bridge.sh /home/arduino/ArduinoApps/face_security_f5_applab \
#          >/tmp/fs_mcu_bridge.log 2>&1 &
# ============================================================================
set -u

APPDIR="${1:-/home/arduino/ArduinoApps/face_security_f5_applab}"
EVT="${APPDIR}/mcu_event.json"
REQ="${APPDIR}/mcu_request.json"
SEQ_FILE="/tmp/fs_mcu_event.seq"
FIFO="/tmp/fs_mcu_in.fifo"
MONITOR_CMD="${MONITOR_CMD:-arduino-app-cli monitor}"

log() { echo "[mcu_bridge] $(date +%H:%M:%S) $*" | tee -a /tmp/fs_mcu_bridge_dbg.log; }

read_seq()  { [ -f "${SEQ_FILE}" ] && cat "${SEQ_FILE}" 2>/dev/null || echo 0; }
write_evt() {
  local seq; seq="$(( $(read_seq) + 1 ))"; echo "${seq}" > "${SEQ_FILE}"
  printf '{"evt":"%s","seq":%s,"ts":%s}\n' "$1" "${seq}" "$(date +%s)" > "${EVT}.tmp"
  mv -f "${EVT}.tmp" "${EVT}"
  log "EVT $1 -> mcu_event.json (seq=${seq})"
}

# FIFO limpio para el stdin del monitor.
rm -f "${FIFO}"; mkfifo "${FIFO}"

# Log de depuracion: TODAS las lineas del MCU (para diagnostico/demo).
SERIAL_LOG="/tmp/fs_mcu_serial.log"
: > "${SERIAL_LOG}"

# Sesion unica de monitor: stdin <- FIFO ; stdout -> parser de EVT.
( ${MONITOR_CMD} < "${FIFO}" | while IFS= read -r line; do
    printf '%s\n' "${line}" >> "${SERIAL_LOG}"
    case "${line}" in
      *EVT:INTRUSION*) write_evt "INTRUSION" ;;
    esac
  done ) &
MON_PID=$!

# Mantener abierto el extremo de escritura del FIFO (evita EOF que cierra el monitor).
exec 3>"${FIFO}"
log "monitor unico abierto (grupo=${MON_PID}); APPDIR=${APPDIR}"

# Bucle de escritura python -> MCU.
while true; do
  if [ -f "${REQ}" ]; then
    cmd="$(python3 - "${REQ}" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("cmd", "").strip())
except Exception:
    pass
PY
)"
    rm -f "${REQ}"
    if [ -n "${cmd}" ]; then printf '%s\r\n' "${cmd}" >&3; log "MCU <- ${cmd}"; fi
  fi
  if ! kill -0 "${MON_PID}" 2>/dev/null; then
    log "el monitor termino; saliendo para que se relance"; break
  fi
  sleep 1
done

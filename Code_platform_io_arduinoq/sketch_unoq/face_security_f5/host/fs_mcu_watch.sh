#!/usr/bin/env bash
# ============================================================================
#  fs_mcu_watch.sh  -  EMBEBIDOS_1 / Fase 5  -  FALLBACK python -> MCU
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  SOLO se necesita si el RPC del RouterBridge (via primaria del cloud_bridge,
#  Bridge.provide/Bridge.call) no esta disponible en el runtime de App Lab.
#  En ese caso cloud_bridge.py escribe mcu_request.json en la carpeta de la
#  app y ESTE script (corriendo en el HOST, fuera del contenedor) reenvia el
#  comando (ARM/DISARM/CAL) al Monitor del MCU.
#
#  COMO REENVIA: el Monitor de App Lab es bidireccional (lo que se teclea en
#  'arduino-app-cli ... monitor' llega al sketch). Este script prueba, en
#  orden, las variantes de CLI conocidas y se queda con la primera que
#  funcione. Si ninguna funciona en tu version de arduino-app-cli, ejecuta
#  'arduino-app-cli --help' y ajusta MONITOR_CMD abajo (una sola linea).
#
#  USO (en el lado Linux del UNO Q, por ADB o SSH):
#    cd ~/ArduinoApps/face_security_f5/host
#    chmod +x fs_mcu_watch.sh
#    nohup ./fs_mcu_watch.sh >/tmp/fs_mcu_watch.log 2>&1 &
# ============================================================================
set -u

APPDIR="${1:-/home/arduino/ArduinoApps/face_security_f5}"
APP_NAME="$(basename "${APPDIR}")"
REQ="${APPDIR}/mcu_request.json"

# Sobreescribir aqui si tu CLI necesita otra sintaxis (recibe el comando por
# stdin y debe reenviarlo al monitor del MCU):
MONITOR_CMD="${MONITOR_CMD:-}"

log() { echo "[mcu_watch] $*"; }

json_get() { # json_get <file> <key>
  sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" | head -n1
}

# send_cmd CMD - reenvia una linea al monitor del MCU. Prueba variantes de
# arduino-app-cli; cachea la que funcione en MONITOR_CMD.
send_cmd() {
  local cmd="$1"
  if [ -n "${MONITOR_CMD}" ]; then
    printf '%s\n' "${cmd}" | timeout 5 ${MONITOR_CMD} >/dev/null 2>&1 \
      && { log "enviado '${cmd}' via '${MONITOR_CMD}'"; return 0; }
    log "MONITOR_CMD fallo; re-detectando"
    MONITOR_CMD=""
  fi
  local candidate
  for candidate in \
      "arduino-app-cli app monitor ${APP_NAME}" \
      "arduino-app-cli monitor ${APP_NAME}" \
      "arduino-app-cli monitor"; do
    if printf '%s\n' "${cmd}" | timeout 5 ${candidate} >/dev/null 2>&1; then
      MONITOR_CMD="${candidate}"
      log "enviado '${cmd}' via '${candidate}' (cacheado)"
      return 0
    fi
  done
  log "ERROR: ninguna variante de arduino-app-cli acepto el comando."
  log "       Ejecuta 'arduino-app-cli --help' y fija MONITOR_CMD en este script."
  return 1
}

log "vigilando ${REQ} (fallback python->MCU; via primaria = Bridge RPC)"

while true; do
  if [ -f "${REQ}" ]; then
    cmd="$(json_get "${REQ}" cmd)"
    rm -f "${REQ}"
    if [ -n "${cmd}" ]; then
      log "solicitud: ${cmd}"
      send_cmd "${cmd}"
    fi
  fi
  sleep 1
done

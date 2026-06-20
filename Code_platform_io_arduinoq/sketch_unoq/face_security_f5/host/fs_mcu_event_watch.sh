#!/usr/bin/env bash
# ============================================================================
#  fs_mcu_event_watch.sh  -  EMBEBIDOS_1 / Fase 5 v3  -  MCU -> python (eventos)
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  Simetrico a fs_mcu_watch.sh, pero en sentido inverso: tail-ea el MONITOR del
#  MCU (lectura) y, cuando ve la linea 'EVT:INTRUSION' que emite el sketch al
#  confirmar un corte del haz estando ARMED, escribe mcu_event.json en la
#  carpeta de la app. cloud_bridge.py (dentro del contenedor) lee ese archivo
#  y hace POST /intrusion al servidor de reconocimiento.
#
#  Solo se necesita si el RouterBridge no entrega los eventos del MCU al lado
#  python por RPC. Es el FALLBACK robusto (mismo patron archivo+watcher de F4).
#
#  COMO LEE: el Monitor de App Lab es bidireccional; 'arduino-app-cli ... monitor'
#  imprime por stdout lo que el sketch manda por Serial. Probamos, en orden, las
#  variantes de CLI conocidas y nos quedamos con la primera que emita lineas.
#  Si ninguna funciona en tu version, ejecuta 'arduino-app-cli --help' y ajusta
#  MONITOR_READ_CMD abajo (una sola linea que vuelque el monitor a stdout).
#
#  USO (en el lado Linux del UNO Q, por ADB o SSH):
#    cd ~/ArduinoApps/face_security_f5/host
#    chmod +x fs_mcu_event_watch.sh
#    nohup ./fs_mcu_event_watch.sh >/tmp/fs_mcu_event_watch.log 2>&1 &
# ============================================================================
set -u

APPDIR="${1:-/home/arduino/ArduinoApps/face_security_f5}"
APP_NAME="$(basename "${APPDIR}")"
EVT="${APPDIR}/mcu_event.json"
SEQ_FILE="/tmp/fs_mcu_event.seq"

# Sobreescribir aqui si tu CLI necesita otra sintaxis (debe volcar el monitor
# del MCU a stdout, linea a linea):
MONITOR_READ_CMD="${MONITOR_READ_CMD:-}"

log() { echo "[evt_watch] $*"; }

# Lleva un contador monotono para que cloud_bridge dispare a lo sumo 1 vez/seq.
read_seq()  { [ -f "${SEQ_FILE}" ] && cat "${SEQ_FILE}" 2>/dev/null || echo 0; }
write_evt() { # write_evt <nombre>
  local name="$1" seq
  seq="$(( $(read_seq) + 1 ))"
  echo "${seq}" > "${SEQ_FILE}"
  local tmp="${EVT}.tmp"
  printf '{"evt":"%s","seq":%s,"ts":%s}\n' "${name}" "${seq}" "$(date +%s)" > "${tmp}"
  mv -f "${tmp}" "${EVT}"
  log "evento ${name} -> ${EVT} (seq=${seq})"
}

# Detecta una variante de CLI que vuelque el monitor a stdout.
detect_monitor() {
  if [ -n "${MONITOR_READ_CMD}" ]; then return 0; fi
  local candidate
  for candidate in \
      "arduino-app-cli app monitor ${APP_NAME}" \
      "arduino-app-cli monitor ${APP_NAME}" \
      "arduino-app-cli monitor"; do
    # Probamos 3 s; si emite cualquier byte lo damos por valido.
    if timeout 3 ${candidate} 2>/dev/null | head -c1 | grep -q .; then
      MONITOR_READ_CMD="${candidate}"
      log "monitor detectado: '${candidate}'"
      return 0
    fi
  done
  return 1
}

log "vigilando el monitor del MCU en busca de 'EVT:INTRUSION'"

while true; do
  if ! detect_monitor; then
    log "no se detecto un comando de monitor; reintento en 5 s "
    log "(ejecuta 'arduino-app-cli --help' y fija MONITOR_READ_CMD)"
    sleep 5
    continue
  fi
  # Stream del monitor; por cada linea EVT:INTRUSION escribimos el evento.
  # Si el stream se corta (app reiniciada), el while exterior re-detecta.
  ${MONITOR_READ_CMD} 2>/dev/null | while IFS= read -r line; do
    case "${line}" in
      *EVT:INTRUSION*) write_evt "INTRUSION" ;;
    esac
  done
  log "stream del monitor terminado; reabriendo en 2 s"
  MONITOR_READ_CMD=""
  sleep 2
done

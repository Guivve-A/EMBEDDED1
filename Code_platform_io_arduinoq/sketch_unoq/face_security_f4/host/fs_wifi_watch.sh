#!/usr/bin/env bash
# ============================================================================
#  fs_wifi_watch.sh  -  EMBEBIDOS_1 / Fase 4  -  Puente contenedor -> host
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  POR QUE EXISTE:
#    El portal web (brick web_ui) corre DENTRO de un contenedor Docker que NO
#    puede hablar con NetworkManager del host. Cuando el usuario pulsa
#    "Guardar" en el portal, la app Python escribe un archivo de solicitud en
#    su carpeta (/app dentro del contenedor == ~/ArduinoApps/face_security_f4
#    en el host). Este watcher corre en el HOST, detecta ese archivo y aplica
#    las credenciales con fs_wifi.sh (que si tiene permisos nmcli).
#
#  ARCHIVOS (en la carpeta de la app, vista desde el host):
#    wifi_request.json   <- lo escribe el portal:  {"ssid1","pass1","ssid2","pass2"}
#    wifi_status.json    -> lo escribe este script: {"state","ip","ssid","ts"}
#
#  USO (en el lado Linux del UNO Q, por ADB o SSH):
#    ./fs_wifi_watch.sh            usa la carpeta por defecto de la app
#    ./fs_wifi_watch.sh <APPDIR>   carpeta explicita de la app
#
#  Dejarlo corriendo mientras se configura. Se puede lanzar en segundo plano:
#    nohup ./fs_wifi_watch.sh >/tmp/fs_wifi_watch.log 2>&1 &
# ============================================================================
set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FS_WIFI="${SELF_DIR}/fs_wifi.sh"
APPDIR="${1:-/home/arduino/ArduinoApps/face_security_f4}"
REQ="${APPDIR}/wifi_request.json"
STATUS="${APPDIR}/wifi_status.json"
WIFI_IFACE="${WIFI_IFACE:-wlan0}"

log() { echo "[watch] $*"; }

[ -x "${FS_WIFI}" ] || chmod +x "${FS_WIFI}" 2>/dev/null || true

# Extrae un campo string de un JSON plano sin depender de jq.
json_get() { # json_get <file> <key>
  sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" | head -n1
}

write_status() { # write_status <state> <extra-ssid>
  local state="$1" ssid="${2:-}"
  local ip; ip="$(ip -4 -o addr show "${WIFI_IFACE}" 2>/dev/null | awk '{print $4}' | sed 's#/.*##' | head -n1)"
  printf '{"state":"%s","ip":"%s","ssid":"%s","ts":%s}\n' \
    "${state}" "${ip:-}" "${ssid}" "$(date +%s)" > "${STATUS}"
}

log "vigilando ${REQ}"
log "motor: ${FS_WIFI}"

# Estado inicial publicado para el portal.
if "${FS_WIFI}" has-creds >/dev/null 2>&1; then
  write_status "client" ""
else
  write_status "ap" ""
fi

while true; do
  if [ -f "${REQ}" ]; then
    log "solicitud detectada"
    s1="$(json_get "${REQ}" ssid1)"
    p1="$(json_get "${REQ}" pass1)"
    s2="$(json_get "${REQ}" ssid2)"
    p2="$(json_get "${REQ}" pass2)"
    action="$(json_get "${REQ}" action)"
    rm -f "${REQ}"

    if [ "${action}" = "reset" ]; then
      log "accion=reset"
      "${FS_WIFI}" reset
      write_status "ap" ""
    elif [ -n "${s1}" ]; then
      log "guardando redes: '${s1}'${s2:+ + '${s2}'}"
      write_status "saving" "${s1}"
      if "${FS_WIFI}" save "${s1}" "${p1}" "${s2}" "${p2}"; then
        write_status "client" "${s1}"
      else
        write_status "error" "${s1}"
      fi
    else
      log "solicitud invalida (sin ssid1)"
    fi
  fi
  sleep 1
done

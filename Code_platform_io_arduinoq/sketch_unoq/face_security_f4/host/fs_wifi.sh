#!/usr/bin/env bash
# ============================================================================
#  fs_wifi.sh  -  EMBEBIDOS_1 / Fase 4  -  Motor WiFi del lado LINUX del UNO Q
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  POR QUE EXISTE (hallazgo clave de F4):
#    El Arduino UNO Q es HIBRIDO. El WiFi NO se controla desde el sketch del
#    MCU (STM32U585) como en un ESP32: NO hay libreria WiFi.h para el sketch.
#    El radio WiFi pertenece al lado LINUX (Qualcomm) y se gestiona con
#    NetworkManager (nmcli). El usuario 'arduino' tiene permisos polkit
#    completos (grupo netdev) -> puede crear AP y perfiles cliente SIN sudo.
#
#    Ademas, las apps de App Lab corren DENTRO de un contenedor Docker sin
#    acceso al D-Bus de NetworkManager del host. Por eso la parte privilegiada
#    (levantar AP, guardar redes, conmutar a cliente) vive en ESTE script, que
#    se ejecuta en el HOST (lado Linux), no en el contenedor de la app.
#
#  EQUIVALENCIAS con el plan original (pensado para ESP32):
#    - "Modo AP 192.168.4.1"      -> NM modo 'ap'+'shared'  => gateway 10.42.0.1
#    - "Guardar 2 redes en EEPROM"-> 2 perfiles de conexion NM persistentes
#                                    (sobreviven reinicios; son la "EEPROM")
#    - "Conmutar a cliente"       -> 'nmcli connection up' del perfil primario;
#                                    NM autoconecta por prioridad (primary>backup)
#    - "Boton reset borra EEPROM" -> subcomando 'reset' (borra perfiles + AP up)
#
#  USO:
#    ./fs_wifi.sh status                         estado del radio y la conexion
#    ./fs_wifi.sh ap-up                          levanta el AP FaceSecurity_Setup
#    ./fs_wifi.sh ap-down                        baja el AP
#    ./fs_wifi.sh save SSID1 PASS1 SSID2 PASS2   guarda 2 redes (PASS2 puede ir
#                                                vacio "" si no hay backup) y
#                                                conmuta a cliente
#    ./fs_wifi.sh client-up                      conecta al primario (o backup)
#    ./fs_wifi.sh has-creds                      exit 0 si hay redes guardadas
#    ./fs_wifi.sh reset                          borra redes y vuelve a AP
#
#  Las constantes (SSID/pass del AP, nombres de perfil) se leen de
#  fs_wifi.conf si existe junto a este script; si no, usan los valores de
#  config.h del proyecto (FaceSecurity_Setup / setup1234).
# ============================================================================
set -u

# --- Configuracion (espejo de sketch/config.h) ------------------------------
AP_SSID="${AP_SSID:-FaceSecurity_Setup}"
AP_PASS="${AP_PASS:-setup1234}"
WIFI_IFACE="${WIFI_IFACE:-wlan0}"

# Nombres de los perfiles NetworkManager que actuan como "EEPROM".
AP_CON="FaceSecurity_AP"            # perfil del Access Point de setup
CON_PRIMARY="FaceSecurity_WiFi1"    # red primaria del usuario
CON_BACKUP="FaceSecurity_WiFi2"     # red de respaldo del usuario

# Carga overrides opcionales (no obligatorio).
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "${SELF_DIR}/fs_wifi.conf" ] && . "${SELF_DIR}/fs_wifi.conf"

log() { echo "[fs_wifi] $*"; }
err() { echo "[fs_wifi][ERROR] $*" >&2; }

require_nmcli() {
  command -v nmcli >/dev/null 2>&1 || { err "nmcli no encontrado"; exit 2; }
}

# has_creds: exit 0 si existe el perfil primario (= hay redes guardadas).
cmd_has_creds() {
  nmcli -t -f NAME connection show 2>/dev/null | grep -qx "${CON_PRIMARY}"
}

cmd_status() {
  log "radio wifi : $(nmcli radio wifi 2>/dev/null)"
  log "iface ${WIFI_IFACE}:"
  nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null | grep "^${WIFI_IFACE}:" || true
  log "IP ${WIFI_IFACE}: $(ip -4 -o addr show "${WIFI_IFACE}" 2>/dev/null | awk '{print $4}' | head -n1)"
  if cmd_has_creds; then
    log "credenciales guardadas: SI (perfil ${CON_PRIMARY})"
    nmcli -t -f connection.id,802-11-wireless.ssid,connection.autoconnect-priority \
      connection show "${CON_PRIMARY}" 2>/dev/null | sed 's/^/[fs_wifi]   /'
    if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "${CON_BACKUP}"; then
      nmcli -t -f connection.id,802-11-wireless.ssid,connection.autoconnect-priority \
        connection show "${CON_BACKUP}" 2>/dev/null | sed 's/^/[fs_wifi]   /'
    fi
  else
    log "credenciales guardadas: NO -> corresponde modo AP"
  fi
}

# ap_up: (re)crea y activa el AP de setup. ipv4 'shared' => NM corre dnsmasq
# (DHCP) y asigna gateway 10.42.0.1. El portal de la app queda en :7000.
cmd_ap_up() {
  require_nmcli
  nmcli radio wifi on >/dev/null 2>&1 || true
  # Recrear el perfil idempotentemente.
  nmcli connection delete "${AP_CON}" >/dev/null 2>&1 || true
  if ! nmcli connection add type wifi ifname "${WIFI_IFACE}" con-name "${AP_CON}" \
        autoconnect no ssid "${AP_SSID}" \
        802-11-wireless.mode ap 802-11-wireless.band bg \
        ipv4.method shared \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${AP_PASS}" >/dev/null 2>&1; then
    err "no se pudo crear el perfil del AP"
    return 1
  fi
  if nmcli connection up "${AP_CON}" >/dev/null 2>&1; then
    sleep 1
    local ip
    ip="$(ip -4 -o addr show "${WIFI_IFACE}" 2>/dev/null | awk '{print $4}' | head -n1)"
    log "AP '${AP_SSID}' ACTIVO. Gateway/portal: http://${ip%%/*}:7000  (pass: ${AP_PASS})"
    return 0
  fi
  err "no se pudo activar el AP"
  return 1
}

cmd_ap_down() {
  require_nmcli
  nmcli connection down "${AP_CON}" >/dev/null 2>&1 || true
  log "AP '${AP_SSID}' detenido."
}

# save: crea/actualiza 2 perfiles cliente (la "EEPROM") y conmuta a cliente.
# Args: SSID1 PASS1 [SSID2] [PASS2]. La red 2 es opcional.
cmd_save() {
  require_nmcli
  local s1="${1:-}" p1="${2:-}" s2="${3:-}" p2="${4:-}"
  if [ -z "${s1}" ]; then err "save requiere al menos SSID1"; return 2; fi

  _upsert_client "${CON_PRIMARY}" "${s1}" "${p1}" 20
  if [ -n "${s2}" ]; then
    _upsert_client "${CON_BACKUP}" "${s2}" "${p2}" 10
  else
    nmcli connection delete "${CON_BACKUP}" >/dev/null 2>&1 || true
  fi
  log "redes guardadas: '${s1}'${s2:+ + '${s2}'} (persistentes en NetworkManager)"

  # Conmutar a cliente: bajar AP y subir el primario.
  cmd_ap_down
  cmd_client_up
}

# _upsert_client NAME SSID PASS PRIORITY
_upsert_client() {
  local name="$1" ssid="$2" pass="$3" prio="$4"
  nmcli connection delete "${name}" >/dev/null 2>&1 || true
  local -a add=(connection add type wifi ifname "${WIFI_IFACE}" con-name "${name}"
                ssid "${ssid}" autoconnect yes
                connection.autoconnect-priority "${prio}"
                802-11-wireless.mode infrastructure)
  if [ -n "${pass}" ]; then
    add+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${pass}")
  fi
  nmcli "${add[@]}" >/dev/null 2>&1 \
    && log "perfil '${name}' -> SSID '${ssid}' (prioridad ${prio})" \
    || err "no se pudo crear el perfil '${name}'"
}

# client_up: intenta el primario; si falla, el backup. NM tambien autoconecta
# por prioridad, pero forzamos para reportar resultado de inmediato.
cmd_client_up() {
  require_nmcli
  if ! cmd_has_creds; then err "no hay credenciales guardadas"; return 1; fi
  if nmcli connection up "${CON_PRIMARY}" >/dev/null 2>&1; then
    sleep 1
    log "CLIENTE conectado a la red primaria. IP: $(ip -4 -o addr show "${WIFI_IFACE}" 2>/dev/null | awk '{print $4}' | head -n1)"
    return 0
  fi
  log "primario fallo; probando backup..."
  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "${CON_BACKUP}" \
     && nmcli connection up "${CON_BACKUP}" >/dev/null 2>&1; then
    sleep 1
    log "CLIENTE conectado a la red de respaldo. IP: $(ip -4 -o addr show "${WIFI_IFACE}" 2>/dev/null | awk '{print $4}' | head -n1)"
    return 0
  fi
  err "no se pudo conectar a ninguna red guardada"
  return 1
}

# reset: equivalente al boton fisico de reset -> borra "EEPROM" y vuelve a AP.
cmd_reset() {
  require_nmcli
  nmcli connection delete "${CON_PRIMARY}" >/dev/null 2>&1 || true
  nmcli connection delete "${CON_BACKUP}"  >/dev/null 2>&1 || true
  log "credenciales borradas. Volviendo a modo AP..."
  cmd_ap_up
}

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}"
}

main() {
  local cmd="${1:-status}"; shift || true
  case "${cmd}" in
    status)     cmd_status ;;
    ap-up)      cmd_ap_up ;;
    ap-down)    cmd_ap_down ;;
    save)       cmd_save "$@" ;;
    client-up)  cmd_client_up ;;
    has-creds)  cmd_has_creds && { log "SI"; exit 0; } || { log "NO"; exit 1; } ;;
    reset)      cmd_reset ;;
    -h|--help|help) usage ;;
    *) err "comando desconocido: ${cmd}"; usage; exit 2 ;;
  esac
}

main "$@"

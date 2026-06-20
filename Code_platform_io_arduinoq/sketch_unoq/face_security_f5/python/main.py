# ============================================================================
#  main.py  -  EMBEBIDOS_1 / Fase 5 (v2)  -  Lado Linux del UNO Q (App Lab)
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  Dos responsabilidades:
#
#  1) PORTAL WIFI (heredado INTACTO de F4, verificado en HW):
#       GET  /api/status   -> estado actual {state, ip, ssid}  (wifi_status.json)
#       POST /api/save     -> guarda 2 redes (escribe wifi_request.json)
#       POST /api/reset    -> reset de fabrica (wifi_request.json action=reset)
#     El contenedor NO ve NetworkManager: host/fs_wifi_watch.sh (en el host)
#     aplica los cambios con nmcli. Portal: http://10.42.0.1:7000 (en modo AP).
#
#  2) CLOUD BRIDGE (nuevo, modulo cloud_bridge.py):
#       - poll GET https://<SERVER_HOST>/state cada 5 s; si 'armed' cambia,
#         reenvia ARM/DISARM al MCU (RPC del RouterBridge o fallback archivo).
#       - heartbeat POST /device/heartbeat {"device_id":"unoq","fw":...} cada
#         15 s con X-API-Key.
#     Config en /app/cloud.json (copiar de cloud.json.example y rellenar).
# ============================================================================
import json
import os
import time

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI

import cloud_bridge

# /app es el bind-mount de la carpeta de la app (compartida con el host).
APP_DIR = os.environ.get("APP_DIR", "/app")
REQ_FILE = os.path.join(APP_DIR, "wifi_request.json")
STATUS_FILE = os.path.join(APP_DIR, "wifi_status.json")

ui = WebUI()  # bind 0.0.0.0:7000, sirve ./assets (index.html)


def _read_status() -> dict:
    """Lee el estado publicado por el watcher del host. Tolerante a fallos."""
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"state": "unknown", "ip": "", "ssid": ""}


def _write_request(payload: dict) -> None:
    """Escribe la solicitud para que el watcher del host la aplique."""
    tmp = REQ_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, REQ_FILE)  # escritura atomica


# --- API REST del portal (identica a F4) ------------------------------------
def api_status():
    return _read_status()


def api_save(body: dict):
    """body: {ssid1, pass1, ssid2?, pass2?}. ssid1 es obligatorio."""
    ssid1 = (body or {}).get("ssid1", "").strip()
    if not ssid1:
        return {"ok": False, "error": "ssid1 (red primaria) es obligatorio"}
    payload = {
        "action": "save",
        "ssid1": ssid1,
        "pass1": (body or {}).get("pass1", ""),
        "ssid2": (body or {}).get("ssid2", "").strip(),
        "pass2": (body or {}).get("pass2", ""),
        "ts": int(time.time()),
    }
    _write_request(payload)
    return {"ok": True, "message": "Configuracion recibida. Conmutando a cliente..."}


def api_reset():
    _write_request({"action": "reset", "ts": int(time.time())})
    return {"ok": True, "message": "Reset solicitado. Volviendo a modo AP..."}


ui.expose_api("GET", "/api/status", api_status)
ui.expose_api("POST", "/api/save", api_save)
ui.expose_api("POST", "/api/reset", api_reset)

print("[F5] Portal WiFi listo en :7000  (assets/index.html)")
print(f"[F5] req={REQ_FILE}")
print(f"[F5] status={STATUS_FILE}")

# --- Cloud bridge (hilo demonio; no bloquea el portal) -----------------------
cloud_bridge.start(APP_DIR)

App.run()  # bloquea hasta que la app se detenga

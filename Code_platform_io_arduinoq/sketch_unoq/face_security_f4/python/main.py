# ============================================================================
#  main.py  -  EMBEBIDOS_1 / Fase 4  -  Portal WiFi (lado Linux, App Lab)
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  Esta es la parte de la app que corre en el LADO LINUX del UNO Q, dentro del
#  contenedor de App Lab, usando el brick 'web_ui' (FastAPI + Uvicorn + Socket.IO).
#  Sirve el portal de configuracion (assets/index.html) y expone una API REST:
#
#     GET  /api/status   -> estado actual {state, ip, ssid}  (lee wifi_status.json)
#     POST /api/save     -> guarda 2 redes (escribe wifi_request.json)
#     POST /api/reset    -> reset de fabrica (escribe wifi_request.json action=reset)
#
#  POR QUE escribe archivos en vez de llamar nmcli directo:
#    El contenedor NO tiene acceso a NetworkManager del host. El script de host
#    host/fs_wifi_watch.sh vigila wifi_request.json y aplica los cambios con
#    nmcli (host/fs_wifi.sh). /app dentro del contenedor == la carpeta de la
#    app en el host, asi que el archivo cruza la frontera contenedor<->host.
#
#  El portal queda accesible en http://<ip-del-UNO-Q>:7000  (puerto del web_ui).
#  En modo AP (FaceSecurity_Setup) esa IP es 10.42.0.1  -> http://10.42.0.1:7000
# ============================================================================
import json
import os
import time

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI

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


# --- API REST -------------------------------------------------------------
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

print("[F4] Portal WiFi listo en :7000  (assets/index.html)")
print(f"[F4] req={REQ_FILE}")
print(f"[F4] status={STATUS_FILE}")

App.run()  # bloquea hasta que la app se detenga

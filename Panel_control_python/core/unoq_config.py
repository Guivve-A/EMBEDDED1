"""
core/unoq_config.py — Configuración del Arduino UNO Q por ADB desde la GUI.

Qué hace (la prioridad pedida por el PM es la config WiFi + cloud.json):
    1. Genera localmente un cloud.json (SERVER_HOST = IP:8000 de la PC, API_KEY,
       POLL_S, HB_S) en una carpeta temporal de la GUI.
    2. adb push de ese cloud.json a la carpeta de la app en el UNO Q
       (~/ArduinoApps/face_security_f5/cloud.json) — lo lee cloud_bridge.py.
    3. Por adb shell, hace ejecutable y corre host/fs_wifi.sh:
           fs_wifi.sh save SSID1 PASS1 SSID2 PASS2   (guarda 2 redes y conmuta)
       y luego fs_wifi.sh status para reportar el resultado.

Todo el progreso se emite por callback `on_log`; el llamador lo corre en un hilo
para no congelar la GUI. Cada subproceso adb tiene timeout.

Notas de robustez:
    - Se usa el device_id detectado (adb -s <id>) para no apuntar al teléfono.
    - El cloud_bridge del UNO Q acepta SERVER_HOST con http:// (lo respeta) o sin
      esquema (le antepone https://). Para LAN local conviene "http://IP:8000".
    - Las contraseñas WiFi NO se loguean (se enmascaran).

Verificación headless: NO se toca el UNO Q de verdad. El __main__ solo genera un
cloud.json de ejemplo en memoria/temporal e imprime los comandos que se correrían.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Callable

from . import paths

LogFn = Callable[[str], None]


def _noop(_: str) -> None:
    """Callback de log por defecto."""


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def build_cloud_json(
    server_host: str,
    api_key: str = "",
    poll_s: int = 3,
    hb_s: int = 15,
    result_poll_s: float = 0.8,
) -> dict:
    """
    Construye el dict de cloud.json para el UNO Q.

    Inputs:
        server_host: IP/host del servidor. Para LAN local usa "http://IP:8000"
                     (con esquema) para que el bridge no le anteponga https://.
        api_key:     X-API-Key del servidor (vacío en modo dev).
    Outputs:
        dict listo para json.dump, con los mismos campos que cloud.json.example.
    """
    return {
        "SERVER_HOST": server_host,
        "API_KEY": api_key,
        "POLL_S": int(poll_s),
        "RESULT_POLL_S": float(result_poll_s),  # bajo = LED reacciona casi al instante
        "HB_S": int(hb_s),
    }


def server_host_for_lan(ip: str, port: int = 8000) -> str:
    """Devuelve 'http://IP:PORT' (esquema explícito para LAN, sin TLS)."""
    return f"http://{ip}:{port}"


def write_cloud_json_temp(cfg: dict) -> str:
    """
    Escribe cfg como cloud.json en una carpeta temporal de la GUI y devuelve la ruta.

    Se usa un archivo real (no NamedTemporaryFile abierto) para que adb push pueda
    leerlo en Windows sin bloqueo de archivo.
    """
    tmp_dir = tempfile.mkdtemp(prefix="embebidos_unoq_")
    path = os.path.join(tmp_dir, "cloud.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    return path


def _adb(args: list[str], device_id: str | None, timeout: float = 30.0):
    """
    Ejecuta `adb [-s id] <args>` y devuelve el CompletedProcess.

    Lanza FileNotFoundError/TimeoutExpired/OSError al llamador (lo maneja arriba).
    """
    base = [paths.adb_path()]
    if device_id:
        base += ["-s", device_id]
    return subprocess.run(
        base + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def _mask(secret: str) -> str:
    """Enmascara una contraseña para logs (deja ver solo que hay/no hay valor)."""
    if not secret:
        return "(vacía)"
    return "*" * len(secret)


def configure_unoq(
    *,
    device_id: str | None,
    ssid1: str,
    pass1: str,
    ssid2: str = "",
    pass2: str = "",
    server_ip: str,
    server_port: int = 8000,
    api_key: str = "",
    on_log: LogFn = _noop,
    remote_app_dir: str = paths.UNOQ_REMOTE_APP_DIR,
) -> bool:
    """
    Configura el UNO Q: push de cloud.json + fs_wifi.sh save/status por adb shell.

    Inputs:
        device_id:   id de adb del UNO Q (de devices.detect_unoq); None = el único.
        ssid1/pass1: red WiFi primaria (obligatoria).
        ssid2/pass2: red de respaldo (opcional; pass2 puede ir vacío).
        server_ip:   IP de esta PC (servidor) para el cloud.json del bridge.
        api_key:     X-API-Key (vacío en dev).
        remote_app_dir: carpeta de la app en el UNO Q (donde va cloud.json).
    Outputs:
        True si todas las etapas críticas (push cloud.json + save WiFi) salieron OK.

    Por etapas, con progreso. No lanza: cualquier error se loguea y devuelve False.
    """
    if not ssid1.strip():
        on_log("ERROR: la red WiFi primaria (SSID1) es obligatoria.")
        return False

    # --- Etapa 0: comprobar adb disponible ---
    on_log("== Configurando Arduino UNO Q ==")
    try:
        ping = _adb(["get-state"], device_id, timeout=10)
    except FileNotFoundError:
        on_log("ERROR: adb no encontrado. Revisa platform-tools.")
        return False
    except subprocess.TimeoutExpired:
        on_log("ERROR: adb no respondió (get-state).")
        return False
    except OSError as exc:
        on_log(f"ERROR ejecutando adb: {exc}")
        return False
    if ping.returncode != 0 or "device" not in (ping.stdout or ""):
        on_log(f"ERROR: el UNO Q no está en estado 'device' (adb get-state: "
               f"{(ping.stdout or ping.stderr or '').strip()}).")
        return False
    on_log(f"UNO Q accesible por ADB (device_id={device_id or 'único'}).")

    # --- Etapa 1: generar cloud.json local ---
    host = server_host_for_lan(server_ip, server_port)
    cfg = build_cloud_json(host, api_key=api_key)
    on_log(f"cloud.json: SERVER_HOST={host}  API_KEY={'(set)' if api_key else '(vacía)'}"
           f"  POLL_S={cfg['POLL_S']}  HB_S={cfg['HB_S']}")
    try:
        local_cloud = write_cloud_json_temp(cfg)
    except OSError as exc:
        on_log(f"ERROR escribiendo cloud.json temporal: {exc}")
        return False

    # --- Etapa 2: push de cloud.json al UNO Q ---
    remote_cloud = remote_app_dir.rstrip("/") + "/cloud.json"
    on_log(f"adb push cloud.json -> {remote_cloud}")
    try:
        push = _adb(["push", local_cloud, remote_cloud], device_id, timeout=40)
    except (subprocess.TimeoutExpired, OSError) as exc:
        on_log(f"ERROR en adb push: {exc}")
        return False
    if push.returncode != 0:
        on_log("ERROR: falló adb push de cloud.json.")
        on_log((push.stderr or push.stdout or "").strip())
        on_log(f"  Verifica que exista la carpeta de la app: {remote_app_dir}")
        return False
    on_log("cloud.json copiado al UNO Q.")

    # --- Etapa 3: hacer ejecutables los scripts de host ---
    host_dir = remote_app_dir.rstrip("/") + "/host"
    on_log("chmod +x de los scripts de host (fs_wifi.sh ...)")
    try:
        _adb(
            ["shell", f"chmod +x {host_dir}/fs_wifi.sh {host_dir}/fs_wifi_watch.sh "
                      f"{host_dir}/fs_mcu_watch.sh 2>/dev/null; true"],
            device_id,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        on_log(f"Aviso: no se pudo hacer chmod ({exc}). Se intenta con bash igual.")

    # --- Etapa 4: guardar redes WiFi y conmutar a cliente ---
    on_log(f"Guardando redes WiFi: '{ssid1}' (pass {_mask(pass1)})"
           + (f" + '{ssid2}' (pass {_mask(pass2)})" if ssid2.strip() else " (sin backup)"))
    # Se invoca por bash explícito por si el shell por defecto no es bash.
    # Los argumentos van entre comillas simples para tolerar espacios/símbolos.
    save_cmd = (
        f"bash {host_dir}/fs_wifi.sh save "
        f"'{ssid1}' '{pass1}' '{ssid2}' '{pass2}'"
    )
    try:
        save = _adb(["shell", save_cmd], device_id, timeout=90)
    except (subprocess.TimeoutExpired, OSError) as exc:
        on_log(f"ERROR ejecutando fs_wifi.sh save: {exc}")
        return False
    for line in (save.stdout or "").splitlines():
        on_log("  " + line)
    if save.stderr:
        for line in save.stderr.splitlines():
            on_log("  [err] " + line)
    if save.returncode != 0:
        on_log(f"ERROR: fs_wifi.sh save devolvió código {save.returncode}.")
        return False

    # --- Etapa 5: status (informativo) ---
    on_log("Estado WiFi del UNO Q tras la configuración:")
    try:
        st = _adb(["shell", f"bash {host_dir}/fs_wifi.sh status"], device_id, timeout=30)
        for line in (st.stdout or "").splitlines():
            on_log("  " + line)
    except (subprocess.TimeoutExpired, OSError) as exc:
        on_log(f"Aviso: no se pudo leer status ({exc}).")

    on_log("UNO Q configurado. Reinicia la app desde App Lab si el bridge no "
           "toma la nueva config (el bridge relee cloud.json cada 30 s).")
    return True


if __name__ == "__main__":
    # Verificación headless: NO toca el UNO Q. Solo muestra cloud.json y comandos.
    print("== unoq_config self-test (dry-run, sin tocar el UNO Q) ==")
    cfg = build_cloud_json(server_host_for_lan("192.168.1.50", 8000), api_key="")
    print("cloud.json que se generaría:")
    print(json.dumps(cfg, indent=2))
    print("remote_app_dir ->", paths.UNOQ_REMOTE_APP_DIR)
    print("fs_wifi.sh local existe ->", paths.UNOQ_FS_WIFI.is_file())
    print("Comando save de ejemplo:")
    print("  bash <app>/host/fs_wifi.sh save 'MiRed' '****' 'Backup' '****'")

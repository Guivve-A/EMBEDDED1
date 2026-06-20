"""
core/devices.py — Detección de dispositivos físicos para el Panel de Control.

Detecta dos cosas, sin bloquear nunca la GUI (el llamador lo corre en un hilo
de sondeo cada ~3 s):

    ESP32-CAM  -> aparece como puerto COM con chip USB-serie CP210x / CH340 /
                  CH9102 (según el shield ESP32-CAM-MB o adaptador). Se detecta
                  con pyserial (list_ports); fallback a `pio device list`.
    UNO Q      -> se opera por ADB. `adb devices` lista un id alfanumérico tipo
                  "2892129533" en estado "device". OJO: hay que IGNORAR el
                  teléfono Samsung "R58X30WSJNP" (también sale en adb devices).

Cada detector devuelve un dataclass con .online + detalle, para que la GUI pinte
el semáforo y habilite/inhabilite los botones de las secciones 5 y 6.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field

from . import paths

# IDs de ADB que NO son el UNO Q (lista negra). El teléfono Samsung del usuario
# aparece en adb devices y no debe confundirse con el UNO Q.
_ADB_IGNORE_IDS = {"R58X30WSJNP"}

# Pistas de descripción/HWID de los puentes USB-serie típicos del ESP32-CAM.
_ESP32_SERIAL_HINTS = ("CP210", "CH340", "CH910", "SILICON LABS", "USB-SERIAL")
# VID:PID conocidos: Silicon Labs CP210x (10C4:EA60), WCH CH340 (1A86:7523),
# WCH CH9102 (1A86:55D4).
_ESP32_VIDPID = {(0x10C4, 0xEA60), (0x1A86, 0x7523), (0x1A86, 0x55D4)}

# Flag para que los subprocess no abran ventana de consola en Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass
class Esp32Status:
    """Estado del ESP32-CAM detectado por puerto serie."""

    online: bool = False
    port: str | None = None          # p. ej. "COM5"
    description: str = ""            # descripción del puerto / chip
    detail: str = ""                # texto para el log/tooltip


@dataclass
class UnoqStatus:
    """Estado del UNO Q detectado por ADB."""

    online: bool = False
    device_id: str | None = None     # id de adb (no el del teléfono)
    detail: str = ""
    all_ids: list[str] = field(default_factory=list)  # todo lo que vio adb


# --------------------------------------------------------------------------- #
# ESP32-CAM por puerto serie
# --------------------------------------------------------------------------- #
def detect_esp32() -> Esp32Status:
    """
    Detecta el ESP32-CAM como puerto COM (CP210x/CH340/CH9102).

    Estrategia:
        1. pyserial list_ports: filtra por VID:PID conocido o por palabras clave
           en la descripción/HWID.
        2. Si pyserial no encuentra (o no está instalado), cae a `pio device list`
           y busca el primer COM con una pista de chip serie.
    Nunca lanza: ante cualquier error devuelve online=False con el motivo.
    """
    # --- Vía 1: pyserial ---
    try:
        from serial.tools import list_ports  # import perezoso (dep opcional)

        candidates: list[tuple[str, str]] = []  # (device, description)
        for p in list_ports.comports():
            desc = (p.description or "").upper()
            hwid = (p.hwid or "").upper()
            vidpid_match = (
                p.vid is not None
                and p.pid is not None
                and (p.vid, p.pid) in _ESP32_VIDPID
            )
            hint_match = any(h in desc or h in hwid for h in _ESP32_SERIAL_HINTS)
            if vidpid_match or hint_match:
                candidates.append((p.device, p.description or ""))
        if candidates:
            dev, desc = candidates[0]
            extra = ""
            if len(candidates) > 1:
                extra = f" (+{len(candidates) - 1} más)"
            return Esp32Status(
                online=True,
                port=dev,
                description=desc,
                detail=f"ESP32-CAM en {dev}: {desc}{extra}",
            )
        # pyserial funcionó pero no halló un chip compatible.
        return Esp32Status(
            online=False, detail="Sin puerto COM compatible (CP210x/CH340)."
        )
    except ImportError:
        pass  # pyserial no instalado -> probar pio
    except Exception as exc:  # noqa: BLE001 — detección nunca debe romper la GUI
        return Esp32Status(online=False, detail=f"Error pyserial: {exc}")

    # --- Vía 2: fallback `pio device list` ---
    return _detect_esp32_via_pio()


def _detect_esp32_via_pio() -> Esp32Status:
    """Fallback: parsea `pio device list` buscando un COM con chip serie conocido."""
    try:
        out = subprocess.run(
            [paths.pio_path(), "device", "list"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        return Esp32Status(online=False, detail="pyserial ausente y pio no encontrado.")
    except subprocess.TimeoutExpired:
        return Esp32Status(online=False, detail="`pio device list` excedió el tiempo.")
    except OSError as exc:
        return Esp32Status(online=False, detail=f"Error ejecutando pio: {exc}")

    text = (out.stdout or "") + "\n" + (out.stderr or "")
    lines = text.splitlines()
    current_port: str | None = None
    for line in lines:
        m = re.match(r"^(COM\d+)\b", line.strip())
        if m:
            current_port = m.group(1)
            continue
        upper = line.upper()
        if current_port and any(h in upper for h in _ESP32_SERIAL_HINTS):
            return Esp32Status(
                online=True,
                port=current_port,
                description=line.strip(),
                detail=f"ESP32-CAM en {current_port} (vía pio): {line.strip()}",
            )
    return Esp32Status(online=False, detail="pio no listó un COM compatible.")


# --------------------------------------------------------------------------- #
# UNO Q por ADB
# --------------------------------------------------------------------------- #
def detect_unoq() -> UnoqStatus:
    """
    Detecta el UNO Q con `adb devices`, ignorando el teléfono Samsung.

    Parseo de la salida de `adb devices`:
        List of devices attached
        2892129533    device
        R58X30WSJNP   device      <- teléfono, se ignora

    Un id cuenta como UNO Q si su estado es "device" (no "unauthorized"/"offline")
    y no está en la lista negra _ADB_IGNORE_IDS. Nunca lanza.
    """
    try:
        out = subprocess.run(
            [paths.adb_path(), "devices"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        return UnoqStatus(online=False, detail="adb no encontrado (revisa platform-tools).")
    except subprocess.TimeoutExpired:
        return UnoqStatus(online=False, detail="`adb devices` excedió el tiempo.")
    except OSError as exc:
        return UnoqStatus(online=False, detail=f"Error ejecutando adb: {exc}")

    all_ids: list[str] = []
    unoq_ids: list[str] = []
    for raw in (out.stdout or "").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        dev_id, state = parts[0], parts[1]
        all_ids.append(f"{dev_id} ({state})")
        if state != "device":
            continue  # unauthorized/offline no cuentan como listos
        if dev_id in _ADB_IGNORE_IDS:
            continue  # teléfono, no es el UNO Q
        unoq_ids.append(dev_id)

    if unoq_ids:
        chosen = unoq_ids[0]
        extra = f" (+{len(unoq_ids) - 1} más)" if len(unoq_ids) > 1 else ""
        return UnoqStatus(
            online=True,
            device_id=chosen,
            detail=f"UNO Q por ADB: {chosen}{extra}",
            all_ids=all_ids,
        )
    detail = "UNO Q no detectado por ADB."
    if all_ids:
        detail += " Visto: " + ", ".join(all_ids)
    return UnoqStatus(online=False, detail=detail, all_ids=all_ids)


# --------------------------------------------------------------------------- #
# Estado de RED de los dispositivos (vía el servidor FastAPI)
# --------------------------------------------------------------------------- #
def network_status(timeout: float = 2.0) -> dict:
    """
    Consulta al servidor el estado de RED (heartbeat) de ESP32-CAM y UNO Q.

    Hace `GET http://127.0.0.1:8000/device/status` y normaliza la respuesta a:
        {
          "esp32cam": {"online": bool, "wifi_rssi": ..., "last_seen": ..., "fw": ...},
          "unoq":     {"online": bool, "wifi_rssi": ..., "last_seen": ...},
        }
    Si el servidor no responde (apagado, timeout, error de red) devuelve
        {"_server_down": True}
    para que la GUI pinte el semáforo de Red en gris ("servidor apagado").

    Nunca lanza: cualquier error se traduce a _server_down o a devices vacíos.
    El llamador debe correrlo en un hilo (igual que detect_*).
    """
    url = "http://127.0.0.1:8000/device/status"
    try:
        import requests  # import perezoso (dep del lado servidor/GUI)

        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 — servidor caído/timeout/JSON inválido
        return {"_server_down": True}

    devs = data.get("devices", {}) if isinstance(data, dict) else {}
    out: dict = {}
    for key in ("esp32cam", "unoq"):
        d = devs.get(key, {}) if isinstance(devs, dict) else {}
        if not isinstance(d, dict):
            d = {}
        out[key] = {
            "online": bool(d.get("online", False)),
            "wifi_rssi": d.get("wifi_rssi"),
            "last_seen": d.get("last_seen"),
            "fw": d.get("fw"),
        }
    return out


if __name__ == "__main__":
    print("== devices self-test ==")
    e = detect_esp32()
    print("ESP32:", e)
    u = detect_unoq()
    print("UNO Q:", u)
    print("network_status():", network_status())

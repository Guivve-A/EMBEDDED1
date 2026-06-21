"""
core/system_ctrl.py — Armar/Desarmar la vigilancia vía el servidor.

El "sistema" se controla por el flag `armed` del servidor (POST /arm, /disarm).
El cloud_bridge del UNO Q sincroniza ese flag y manda ARM/DISARM al MCU. Al
desarmar, el servidor además limpia disparos pendientes (sistema en reposo).

En modo dev (API_KEY vacío) estos endpoints no exigen cabecera. Todas las
funciones son tolerantes a "servidor caído" (devuelven (False, motivo) sin lanzar).
"""

from __future__ import annotations

import requests


def _base(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def arm(host: str = "127.0.0.1", port: int = 8000, timeout: float = 4.0) -> tuple[bool, str]:
    """POST /arm {armed:true}. Devuelve (ok, mensaje)."""
    try:
        r = requests.post(f"{_base(host, port)}/arm", json={"armed": True}, timeout=timeout)
        if r.status_code == 200:
            return True, "Sistema ARMADO (vigilancia activa)."
        return False, f"El servidor respondió {r.status_code} al armar."
    except requests.RequestException as exc:
        return False, f"No se pudo contactar el servidor (¿está montado?): {exc}"


def disarm(host: str = "127.0.0.1", port: int = 8000, timeout: float = 4.0) -> tuple[bool, str]:
    """POST /disarm. Devuelve (ok, mensaje). Deja el sistema en reposo (off)."""
    try:
        r = requests.post(f"{_base(host, port)}/disarm", timeout=timeout)
        if r.status_code == 200:
            return True, "Sistema DESARMADO (en reposo; disparos pendientes limpiados)."
        return False, f"El servidor respondió {r.status_code} al desarmar."
    except requests.RequestException as exc:
        return False, f"No se pudo contactar el servidor (¿está montado?): {exc}"


def trigger_intrusion(host: str = "127.0.0.1", port: int = 8000, timeout: float = 6.0) -> tuple[bool, str]:
    """POST /intrusion — dispara captura + validación facial desde el ESP32-CAM."""
    try:
        r = requests.post(f"{_base(host, port)}/intrusion", timeout=timeout)
        if r.status_code == 200:
            return True, "Intrusion disparada: el ESP32-CAM tomará foto y validará."
        return False, f"El servidor respondió {r.status_code}."
    except requests.RequestException as exc:
        return False, f"No se pudo contactar el servidor (¿está montado?): {exc}"

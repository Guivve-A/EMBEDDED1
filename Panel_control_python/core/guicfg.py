"""
core/guicfg.py — Persistencia de la configuración de la PROPIA GUI.

Guarda en gui_config.json (junto al paquete) cosas que conviene recordar entre
sesiones: última IP del servidor usada, último TOKEN de Telegram tecleado,
últimos SSIDs del UNO Q, etc. NO toca el .env del servidor (eso lo hace
telegram_wizard); esto es solo memoria de comodidad de la interfaz.

Diseño defensivo: si el archivo está corrupto o no existe, se devuelven los
defaults sin lanzar. La escritura es atómica (archivo temporal + replace).
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import paths

# Valores por defecto de la config de la GUI.
_DEFAULTS: dict[str, Any] = {
    "server_ip": "",          # IP que el usuario fija para los dispositivos/app
    "telegram_token": "",     # último token tecleado (comodidad; el real va al .env)
    "unoq_ssid1": "",
    "unoq_ssid2": "",
    "unoq_server_host": "",   # host/IP del servidor para el UNO Q (cloud.json)
    # --- "Red de trabajo": la red en la que se configuraron los dispositivos. ---
    # Se fija cuando el usuario configura el ESP32-CAM o el UNO Q. Sirve para
    # detectar incoherencias si luego la PC cambia de red (otra SSID / otra IP).
    "work_ssid": "",          # SSID con el que se configuraron los dispositivos
    "work_server_ip": "",     # IP del servidor que quedó grabada en los dispositivos
    "device_ip": "",          # IP conocida de un dispositivo (para "Probar alcance")
}


def load() -> dict[str, Any]:
    """
    Lee gui_config.json fusionado con los defaults (todas las claves presentes).

    Nunca lanza: ante archivo ausente o corrupto devuelve una copia de _DEFAULTS.
    """
    cfg = dict(_DEFAULTS)
    try:
        with open(paths.GUI_CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for k in cfg:
                if k in data:
                    cfg[k] = data[k]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save(cfg: dict[str, Any]) -> bool:
    """
    Persiste el dict de config (escritura atómica). Devuelve True si se escribió.

    Solo conserva las claves conocidas (_DEFAULTS) para no acumular basura.
    """
    clean = {k: cfg.get(k, _DEFAULTS[k]) for k in _DEFAULTS}
    try:
        paths.GUI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(paths.GUI_CONFIG_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2)
        os.replace(tmp, paths.GUI_CONFIG_FILE)
        return True
    except OSError:
        return False


def update(**kwargs: Any) -> dict[str, Any]:
    """Carga, aplica los cambios pasados por kwargs, guarda y devuelve la config."""
    cfg = load()
    for k, v in kwargs.items():
        if k in _DEFAULTS:
            cfg[k] = v
    save(cfg)
    return cfg


if __name__ == "__main__":
    print("load() ->", load())

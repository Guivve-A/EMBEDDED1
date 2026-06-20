"""
config.py — Configuración central del servidor FastAPI (FASE 6).

Propósito:
    Cargar TODA la configuración desde un archivo `.env` (vía python-dotenv) y
    exponerla como constantes del módulo. Prohibido hardcodear secretos o rutas
    en el resto del código: todo lo configurable vive aquí.

Inputs:
    - Variables de entorno (opcionalmente desde `.env` en esta carpeta).
Outputs:
    - Constantes de módulo (rutas absolutas, threshold, host/puerto, placeholders
      de secretos para Telegram/FCM que se usarán en Fases 8/9).

Notas:
    - Las rutas se resuelven en absoluto respecto a la ubicación de este archivo,
      de modo que el servidor funcione sin importar el CWD desde el que se lance.
    - Las carpetas de storage se crean al importar (idempotente).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Carga del archivo .env (si existe). No falla si no está: usamos defaults.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _env_str(key: str, default: str) -> str:
    """Lee una variable de entorno como string con valor por defecto."""
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    """Lee una variable de entorno como int con valor por defecto y validación."""
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Lee una variable de entorno como float con valor por defecto y validación."""
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Rutas de almacenamiento (absolutas, derivadas de BASE_DIR salvo override).
# ---------------------------------------------------------------------------
STORAGE_DIR = Path(_env_str("STORAGE_DIR", str(BASE_DIR / "storage")))
PHOTOS_DIR = Path(_env_str("PHOTOS_DIR", str(STORAGE_DIR / "photos")))
EMBEDDINGS_FILE = Path(_env_str("EMBEDDINGS_FILE", str(STORAGE_DIR / "embeddings.pkl")))
EVENTS_DB = Path(_env_str("EVENTS_DB", str(STORAGE_DIR / "events.db")))
FCM_TOKENS_FILE = Path(_env_str("FCM_TOKENS_FILE", str(STORAGE_DIR / "fcm_tokens.json")))
STATE_FILE = Path(_env_str("STATE_FILE", str(STORAGE_DIR / "state.json")))
# Estado de dispositivos físicos (heartbeats de ESP32-CAM / UNO Q). JSON simple:
# { "<device_id>": { "last_seen": iso8601, "camera_ok"?, "wifi_rssi"?, "fw"? } }
DEVICE_STATUS_FILE = Path(_env_str("DEVICE_STATUS_FILE", str(STORAGE_DIR / "device_status.json")))

# ---------------------------------------------------------------------------
# Parámetros de reconocimiento facial (consumidos por services/recognition.py).
# El motor real (DeepFace/ArcFace) llega en FASE 7; aquí solo la config.
# ---------------------------------------------------------------------------
DEEPFACE_MODEL = _env_str("DEEPFACE_MODEL", "ArcFace")
DEEPFACE_DETECTOR = _env_str("DEEPFACE_DETECTOR", "opencv")
# Threshold de distancia/similitud para aceptar un match. Ajustable sin recompilar.
THRESHOLD = _env_float("THRESHOLD", 0.6)

# ---------------------------------------------------------------------------
# Secretos / integraciones externas — placeholders.
# Telegram se implementa en FASE 8, FCM en FASE 9. Aquí solo se cargan.
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = _env_str("TELEGRAM_TOKEN", "")          # TODO Fase 8
TELEGRAM_CHAT_ID = _env_str("TELEGRAM_CHAT_ID", "")      # TODO Fase 8
FCM_CREDENTIALS_PATH = _env_str(
    "FCM_CREDENTIALS_PATH", str(BASE_DIR / "secrets" / "serviceAccountKey.json")
)                                                         # TODO Fase 9

# ---------------------------------------------------------------------------
# Servidor HTTP.
# ---------------------------------------------------------------------------
HOST = _env_str("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)

# CORS: red local + proyecto académico → abierto. Configurable por si se cierra.
CORS_ORIGINS = _env_str("CORS_ORIGINS", "*")

# Nivel de log para el middleware y servicios.
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Endurecimiento para despliegue en la nube (hardening).
# ---------------------------------------------------------------------------
# API_KEY: si está VACÍA → modo dev (sin protección). Si está definida, los
# endpoints sensibles exigen el header `X-API-Key` con este mismo valor (ver
# middleware en main.py). Genera una con:
#     python -c "import secrets;print(secrets.token_urlsafe(32))"
API_KEY = _env_str("API_KEY", "")

# Días de retención de fotos en PHOTOS_DIR. La tarea periódica del lifespan
# borra los archivos más antiguos que este umbral (privacidad + disco).
PHOTO_RETENTION_DAYS = _env_int("PHOTO_RETENTION_DAYS", 7)

# Cada cuántas horas corre la pasada de borrado de fotos antiguas.
PHOTO_CLEANUP_INTERVAL_HOURS = _env_int("PHOTO_CLEANUP_INTERVAL_HOURS", 6)

# Segundos sin heartbeat tras los cuales un dispositivo se considera offline
# en GET /device/status. La ESP32-CAM/UNO Q reportan cada ~15-30 s, así que
# 45 s tolera perder un latido sin marcar falso offline.
DEVICE_OFFLINE_AFTER_S = _env_int("DEVICE_OFFLINE_AFTER_S", 45)


def ensure_dirs() -> None:
    """
    Crea las carpetas de almacenamiento necesarias si no existen.

    Inputs:  ninguno (usa las constantes del módulo).
    Outputs: ninguno (efecto secundario: directorios creados en disco).
    Idempotente: seguro llamarlo en cada arranque.
    """
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)


# Asegura las carpetas al importar el módulo (antes de que main.py las use).
ensure_dirs()

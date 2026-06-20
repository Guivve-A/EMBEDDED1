"""
core/paths.py — Rutas absolutas del proyecto EMBEBIDOS_1 (única fuente de verdad).

Todas las rutas se derivan de PROJECT_ROOT (la raíz del repo), que se calcula a
partir de la ubicación de este archivo:
    Panel_control_python/core/paths.py  ->  ../../  ->  EMBEBIDOS_1/

Si en el futuro se mueve el repo, NADA más hay que tocar: el resto de módulos
importa estas constantes en vez de hardcodear C:\\Users\\... por todos lados.

Notas:
    - No se valida que cada ruta exista al importar (la GUI debe seguir abriendo
      aunque, p. ej., aún no exista el venv). Usa los helpers *_ok() para chequear.
"""

from __future__ import annotations

from pathlib import Path

# Panel_control_python/core/paths.py -> sube 2 niveles -> raíz del repo.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Servidor FastAPI
# --------------------------------------------------------------------------- #
SERVER_DIR: Path = PROJECT_ROOT / "Server_python_fastapi" / "face_server"
SERVER_VENV_PY: Path = SERVER_DIR / ".venv" / "Scripts" / "python.exe"
SERVER_ENV_FILE: Path = SERVER_DIR / ".env"

# --------------------------------------------------------------------------- #
# ESP32-CAM (PlatformIO)
# --------------------------------------------------------------------------- #
ESP32_DIR: Path = PROJECT_ROOT / "Code_platform_io_esp32cam"
ESP32_ENV: str = "esp32cam"  # nombre del [env:...] en platformio.ini

# --------------------------------------------------------------------------- #
# Arduino UNO Q (App Lab + scripts de host)
# --------------------------------------------------------------------------- #
UNOQ_APP_DIR: Path = (
    PROJECT_ROOT
    / "Code_platform_io_arduinoq"
    / "sketch_unoq"
    / "face_security_f5"
)
UNOQ_CLOUD_EXAMPLE: Path = UNOQ_APP_DIR / "cloud.json.example"
UNOQ_FS_WIFI: Path = UNOQ_APP_DIR / "host" / "fs_wifi.sh"
# Carpeta de la app ya staged en el propio UNO Q (lado Linux).
UNOQ_REMOTE_APP_DIR: str = "/home/arduino/ArduinoApps/face_security_f5"

# --------------------------------------------------------------------------- #
# App Android (APK de debug)
# --------------------------------------------------------------------------- #
ANDROID_DIR: Path = PROJECT_ROOT / "App_kotlin_androidStudio"
ANDROID_APK: Path = (
    ANDROID_DIR / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
)

# --------------------------------------------------------------------------- #
# Herramientas externas (rutas conocidas del entorno del usuario; con fallback
# a buscarlas en el PATH si no estuvieran en la ruta esperada).
# --------------------------------------------------------------------------- #
ADB_EXE: Path = Path(
    r"C:\Users\ADMIN\AppData\Local\Android\Sdk\platform-tools\adb.exe"
)
PIO_EXE: Path = Path(r"C:\Users\ADMIN\.platformio\penv\Scripts\pio.exe")

# Config persistente de la propia GUI (junto a este paquete).
GUI_DIR: Path = PROJECT_ROOT / "Panel_control_python"
GUI_CONFIG_FILE: Path = GUI_DIR / "gui_config.json"


def server_ready() -> bool:
    """True si existen el venv del server y main.py (mínimo para montarlo)."""
    return SERVER_VENV_PY.is_file() and (SERVER_DIR / "main.py").is_file()


def esp32_ready() -> bool:
    """True si existe el proyecto PlatformIO del ESP32-CAM."""
    return (ESP32_DIR / "platformio.ini").is_file()


def unoq_ready() -> bool:
    """True si existe la app del UNO Q (carpeta f5) en el repo local."""
    return UNOQ_APP_DIR.is_dir()


def adb_path() -> str:
    """Ruta de adb: la conocida si existe, si no 'adb' (que esté en PATH)."""
    return str(ADB_EXE) if ADB_EXE.is_file() else "adb"


def pio_path() -> str:
    """Ruta de pio: la conocida si existe, si no 'pio' (que esté en PATH)."""
    return str(PIO_EXE) if PIO_EXE.is_file() else "pio"


if __name__ == "__main__":
    # Pequeño volcado de diagnóstico (verificación headless).
    print("PROJECT_ROOT     :", PROJECT_ROOT, PROJECT_ROOT.is_dir())
    print("SERVER_DIR       :", SERVER_DIR, SERVER_DIR.is_dir())
    print("SERVER_VENV_PY   :", SERVER_VENV_PY, SERVER_VENV_PY.is_file())
    print("SERVER_ENV_FILE  :", SERVER_ENV_FILE, SERVER_ENV_FILE.is_file())
    print("ESP32_DIR        :", ESP32_DIR, ESP32_DIR.is_dir())
    print("UNOQ_APP_DIR     :", UNOQ_APP_DIR, UNOQ_APP_DIR.is_dir())
    print("UNOQ_CLOUD_EX    :", UNOQ_CLOUD_EXAMPLE, UNOQ_CLOUD_EXAMPLE.is_file())
    print("UNOQ_FS_WIFI     :", UNOQ_FS_WIFI, UNOQ_FS_WIFI.is_file())
    print("ANDROID_APK      :", ANDROID_APK, ANDROID_APK.is_file())
    print("ADB_EXE          :", ADB_EXE, ADB_EXE.is_file())
    print("PIO_EXE          :", PIO_EXE, PIO_EXE.is_file())
    print("server_ready()   :", server_ready())
    print("esp32_ready()    :", esp32_ready())
    print("unoq_ready()     :", unoq_ready())

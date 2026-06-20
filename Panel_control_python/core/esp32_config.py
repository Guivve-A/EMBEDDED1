"""
core/esp32_config.py — Flasheo del ESP32-CAM desde la GUI (PlatformIO).

Corre `pio run -e esp32cam -t upload` en la carpeta del proyecto ESP32-CAM y
hace STREAM de su salida línea a línea por un callback `on_log`, para que la GUI
muestre el progreso en vivo SIN congelarse (el llamador lo ejecuta en un hilo).

Detalles importantes:
    - Antes de compilar, copia src/config.h.example -> src/config.h si config.h
      no existe (el firmware no compila sin él). NO sobrescribe un config.h ya
      presente (puede tener la IP/secretos del usuario).
    - Devuelve el código de salida de pio (0 = OK). Mapea errores típicos
      (puerto ocupado, driver, no encontrado) a un texto claro.
    - El upload puede tardar; el timeout es generoso y se puede cancelar matando
      el proceso (cancel()).

Verificación headless: NO se flashea de verdad (requiere hardware). El bloque
__main__ solo valida rutas y la preparación de config.h en modo "dry-run".
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from . import netinfo
from . import paths

LogFn = Callable[[str], None]


def _noop(_: str) -> None:
    """Callback de log por defecto."""


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def inject_server_host(
    ip: str | None = None,
    port: int = 8000,
    on_log: LogFn = _noop,
    config_path: Path | None = None,
) -> bool:
    """
    Reescribe el SERVER_HOST/SERVER_PORT del bloque LOCAL (#else) de config.h.

    El firmware tiene dos bloques de servidor en config.h:
        #if USE_TLS   -> NUBE  (HTTPS, dominio público)   <- NO se toca
        #else         -> LOCAL (HTTP plano contra la PC)  <- SE inyecta aquí
    Esta función localiza el bloque `#else ... #endif` y reemplaza dentro de él
    SOLO las líneas `#define SERVER_HOST ...` y `#define SERVER_PORT ...`, con la
    IP ACTUAL de la PC. Así el fallback siempre apunta a la red de campo actual
    (el portal AP del ESP32 puede sobreescribir en NVS si hace falta).

    Inputs:
        ip:          IP a inyectar; si None se descubre con netinfo (IP actual).
        port:        puerto del servidor (8000 por defecto).
        config_path: ruta de config.h a editar; si None usa la real del proyecto.
                     (Se pasa explícita en las pruebas headless sobre una COPIA.)
    Outputs:
        True si config.h quedó con el SERVER_HOST inyectado; False si hubo error.

    El reemplazo es robusto por regex y NO toca el bloque #if USE_TLS (nube).
    """
    if ip is None:
        try:
            ip = netinfo.current_wifi().get("ip", "") or netinfo.local_ip()
        except Exception:  # noqa: BLE001 — nunca romper el flasheo por netinfo
            ip = netinfo.local_ip()

    target = config_path if config_path is not None else (
        paths.ESP32_DIR / "src" / "config.h"
    )

    # Si no existe el config.h real, créalo desde el .example antes de inyectar.
    if config_path is None and not target.is_file():
        if not ensure_config_h(on_log):
            return False

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        on_log(f"ERROR leyendo config.h: {exc}")
        return False

    # Aislar el bloque LOCAL: desde el primer '#else' tras '#if USE_TLS' hasta el
    # '#endif' que cierra ese condicional. Solo dentro de ese bloque se reemplaza.
    else_match = re.search(r"#if\s+USE_TLS\b.*?\n(\s*#else\b)", text, re.DOTALL)
    if not else_match:
        on_log("ERROR: no se encontró el bloque '#else' (LOCAL) en config.h.")
        return False
    block_start = else_match.start(1)
    endif_match = re.search(r"#endif", text[block_start:])
    if not endif_match:
        on_log("ERROR: no se encontró el '#endif' del bloque LOCAL en config.h.")
        return False
    block_end = block_start + endif_match.start()

    head = text[:block_start]
    block = text[block_start:block_end]
    tail = text[block_end:]

    def _sub_host(m: re.Match) -> str:
        return f'{m.group(1)}"{ip}"'

    new_block, n_host = re.subn(
        r'(#define\s+SERVER_HOST\s+)"[^"]*"', _sub_host, block
    )
    new_block, n_port = re.subn(
        r"(#define\s+SERVER_PORT\s+)\d+", rf"\g<1>{int(port)}", new_block
    )
    if n_host == 0:
        on_log("ERROR: no se halló '#define SERVER_HOST' en el bloque LOCAL.")
        return False

    new_text = head + new_block + tail
    try:
        target.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        on_log(f"ERROR escribiendo config.h: {exc}")
        return False

    on_log(f"config.h: SERVER_HOST={ip}  SERVER_PORT={int(port)} (bloque LOCAL).")
    return True


def ensure_config_h(on_log: LogFn = _noop) -> bool:
    """
    Garantiza que exista src/config.h (lo crea desde el .example si falta).

    Outputs: True si config.h existe o se creó; False si ni siquiera hay .example.
    No sobrescribe un config.h existente (preserva la config del usuario).
    """
    config_h = paths.ESP32_DIR / "src" / "config.h"
    example = paths.ESP32_DIR / "src" / "config.h.example"
    if config_h.is_file():
        on_log("src/config.h ya existe (no se toca).")
        return True
    if not example.is_file():
        on_log("ERROR: no existe src/config.h ni src/config.h.example.")
        return False
    try:
        shutil.copyfile(example, config_h)
        on_log("Creado src/config.h desde config.h.example (revisa SERVER_HOST).")
        return True
    except OSError as exc:
        on_log(f"ERROR copiando config.h: {exc}")
        return False


class Esp32Flasher:
    """
    Lanza y monitorea un `pio run -t upload` con streaming de salida.

    Uso desde la GUI (en un hilo):
        fl = Esp32Flasher()
        rc = fl.flash(on_log=panel.log)     # bloquea hasta terminar; rc==0 OK
    Cancelación: otra llamada (p. ej. botón) puede invocar fl.cancel().
    """

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self, on_log: LogFn = _noop) -> None:
        """Marca cancelación y mata el proceso pio si está vivo."""
        self._cancelled = True
        if self.proc is not None and self.proc.poll() is None:
            on_log("Cancelando flasheo...")
            try:
                self.proc.kill()
            except OSError:
                pass

    def flash(self, on_log: LogFn = _noop, timeout: float = 600.0) -> int:
        """
        Compila y sube el firmware del ESP32-CAM, streameando la salida.

        Inputs:
            on_log:  callback por cada línea de salida de pio + mensajes propios.
            timeout: segundos máximos para todo el run (compilar + subir).
        Outputs:
            código de retorno de pio (0 = éxito). -1 si no se pudo lanzar,
            -2 si fue cancelado, -3 si hubo timeout.
        """
        self._cancelled = False

        if not paths.esp32_ready():
            on_log(f"ERROR: no se encontró el proyecto en {paths.ESP32_DIR}")
            return -1
        if not ensure_config_h(on_log):
            return -1
        # Inyecta la IP ACTUAL de la PC en el fallback LOCAL antes de compilar,
        # para que el firmware apunte siempre a la red de campo detectada ahora.
        inject_server_host(on_log=on_log)

        cmd = [
            paths.pio_path(),
            "run",
            "-e",
            paths.ESP32_ENV,
            "-t",
            "upload",
        ]
        on_log("Flasheando ESP32-CAM...")
        on_log("  " + " ".join(cmd))
        on_log(f"  cwd = {paths.ESP32_DIR}")

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(paths.ESP32_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # unifica stderr en stdout para un solo stream
                text=True,
                bufsize=1,  # line-buffered
                creationflags=_NO_WINDOW,
            )
        except FileNotFoundError:
            on_log("ERROR: no se encontró 'pio'. ¿PlatformIO instalado?")
            return -1
        except OSError as exc:
            on_log(f"ERROR al lanzar pio: {exc}")
            return -1

        # Watchdog de timeout en hilo aparte (mata el proceso si se pasa).
        timed_out = {"flag": False}

        def _watchdog() -> None:
            try:
                self.proc.wait(timeout=timeout)  # type: ignore[union-attr]
            except subprocess.TimeoutExpired:
                timed_out["flag"] = True
                try:
                    self.proc.kill()  # type: ignore[union-attr]
                except OSError:
                    pass

        wd = threading.Thread(target=_watchdog, daemon=True)
        wd.start()

        # Stream línea a línea (esto es lo que hace que la GUI vea progreso real).
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            on_log(line.rstrip("\n"))
        rc = self.proc.wait()
        wd.join(timeout=1.0)

        if self._cancelled:
            on_log("Flasheo CANCELADO por el usuario.")
            return -2
        if timed_out["flag"]:
            on_log(f"ERROR: timeout ({int(timeout)} s) flasheando el ESP32-CAM.")
            return -3

        if rc == 0:
            on_log("Flasheo OK. Ahora configura el WiFi del ESP32-CAM:")
            on_log("  1) Conéctate a la red WiFi 'FaceCam_Setup' (clave: facecam1234).")
            on_log("  2) Abre http://192.168.4.1 en el navegador.")
            on_log("  3) Ingresa tu red WiFi y la IP del servidor (esta PC).")
        else:
            on_log(f"ERROR: pio terminó con código {rc}.")
            on_log(_hint_for_failure(rc))
        return rc


def erase(on_log: LogFn = _noop, timeout: float = 300.0) -> int:
    """
    Borra por completo la flash del ESP32-CAM (`pio run -e esp32cam -t erase`).

    Esto borra el firmware y la NVS (donde el portal AP guardó WiFi + IP del
    servidor), de modo que en el siguiente arranque el ESP32 vuelve a levantar
    el portal de configuración 'FaceCam_Setup'. Se streamea la salida de pio
    línea a línea por `on_log` (mismo patrón que flash()); el llamador lo corre
    en un hilo para no congelar la GUI.

    Inputs:
        on_log:  callback por cada línea de salida de pio + mensajes propios.
        timeout: segundos máximos para el erase.
    Outputs:
        código de retorno de pio (0 = éxito). -1 si no se pudo lanzar,
        -3 si hubo timeout.
    """
    if not paths.esp32_ready():
        on_log(f"ERROR: no se encontró el proyecto en {paths.ESP32_DIR}")
        return -1

    cmd = [
        paths.pio_path(),
        "run",
        "-e",
        paths.ESP32_ENV,
        "-t",
        "erase",
    ]
    on_log("Borrando flash + NVS del ESP32-CAM (forzar portal)...")
    on_log("  " + " ".join(cmd))
    on_log(f"  cwd = {paths.ESP32_DIR}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(paths.ESP32_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        on_log("ERROR: no se encontró 'pio'. ¿PlatformIO instalado?")
        return -1
    except OSError as exc:
        on_log(f"ERROR al lanzar pio: {exc}")
        return -1

    timed_out = {"flag": False}

    def _watchdog() -> None:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out["flag"] = True
            try:
                proc.kill()
            except OSError:
                pass

    wd = threading.Thread(target=_watchdog, daemon=True)
    wd.start()

    assert proc.stdout is not None
    for line in proc.stdout:
        on_log(line.rstrip("\n"))
    rc = proc.wait()
    wd.join(timeout=1.0)

    if timed_out["flag"]:
        on_log(f"ERROR: timeout ({int(timeout)} s) borrando el ESP32-CAM.")
        return -3
    if rc == 0:
        on_log("Flash + NVS borradas. El ESP32 volverá al portal en el próximo boot.")
    else:
        on_log(f"ERROR: pio erase terminó con código {rc}.")
        on_log(_hint_for_failure(rc))
    return rc


def _hint_for_failure(rc: int) -> str:
    """Devuelve una pista de solución según fallos típicos de upload."""
    return (
        "Pistas: (a) revisa que el cable sea de DATOS (no solo carga); "
        "(b) cierra cualquier monitor serie/IDE que tenga el COM abierto; "
        "(c) si es AI-Thinker sin botón, mantén pulsado IO0/BOOT al iniciar el "
        "upload; (d) instala el driver del puente USB-serie (CP210x o CH340)."
    )


if __name__ == "__main__":
    # Verificación headless: NO flashea (sin hardware). Solo valida preparación.
    print("== esp32_config self-test (dry-run, sin flasheo) ==")
    print("esp32_ready() ->", paths.esp32_ready())
    print("ESP32_DIR     ->", paths.ESP32_DIR)
    print("pio_path()    ->", paths.pio_path())
    # No tocamos config.h aquí para no alterar el repo del usuario; solo informamos.
    cfg = paths.ESP32_DIR / "src" / "config.h"
    print("config.h existe ->", cfg.is_file())

"""
core/server_ctrl.py — Control del servidor FastAPI (uvicorn) para la GUI.

Responsabilidad:
    - start(): lanza uvicorn con el python del venv del server (subprocess.Popen,
      cwd = face_server), espera a que GET / responda 200 (timeout configurable,
      el modelo de reconocimiento tarda en cargar) y reporta progreso por callback.
    - stop(): termina el proceso de forma ordenada (terminate -> kill).
    - is_healthy(): GET / contra el host/puerto dados.
    - status(): combina "¿hay proceso vivo?" + "¿responde el health?".

Diseño:
    - NO usa CustomTkinter: la GUI lo llama dentro de un hilo y recibe progreso
      por el callback `on_log(str)`. Así la UI nunca se congela.
    - El proceso se guarda en una instancia ServerController para poder pararlo.
    - En Windows se crea con CREATE_NEW_PROCESS_GROUP para poder enviar señales
      limpias y para que el árbol de hijos se pueda terminar.

Verificación headless: el bloque __main__ arranca uvicorn en el puerto 8011,
espera health 200 y lo detiene (no usa el 8000 de producción).
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Callable

import requests

from . import paths

LogFn = Callable[[str], None]


def _noop(_: str) -> None:
    """Callback de log por defecto (no hace nada)."""


def is_healthy(host: str = "127.0.0.1", port: int = 8000, timeout: float = 2.0) -> bool:
    """
    True si GET http://host:port/ responde 200.

    Endpoint raíz libre (no requiere API key), ideal como health-check.
    Cualquier excepción de red se traduce a False (no lanza).
    """
    try:
        resp = requests.get(f"http://{host}:{port}/", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


class ServerController:
    """
    Maneja el ciclo de vida de UN proceso uvicorn del servidor de caras.

    Uso típico desde la GUI (en un hilo):
        sc = ServerController()
        sc.start(on_log=panel.log)        # bloquea hasta health o timeout
        ...
        sc.stop(on_log=panel.log)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """
        host/port para el health-check y para el bind de uvicorn.

        NOTA: el bind real de uvicorn usa --host 0.0.0.0 (para que ESP32/UNO Q
        en la LAN lleguen), pero el health se consulta a 127.0.0.1.
        """
        self.host = host
        self.port = port
        self.proc: subprocess.Popen | None = None

    # --------------------------------------------------------------------- #
    # Estado
    # --------------------------------------------------------------------- #
    def is_process_alive(self) -> bool:
        """True si tenemos un Popen y aún no ha terminado."""
        return self.proc is not None and self.proc.poll() is None

    def is_healthy(self, timeout: float = 2.0) -> bool:
        """Atajo a is_healthy() del módulo con el host/puerto de esta instancia."""
        return is_healthy(self.host, self.port, timeout=timeout)

    def status(self) -> str:
        """
        Devuelve "activo" si el health responde, "iniciando" si el proceso vive
        pero aún no responde, "detenido" en caso contrario.
        """
        if self.is_healthy():
            return "activo"
        if self.is_process_alive():
            return "iniciando"
        return "detenido"

    # --------------------------------------------------------------------- #
    # Arranque / parada
    # --------------------------------------------------------------------- #
    def start(
        self,
        on_log: LogFn = _noop,
        health_timeout: float = 60.0,
        bind_host: str = "0.0.0.0",
    ) -> bool:
        """
        Lanza uvicorn y espera a que el health-check pase.

        Inputs:
            on_log:         callback para emitir líneas de progreso (thread-safe
                            a cargo del llamador: la GUI las encola).
            health_timeout: segundos máximos esperando el primer 200 de GET /.
            bind_host:      host de bind de uvicorn (0.0.0.0 para la LAN).
        Outputs:
            True si el servidor quedó "activo" (health 200) dentro del timeout.

        Comportamiento:
            - Si ya hay uno sano en este host/puerto, no lanza otro (devuelve True).
            - Valida que exista el venv python; si no, loguea y devuelve False.
            - El stdout/stderr de uvicorn se redirige a DEVNULL (sus logs salen por
              consola del proceso hijo; la GUI muestra su propio progreso). Se
              evita PIPE sin lector para no bloquear el buffer.
        """
        if self.is_healthy():
            on_log(f"El servidor ya está activo en http://{self.host}:{self.port}")
            return True

        if not paths.SERVER_VENV_PY.is_file():
            on_log(f"ERROR: no existe el python del venv: {paths.SERVER_VENV_PY}")
            return False
        if not (paths.SERVER_DIR / "main.py").is_file():
            on_log(f"ERROR: no existe main.py en {paths.SERVER_DIR}")
            return False

        cmd = [
            str(paths.SERVER_VENV_PY),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            bind_host,
            "--port",
            str(self.port),
        ]
        on_log("Lanzando uvicorn...")
        on_log("  " + " ".join(cmd))
        on_log(f"  cwd = {paths.SERVER_DIR}")

        creationflags = 0
        if sys.platform == "win32":
            # Grupo de proceso propio: permite terminar el árbol limpiamente.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(paths.SERVER_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            on_log(f"ERROR al lanzar uvicorn: {exc}")
            self.proc = None
            return False

        on_log(
            f"Proceso uvicorn iniciado (PID {self.proc.pid}). "
            f"Esperando health-check (hasta {int(health_timeout)} s; "
            "el modelo de IA tarda en cargar)..."
        )

        # Poll del health hasta 200 o timeout. También se aborta si el proceso muere.
        deadline = time.monotonic() + health_timeout
        last_tick = 0.0
        while time.monotonic() < deadline:
            if not self.is_process_alive():
                on_log("ERROR: el proceso uvicorn terminó antes de responder.")
                return False
            if is_healthy(self.host, self.port, timeout=1.5):
                on_log(f"Servidor ACTIVO en http://{self.host}:{self.port}")
                return True
            # Tick de progreso cada ~3 s para que el usuario vea que sigue vivo.
            now = time.monotonic()
            if now - last_tick >= 3.0:
                remaining = int(deadline - now)
                on_log(f"  ...aún cargando (quedan ~{remaining} s)")
                last_tick = now
            time.sleep(1.0)

        on_log(
            "ERROR: timeout esperando el health-check. El proceso sigue vivo; "
            "puedes esperar más o desmontarlo."
        )
        return False

    def stop(self, on_log: LogFn = _noop, kill_timeout: float = 8.0) -> bool:
        """
        Termina el proceso uvicorn de forma ordenada.

        terminate() primero; si no muere en kill_timeout, kill(). Devuelve True
        si al final no queda proceso vivo. Idempotente: si no había proceso,
        loguea y devuelve True.
        """
        if self.proc is None:
            on_log("No hay servidor lanzado por esta GUI para detener.")
            return True
        if self.proc.poll() is not None:
            on_log("El proceso ya estaba terminado.")
            self.proc = None
            return True

        on_log(f"Deteniendo uvicorn (PID {self.proc.pid})...")
        try:
            self.proc.terminate()
        except OSError as exc:
            on_log(f"Aviso al terminar: {exc}")

        try:
            self.proc.wait(timeout=kill_timeout)
        except subprocess.TimeoutExpired:
            on_log("No respondió a terminate(); forzando kill()...")
            try:
                self.proc.kill()
                self.proc.wait(timeout=kill_timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                on_log(f"ERROR forzando kill: {exc}")
                return False

        alive = self.proc.poll() is None
        if not alive:
            on_log("Servidor DETENIDO.")
            on_log("El UNO Q se apagará solo en unos segundos (al detectar que el "
                   "servidor no responde: buzzer y LEDs OFF). El 'armado' se "
                   "conserva y se retoma al volver a montar el servidor.")
            self.proc = None
            return True
        on_log("ERROR: el proceso sigue vivo tras kill().")
        return False


if __name__ == "__main__":
    # --- Verificación headless: ciclo start -> health -> stop en el puerto 8011 ---
    print("== server_ctrl self-test (puerto 8011) ==")
    sc = ServerController(host="127.0.0.1", port=8011)
    ok_start = sc.start(on_log=lambda m: print("[start]", m), health_timeout=90.0)
    print("start() ->", ok_start)
    if ok_start:
        print("health  ->", sc.is_healthy())
        print("status  ->", sc.status())
    ok_stop = sc.stop(on_log=lambda m: print("[stop]", m))
    print("stop()  ->", ok_stop)
    print("status final ->", sc.status())
    sys.exit(0 if (ok_start and ok_stop) else 1)

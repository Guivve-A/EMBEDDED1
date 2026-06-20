"""
webcam_verify.py — Herramienta interactiva de prueba de inferencia facial en vivo.

Propósito (Ing 3 — servidor IA):
    Probar el motor de reconocimiento facial (DeepFace + ArcFace, ya implementado
    y verificado en services/recognition.py) usando la WEBCAM de la PC, sin
    necesidad del Arduino UNO Q ni de la app Kotlin. Sirve para:
        - Enrolar personas rápidamente (tecla 'e').
        - Verificar en vivo si una cara hace match / es intruso / no hay cara
          (tecla ESPACIO).
    El resultado se dibuja como overlay coloreado sobre el feed de la cámara.

Dos modos (argparse):
    - DIRECTO (default): llama recognition.verify()/enroll() en ESTE proceso.
      Baja latencia, ideal para ver la inferencia en vivo. No toca el server.
    - --server: hace POST http://127.0.0.1:8000/verify (y /enroll) enviando el
      frame como JPEG multipart. Prueba el flujo COMPLETO (incluye persistencia
      de eventos, Telegram y FCM tal como los dispara el endpoint).

Teclas:
    ESPACIO → captura el frame actual y lo verifica (en un hilo de trabajo).
    e       → enrolar: entra en "modo nombre" y se teclea el nombre DENTRO de la
              ventana (sin input() de consola). ENTER confirma y enrola el frame
              actual; BACKSPACE borra; ESC cancela.
    q / ESC → salir (libera cámara y cierra ventanas).

ARQUITECTURA UI (anti-congelamiento):
    La inferencia (verify/enroll) tarda ~0.7 s (y ~15 s la PRIMERA vez). Si se
    ejecutara en el hilo principal, cv2.imshow/waitKey se detendrían y Windows
    marcaría la ventana como "No responde". Por eso:
        - El bucle principal SOLO lee frames, dibuja y atiende teclas (~30 fps);
          nunca bloquea.
        - verify/enroll se ejecutan en un HILO DE TRABAJO (InferenceWorker) con
          una cola de un único trabajo. Mientras procesa, se muestra el overlay
          "Procesando..."; al terminar, el resultado se recoge por la cola y se
          muestra ~3 s.
        - La captura del nombre para enrolar ocurre DENTRO de la ventana (estado
          "modo nombre"), de modo que el render nunca se detiene.

⚠️ OBLIGATORIO (igual que recognition.py): se fija TF_USE_LEGACY_KERAS=1 ANTES de
   importar deepface/tensorflow/recognition. Con keras 3 instalado, sin esto el
   import de DeepFace falla. Lo hacemos en la cabecera del módulo.

NOTA DE COLOR (importante):
    OpenCV captura en BGR. recognition.get_embedding/verify/enroll asumen RGB
    (np.ndarray RGB). Por eso, antes de pasar un frame al motor, lo convertimos
    BGR→RGB. Lo que se MUESTRA en pantalla (cv2.imshow) sigue siendo el BGR
    original (imshow espera BGR), así que los colores en la ventana se ven bien.

NOTA DE RENDIMIENTO:
    La PRIMERA inferencia construye el modelo ArcFace (~130 MB la 1ª vez de todas;
    luego cacheado en ~/.deepface). Puede tardar ~15 s. La herramienta avisa
    "cargando modelo..." en consola/overlay durante esa primera llamada.
"""

# --------------------------------------------------------------------------- #
# 1) Variable de entorno ANTES de cualquier import pesado (deepface/tensorflow).
#    setdefault para respetar un valor ya exportado por el usuario.
# --------------------------------------------------------------------------- #
import os

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import argparse
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# config aporta el host/puerto del server y el THRESHOLD (sin números mágicos).
import config


# --------------------------------------------------------------------------- #
# Constantes de presentación / comportamiento (nada de números mágicos sueltos).
# --------------------------------------------------------------------------- #
WINDOW_TITLE = "EMBEBIDOS_1 — Webcam Verify (Ing3)"
DEFAULT_CAM_INDEX = 0

# Duración (segundos) que el overlay de un resultado permanece en pantalla.
OVERLAY_HOLD_SECONDS = 3.0

# Espera (ms) de cv2.waitKey en cada iteración del bucle principal. 1 ms ≈ render
# continuo (~30 fps reales los marca la cámara), de modo que la ventana nunca se
# percibe congelada mientras el worker procesa en segundo plano.
WAITKEY_MS = 1

# Texto del overlay mientras el hilo de trabajo está corriendo una inferencia.
PROCESSING_TEXT = "Procesando..."
# Texto del overlay la PRIMERA vez (la construcción del modelo tarda ~15 s).
PROCESSING_FIRST_TEXT = "Cargando modelo (~15 s)..."

# Longitud máxima del nombre que se puede teclear en "modo nombre" (evita overlays
# desbordados y nombres absurdos).
NAME_MAX_LEN = 40

# Códigos de tecla relevantes para la captura de nombre dentro de la ventana.
KEY_ENTER = 13      # confirmar nombre
KEY_ESC = 27        # cancelar modo nombre / salir
KEY_BACKSPACE = 8   # borrar último carácter (Windows)
KEY_BACKSPACE_ALT = 127  # algunos backends devuelven DEL como backspace

# Colores BGR (OpenCV usa BGR).
COLOR_GREEN = (0, 200, 0)      # match
COLOR_RED = (0, 0, 230)        # intruso / unknown
COLOR_YELLOW = (0, 210, 230)   # no_face
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)

# Tipografía de los overlays.
FONT = cv2.FONT_HERSHEY_SIMPLEX

# URL base del servidor para el modo --server (derivada de config; 0.0.0.0 → 127.0.0.1).
_SERVER_HOST = "127.0.0.1" if config.HOST in ("0.0.0.0", "") else config.HOST
SERVER_BASE_URL = f"http://{_SERVER_HOST}:{config.PORT}"

# Calidad JPEG al codificar el frame para enviarlo al server (modo --server).
JPEG_QUALITY = 90

# Tiempo de espera (s) para las peticiones HTTP del modo --server.
HTTP_TIMEOUT_SECONDS = 30.0


# --------------------------------------------------------------------------- #
# Backend DIRECTO: usa recognition en este mismo proceso.
# --------------------------------------------------------------------------- #
class DirectBackend:
    """
    Backend que llama a FaceRecognitionService directamente (mismo proceso).

    Importa recognition de forma perezosa para que el coste de TensorFlow solo
    se pague cuando realmente se usa este modo.
    """

    def __init__(self) -> None:
        # Import diferido: arrastra TensorFlow, así que solo al instanciar el modo.
        from services.recognition import FaceRecognitionService

        self.service = FaceRecognitionService()
        self.threshold = self.service.threshold  # umbral real del motor (config)

    @staticmethod
    def _bgr_to_rgb(frame_bgr: np.ndarray) -> np.ndarray:
        """Convierte el frame BGR (OpenCV) a RGB, que es lo que espera el motor."""
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    def verify(self, frame_bgr: np.ndarray) -> dict:
        """Verifica un frame BGR. Devuelve el dict tal cual del motor."""
        return self.service.verify(self._bgr_to_rgb(frame_bgr))

    def enroll(self, name: str, frame_bgr: np.ndarray) -> dict:
        """Enrola una persona con un frame BGR. Devuelve el dict del motor."""
        return self.service.enroll(name, [self._bgr_to_rgb(frame_bgr)])

    def warmup(self) -> None:
        """Fuerza la carga del modelo (amortiza la 1ª inferencia lenta)."""
        try:
            self.service.warmup()
        except Exception:  # noqa: BLE001 — warmup nunca debe tumbar la herramienta
            pass


# --------------------------------------------------------------------------- #
# Backend SERVER: habla con el FastAPI vía HTTP (flujo end-to-end completo).
# --------------------------------------------------------------------------- #
class ServerBackend:
    """
    Backend que envía el frame al servidor FastAPI (POST /verify, /enroll).

    Prueba el flujo COMPLETO: el endpoint guarda la foto, registra el evento y
    dispara Telegram/FCM. Útil para verificar la integración de extremo a extremo.
    """

    def __init__(self, base_url: str = SERVER_BASE_URL) -> None:
        import requests  # import diferido: solo se necesita en modo server

        self._requests = requests
        self.base_url = base_url.rstrip("/")
        # En el contrato HTTP el match lo decide el server; el umbral local es
        # solo informativo para el overlay de ayuda.
        self.threshold = config.THRESHOLD

    @staticmethod
    def _encode_jpeg(frame_bgr: np.ndarray) -> bytes:
        """Codifica el frame BGR a bytes JPEG (cv2.imencode espera BGR)."""
        params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        ok, buf = cv2.imencode(".jpg", frame_bgr, params)
        if not ok:
            raise RuntimeError("No se pudo codificar el frame a JPEG.")
        return buf.tobytes()

    def verify(self, frame_bgr: np.ndarray) -> dict:
        """POST /verify con el frame como JPEG multipart. Devuelve el JSON."""
        jpeg = self._encode_jpeg(frame_bgr)
        files = {"file": ("frame.jpg", jpeg, "image/jpeg")}
        resp = self._requests.post(
            f"{self.base_url}/verify", files=files, timeout=HTTP_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return resp.json()

    def enroll(self, name: str, frame_bgr: np.ndarray) -> dict:
        """POST /enroll con name (form) + frame JPEG (multipart). Devuelve el JSON."""
        jpeg = self._encode_jpeg(frame_bgr)
        files = {"file": ("frame.jpg", jpeg, "image/jpeg")}
        data = {"name": name}
        resp = self._requests.post(
            f"{self.base_url}/enroll",
            data=data,
            files=files,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def warmup(self) -> None:
        """En modo server no hay modelo local que cargar; no-op."""
        return None


# --------------------------------------------------------------------------- #
# Hilo de trabajo para inferencia (verify/enroll) — clave anti-congelamiento.
# --------------------------------------------------------------------------- #
class InferenceWorker:
    """
    Ejecuta verify()/enroll() del backend en un HILO DE TRABAJO dedicado.

    El bucle principal (cámara + cv2.imshow + waitKey) NUNCA llama directamente al
    backend: en su lugar encola un "trabajo" aquí y sigue renderizando. Cuando el
    hilo termina, deja el resultado en una cola de salida que el bucle drena sin
    bloquearse. Así la ventana se mantiene fluida aunque la inferencia tarde
    ~0.7 s (o ~15 s la primera vez).

    Política de cola:
        - Cola de entrada de tamaño 1: solo se acepta UN trabajo a la vez. Si ya
          hay uno en curso/encolado, los nuevos disparos (ESPACIO/ENTER) se
          ignoran (se devuelve False en submit), tal como pide el brief.
    """

    def __init__(self, backend) -> None:
        """
        Inputs: backend — DirectBackend o ServerBackend (expone verify/enroll).
        """
        self._backend = backend
        # maxsize=1 → un único trabajo a la vez (los extra se descartan en submit).
        self._jobs: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=1)
        self._results: "queue.Queue[dict]" = queue.Queue()
        # busy: hay un trabajo aceptado y aún sin resultado entregado.
        self._busy = threading.Event()
        self._stop = threading.Event()
        # daemon=True → el hilo no impide que el proceso termine al salir.
        self._thread = threading.Thread(target=self._run, name="inference", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        """True si hay una inferencia en curso (el bucle muestra 'Procesando...')."""
        return self._busy.is_set()

    def submit(self, kind: str, frame_bgr: np.ndarray, name: Optional[str] = None) -> bool:
        """
        Encola un trabajo de inferencia. NO bloquea.

        Inputs:
            kind:      "verify" o "enroll".
            frame_bgr: frame BGR ya capturado (copia congelada del momento).
            name:      nombre a enrolar (solo para kind="enroll").
        Outputs:
            True si se aceptó el trabajo; False si ya había uno en curso (ignorado).
        """
        if self._busy.is_set():
            return False  # ya hay un trabajo: ignoramos el nuevo disparo
        try:
            self._jobs.put_nowait((kind, frame_bgr, name))
        except queue.Full:
            return False
        # Marcamos busy inmediatamente para que un 2º ESPACIO en el mismo frame
        # no cuele otro trabajo antes de que el hilo lo recoja.
        self._busy.set()
        return True

    def poll_result(self) -> Optional[dict]:
        """
        Devuelve el resultado de un trabajo terminado, o None si no hay ninguno.

        Outputs (dict cuando hay resultado):
            { "kind": str, "name": Optional[str], "result": dict|None, "error": str|None }
        El bucle principal lo llama cada iteración (no bloquea).
        """
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def _run(self) -> None:
        """Bucle del hilo: espera trabajos, los procesa y publica resultados."""
        while not self._stop.is_set():
            try:
                job = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            if job is None:  # señal de parada
                break
            kind, frame_bgr, name = job
            out = {"kind": kind, "name": name, "result": None, "error": None}
            try:
                if kind == "verify":
                    out["result"] = self._backend.verify(frame_bgr)
                elif kind == "enroll":
                    out["result"] = self._backend.enroll(name, frame_bgr)
                else:
                    out["error"] = f"trabajo desconocido: {kind}"
            except Exception as exc:  # noqa: BLE001 — un fallo no debe matar el hilo
                out["error"] = str(exc)
            finally:
                # Publicar resultado y liberar 'busy' SOLO al final (evita que el
                # bucle acepte otro trabajo mientras este aún corre).
                self._results.put(out)
                self._busy.clear()

    def shutdown(self) -> None:
        """Detiene el hilo de trabajo de forma ordenada (al salir de la app)."""
        self._stop.set()
        try:
            self._jobs.put_nowait(None)  # despierta al hilo si está esperando
        except queue.Full:
            pass
        self._thread.join(timeout=2.0)


# --------------------------------------------------------------------------- #
# Interpretación del resultado → texto + color del overlay.
# --------------------------------------------------------------------------- #
def result_to_overlay(result: dict) -> tuple[str, tuple[int, int, int]]:
    """
    Traduce el dict de verify() a (texto, color BGR) para el overlay.

    Casos (mismos que devuelve recognition.verify / el endpoint):
        - {"error": "no_face"}                         → amarillo "SIN CARA"
        - {"match": True, person, confidence}          → verde   "OK: <name> (NN%)"
        - {"match": False, person:"unknown", conf}     → rojo    "INTRUSO (NN%)"

    Inputs:  result — dict de verificación.
    Outputs: (texto a mostrar, color BGR).
    """
    if result.get("error") == "no_face":
        return "SIN CARA DETECTADA", COLOR_YELLOW

    confidence = float(result.get("confidence", 0.0))
    pct = round(confidence * 100.0, 1)

    if result.get("match"):
        person = result.get("person", "?")
        return f"OK: {person}  ({pct}%)", COLOR_GREEN

    # match False y había cara → intruso / desconocido.
    return f"INTRUSO / DESCONOCIDO  ({pct}%)", COLOR_RED


# --------------------------------------------------------------------------- #
# Dibujo de overlays sobre el frame.
# --------------------------------------------------------------------------- #
def _draw_text(
    frame: np.ndarray,
    text: str,
    org: tuple[int, int],
    color: tuple[int, int, int],
    scale: float = 0.6,
    thickness: int = 2,
) -> None:
    """
    Dibuja texto con un contorno negro para legibilidad sobre cualquier fondo.

    Inputs:  frame (se modifica in-place), text, posición org, color, escala, grosor.
    Outputs: ninguno (efecto in-place).
    """
    # Contorno negro (sombra) + texto en color encima.
    cv2.putText(frame, text, org, FONT, scale, COLOR_BLACK, thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, org, FONT, scale, color, thickness, cv2.LINE_AA)


def draw_hud(frame: np.ndarray, fps: float, mode_label: str, threshold: float) -> None:
    """
    Dibuja el HUD permanente: FPS, modo, umbral y ayuda de teclas.

    Inputs:  frame (in-place), fps actual, etiqueta de modo, umbral del motor.
    Outputs: ninguno.
    """
    h = frame.shape[0]
    _draw_text(frame, f"FPS: {fps:4.1f}   modo: {mode_label}   thr: {threshold:.2f}",
               (10, 25), COLOR_WHITE, scale=0.55, thickness=1)
    # Ayuda de teclas, abajo.
    _draw_text(frame, "ESPACIO=verificar   e=enrolar   q/ESC=salir",
               (10, h - 15), COLOR_WHITE, scale=0.55, thickness=1)


def draw_result_overlay(
    frame: np.ndarray, text: str, color: tuple[int, int, int]
) -> None:
    """
    Dibuja una banda con el resultado de la última verificación en el centro-superior.

    Inputs:  frame (in-place), texto del resultado, color BGR.
    Outputs: ninguno.
    """
    w = frame.shape[1]
    # Banda translúcida de fondo para destacar el resultado.
    band_top, band_bottom = 40, 90
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, band_top), (w, band_bottom), COLOR_BLACK, -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
    _draw_text(frame, text, (15, 75), color, scale=0.9, thickness=2)


def draw_name_prompt(frame: np.ndarray, typed_name: str) -> None:
    """
    Dibuja el prompt de "modo nombre": el usuario teclea DENTRO de la ventana.

    Muestra el nombre que se va escribiendo (con un cursor "_") y la ayuda de
    teclas específica del modo. Se redibuja cada frame, así que la ventana sigue
    refrescándose mientras se teclea (no hay input() de consola que bloquee).

    Inputs:  frame (in-place), typed_name — texto acumulado hasta ahora.
    Outputs: ninguno.
    """
    w = frame.shape[1]
    band_top, band_bottom = 40, 110
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, band_top), (w, band_bottom), COLOR_BLACK, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    _draw_text(frame, f"Nombre: {typed_name}_", (15, 75), COLOR_GREEN,
               scale=0.8, thickness=2)
    _draw_text(frame, "ENTER=enrolar   BACKSPACE=borrar   ESC=cancelar",
               (15, 100), COLOR_WHITE, scale=0.5, thickness=1)


# --------------------------------------------------------------------------- #
# Apertura de la cámara con manejo de error claro.
# --------------------------------------------------------------------------- #
def open_camera(index: int) -> Optional[cv2.VideoCapture]:
    """
    Abre la webcam en el índice dado. Devuelve el VideoCapture abierto o None.

    En Windows usa el backend por defecto; si no abre, devuelve None para que el
    caller informe con un mensaje claro y salga limpiamente.
    """
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


# --------------------------------------------------------------------------- #
# Bucle principal interactivo.
# --------------------------------------------------------------------------- #
def _is_typeable_char(key: int) -> Optional[str]:
    """
    Traduce un código de tecla a un carácter aceptable para un nombre, o None.

    Aceptamos letras ASCII, dígitos, espacio, guion y guion bajo (suficiente para
    nombres como "Juan_Perez" o "ana-2"). Inputs: code de cv2.waitKey & 0xFF.
    Outputs: el carácter (str) o None si la tecla no es texto válido.
    """
    if 32 <= key <= 126:  # rango ASCII imprimible
        ch = chr(key)
        if ch.isalnum() or ch in (" ", "-", "_"):
            return ch
    return None


def run_live(backend, cam_index: int, mode_label: str) -> int:
    """
    Bucle interactivo NO BLOQUEANTE: muestra el feed y atiende teclas.

    El bucle principal solo lee/dibuja/atiende teclas; la inferencia corre en un
    InferenceWorker (hilo aparte). El nombre para enrolar se captura DENTRO de la
    ventana mediante un estado "modo nombre". Así la ventana nunca se congela.

    Inputs:  backend (DirectBackend|ServerBackend), índice de cámara, etiqueta de modo.
    Outputs: código de salida (0 OK, 2 cámara no disponible).
    """
    cap = open_camera(cam_index)
    if cap is None:
        print(f"[ERROR] No se pudo abrir la webcam en el indice {cam_index}.")
        print("        Prueba otro indice con --cam 1 (o 2), o verifica que la "
              "camara no este en uso por otra app.")
        return 2

    print(f"[OK] Webcam abierta (indice {cam_index}). Modo: {mode_label}.")
    print("     Teclas: ESPACIO=verificar | e=enrolar (nombre en ventana) | q/ESC=salir")
    print(f"     Umbral del motor (config.THRESHOLD): {backend.threshold}")

    # Hilo de trabajo: aquí se ejecutan verify/enroll sin bloquear el render.
    worker = InferenceWorker(backend)

    # Estado del overlay de resultado (texto, color, hasta cuándo mostrarlo).
    overlay_text: Optional[str] = None
    overlay_color = COLOR_WHITE
    overlay_until = 0.0

    # Estado "modo nombre": si entering_name es True, las teclas alimentan typed_name.
    entering_name = False
    typed_name = ""
    # Frame congelado en el instante de pulsar 'e' (se enrola ESE, no el actual al ENTER).
    pending_enroll_frame: Optional[np.ndarray] = None

    # Bandera para avisar de la 1ª inferencia (carga del modelo) una sola vez.
    first_inference_done = False

    # Cálculo de FPS por suavizado exponencial.
    fps = 0.0
    last_t = time.perf_counter()

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("[ERROR] Falla al leer un frame de la camara. Saliendo.")
                return 2

            # FPS suavizado.
            now = time.perf_counter()
            dt = now - last_t
            last_t = now
            if dt > 0:
                inst_fps = 1.0 / dt
                fps = inst_fps if fps == 0.0 else (0.9 * fps + 0.1 * inst_fps)

            # --- Recoger resultados del worker (no bloquea) ---
            done = worker.poll_result()
            if done is not None:
                first_inference_done = True
                if done["error"] is not None:
                    overlay_text = f"ERROR {done['kind']}: {done['error']}"
                    overlay_color = COLOR_RED
                    print(f"[ERROR {done['kind']}] {done['error']}")
                elif done["kind"] == "verify":
                    overlay_text, overlay_color = result_to_overlay(done["result"])
                    print(f"[VERIFY] {done['result']}")
                else:  # enroll
                    res = done["result"]
                    print(f"[ENROLL] {res}")
                    if res.get("enrolled"):
                        n = res.get("n_photos", "?")
                        overlay_text = f"Enrolado: {done['name']} (fotos: {n})"
                        overlay_color = COLOR_GREEN
                    else:
                        overlay_text = f"NO enrolado: {done['name']} (sin cara?)"
                        overlay_color = COLOR_YELLOW
                overlay_until = time.perf_counter() + OVERLAY_HOLD_SECONDS

            # --- Render: HUD siempre presente ---
            draw_hud(frame, fps, mode_label, backend.threshold)

            # Prioridad de overlays: modo nombre > procesando > último resultado.
            if entering_name:
                draw_name_prompt(frame, typed_name)
            elif worker.busy:
                msg = PROCESSING_FIRST_TEXT if not first_inference_done else PROCESSING_TEXT
                draw_result_overlay(frame, msg, COLOR_WHITE)
            elif overlay_text is not None and now < overlay_until:
                draw_result_overlay(frame, overlay_text, overlay_color)
            elif overlay_text is not None and now >= overlay_until:
                overlay_text = None  # expiró

            cv2.imshow(WINDOW_TITLE, frame)
            key = cv2.waitKey(WAITKEY_MS) & 0xFF

            # ============================================================== #
            # MODO NOMBRE: las teclas construyen el nombre dentro de la ventana
            # ============================================================== #
            if entering_name:
                if key == KEY_ESC:
                    # Cancelar enrolamiento.
                    entering_name = False
                    pending_enroll_frame = None
                    typed_name = ""
                    overlay_text = "Enrolamiento cancelado"
                    overlay_color = COLOR_YELLOW
                    overlay_until = time.perf_counter() + OVERLAY_HOLD_SECONDS
                    print("    Enrolamiento cancelado (ESC).")
                elif key == KEY_ENTER:
                    name = typed_name.strip()
                    entering_name = False
                    if not name:
                        pending_enroll_frame = None
                        typed_name = ""
                        overlay_text = "Enrolamiento cancelado (nombre vacio)"
                        overlay_color = COLOR_YELLOW
                        overlay_until = time.perf_counter() + OVERLAY_HOLD_SECONDS
                        print("    Enrolamiento cancelado (nombre vacio).")
                    else:
                        # Dispara el enroll del frame congelado en el worker.
                        if not first_inference_done:
                            print("[..] Cargando modelo (primera inferencia, ~15 s)...")
                        accepted = worker.submit("enroll", pending_enroll_frame, name)
                        if not accepted:
                            print("[..] Worker ocupado: enrolamiento ignorado.")
                        pending_enroll_frame = None
                        typed_name = ""
                elif key in (KEY_BACKSPACE, KEY_BACKSPACE_ALT):
                    typed_name = typed_name[:-1]
                else:
                    ch = _is_typeable_char(key)
                    if ch is not None and len(typed_name) < NAME_MAX_LEN:
                        typed_name += ch
                # En modo nombre NO procesamos las demás teclas (q/espacio son texto).
                continue

            # ============================================================== #
            # MODO NORMAL
            # ============================================================== #
            # --- Salir (q / ESC) ---
            if key in (ord("q"), KEY_ESC):
                break

            # --- Verificar (ESPACIO) ---
            if key == ord(" "):
                # Encola un verify del frame actual. Si el worker está ocupado,
                # se ignora (submit devuelve False) — sin congelar nada.
                if not first_inference_done:
                    print("[..] Cargando modelo (primera inferencia, ~15 s)...")
                accepted = worker.submit("verify", frame.copy())
                if not accepted:
                    print("[..] Worker ocupado: verificacion ignorada.")

            # --- Enrolar (e): entrar en modo nombre ---
            if key == ord("e"):
                if worker.busy:
                    # No tiene sentido empezar a teclear si ya hay un trabajo.
                    print("[..] Worker ocupado: espera a que termine para enrolar.")
                else:
                    entering_name = True
                    typed_name = ""
                    pending_enroll_frame = frame.copy()  # congela ESTE frame
                    print(">>> Modo nombre: teclea el nombre en la ventana, "
                          "ENTER=enrolar, ESC=cancelar.")

    finally:
        # Liberación garantizada de recursos pase lo que pase.
        worker.shutdown()
        cap.release()
        cv2.destroyAllWindows()

    print("[OK] Camara liberada y ventanas cerradas. Hasta luego.")
    return 0


# --------------------------------------------------------------------------- #
# CLI / entrypoint.
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de la herramienta."""
    parser = argparse.ArgumentParser(
        prog="webcam_verify.py",
        description=(
            "Prueba interactiva del reconocimiento facial (DeepFace/ArcFace) con la "
            "webcam de la PC. Teclas: ESPACIO=verificar, e=enrolar, q/ESC=salir."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cam",
        type=int,
        default=DEFAULT_CAM_INDEX,
        help="Indice de la webcam (cv2.VideoCapture).",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help=(
            f"Usa el servidor FastAPI ({SERVER_BASE_URL}) via HTTP en vez del motor "
            "local (prueba el flujo completo: eventos, Telegram, FCM)."
        ),
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="No precargar el modelo al inicio (modo directo). La 1a inferencia sera lenta.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """
    Punto de entrada. Configura el backend según el modo y lanza el bucle en vivo.

    Outputs: código de salida del proceso.
    """
    args = build_parser().parse_args(argv)

    if args.server:
        try:
            backend = ServerBackend()
        except ImportError:
            print("[ERROR] El modo --server requiere 'requests'. Instala con: "
                  "pip install requests")
            return 1
        mode_label = "SERVER (HTTP)"
        print(f"[INFO] Modo SERVER: enviando frames a {backend.base_url}")
    else:
        backend = DirectBackend()
        mode_label = "DIRECTO (local)"
        print("[INFO] Modo DIRECTO: inferencia en este proceso.")
        if not args.no_warmup:
            print("[..] Precargando modelo ArcFace (puede tardar ~15 s la 1a vez)...")
            backend.warmup()
            print("[OK] Modelo listo.")

    return run_live(backend, args.cam, mode_label)


if __name__ == "__main__":
    sys.exit(main())

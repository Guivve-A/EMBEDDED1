"""
main.py — Aplicación FastAPI del servidor de seguridad facial (FASE 6).

Propósito:
    Exponer TODOS los endpoints del contrato acordado con Ing 1 (app Kotlin) e
    Ing 2 (Arduino UNO Q):
        POST   /verify          (multipart file)   → resultado de reconocimiento
        POST   /enroll          (form name + file) → enrolar persona
        GET    /events          (paginado)         → historial de eventos
        GET    /photos/{id}                         → imagen JPEG del evento
        GET    /enrolled                            → personas registradas
        DELETE /enroll/{name}                       → borrar persona
        POST   /arm             {armed: bool}       → armar/desarmar
        POST   /disarm                              → atajo desarmar
        GET    /state                               → estado del sistema
        POST   /fcm/register    {token}             → registrar token push
        POST   /device/heartbeat {device_id,...}    → latido de ESP32-CAM/UNO Q
        GET    /device/status                       → online/offline de dispositivos

Características transversales:
    - CORS abierto (config.CORS_ORIGINS), proyecto académico en red local.
    - Middleware de logging: timestamp | client_ip | method path | status | latency_ms.
    - Persistencia de eventos en SQLite (aiosqlite).
    - Telegram + FCM se disparan en BackgroundTasks: nunca bloquean la respuesta.

El servicio de reconocimiento es REAL desde la Fase 7 (DeepFace + ArcFace,
embeddings 512-d, similitud coseno). Telegram y FCM siguen como STUBS hasta las
Fases 8 y 9 respectivamente.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import config
from services.enrollment import EnrollmentService
from services.fcm_service import FCMService
from services.recognition import FaceRecognitionService
from services.telegram_service import TelegramService

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("face_server")
access_logger = logging.getLogger("access")

# --------------------------------------------------------------------------- #
# Instancias de servicios (compartidas durante la vida del proceso)
# --------------------------------------------------------------------------- #
recognition = FaceRecognitionService()
enrollment = EnrollmentService(recognition)
telegram_service = TelegramService()
fcm_service = FCMService()


# --------------------------------------------------------------------------- #
# Inicialización / cierre de la app (crea tabla de eventos en SQLite)
# --------------------------------------------------------------------------- #
async def _init_db() -> None:
    """
    Crea la tabla `events` en SQLite si no existe.

    Esquema:
        id          INTEGER PK autoincrement
        ts          TEXT  (ISO8601 UTC del evento)
        match       INTEGER (0/1)
        person      TEXT
        confidence  REAL
        photo_id    TEXT  (nombre del archivo en storage/photos)
        latency_ms  INTEGER
    """
    config.ensure_dirs()
    async with aiosqlite.connect(config.EVENTS_DB) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                match       INTEGER NOT NULL,
                person      TEXT    NOT NULL,
                confidence  REAL    NOT NULL,
                photo_id    TEXT    NOT NULL,
                latency_ms  INTEGER NOT NULL
            )
            """
        )
        await db.commit()


def _warmup_recognition() -> None:
    """
    Precarga el modelo de reconocimiento (bloqueante, pensado para un thread).

    La 1ª inferencia real de DeepFace construye el grafo de TF y descarga los
    pesos (~130 MB la primera vez), lo que puede tardar ~15 s. Hacerlo al
    arranque evita que el primer /verify del Arduino pague ese coste.

    Usa recognition.warmup() (ya existente, atrapa sus propias excepciones); si
    fallara, no debe tumbar el servidor.
    """
    try:
        ok = recognition.warmup()
        if ok:
            logger.info("Warmup de reconocimiento OK (modelo precargado).")
        else:
            logger.warning("Warmup de reconocimiento devolvió False (se cargará en el 1er /verify).")
    except Exception as exc:  # noqa: BLE001 — el warmup nunca debe tumbar el server
        logger.warning("Warmup de reconocimiento falló: %s", exc)


def _purge_old_photos() -> int:
    """
    Borra de PHOTOS_DIR los archivos con antigüedad > PHOTO_RETENTION_DAYS.

    Inputs:  ninguno (usa config).
    Outputs: nº de archivos borrados. Maneja errores por archivo sin romper.
    """
    retention_days = max(0, config.PHOTO_RETENTION_DAYS)
    cutoff = time.time() - retention_days * 86400
    deleted = 0
    photos_dir = config.PHOTOS_DIR
    try:
        if not photos_dir.is_dir():
            return 0
        for entry in photos_dir.iterdir():
            try:
                if not entry.is_file():
                    continue
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    deleted += 1
            except OSError as exc:
                logger.warning("No se pudo borrar la foto %s: %s", entry, exc)
    except OSError as exc:
        logger.warning("Error recorriendo PHOTOS_DIR para limpieza: %s", exc)
    return deleted


async def _photo_cleanup_loop() -> None:
    """
    Tarea periódica (asyncio puro) que purga fotos antiguas cada N horas.

    Corre una pasada inmediata al arrancar y luego duerme
    config.PHOTO_CLEANUP_INTERVAL_HOURS entre pasadas. El borrado (I/O de disco)
    se ejecuta en un thread para no bloquear el event loop. Se cancela limpiamente
    al apagar el servidor.
    """
    interval_s = max(1, config.PHOTO_CLEANUP_INTERVAL_HOURS) * 3600
    try:
        while True:
            try:
                deleted = await asyncio.to_thread(_purge_old_photos)
                if deleted:
                    logger.info(
                        "Limpieza de fotos: %d archivo(s) > %d día(s) borrado(s).",
                        deleted,
                        config.PHOTO_RETENTION_DAYS,
                    )
                else:
                    logger.debug("Limpieza de fotos: nada que borrar.")
            except Exception as exc:  # noqa: BLE001 — la limpieza nunca debe tumbar el loop
                logger.warning("Pasada de limpieza de fotos falló: %s", exc)
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info("Tarea de limpieza de fotos detenida.")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida del servidor:
        - Inicializa la BD de eventos.
        - Lanza el warmup del modelo de reconocimiento en un thread (no bloquea
          el arranque; el 1er /verify espera si aún no terminó).
        - Lanza la tarea periódica de borrado de fotos antiguas (asyncio).
    """
    await _init_db()
    # Estado transitorio limpio al MONTAR: cancela cualquier disparo pendiente o
    # resultado viejo de una sesion anterior (para no validar al instante al
    # remontar). CONSERVA 'armed' -> el sistema "retoma armado" via cloud_bridge.
    _state0 = _read_state_raw()
    _clear_transient(_state0)
    _write_state_raw(_state0)
    logger.info("Estado transitorio reiniciado al montar (armed=%s conservado).",
                _state0.get("armed"))
    # Warmup en background: no bloquea el arranque (uvicorn ya acepta requests).
    asyncio.create_task(asyncio.to_thread(_warmup_recognition))
    cleanup_task = asyncio.create_task(_photo_cleanup_loop())
    logger.info(
        "face_server iniciado. Storage=%s | API_KEY=%s | retención fotos=%d día(s)",
        config.STORAGE_DIR,
        "ON" if config.API_KEY else "OFF (modo dev)",
        config.PHOTO_RETENTION_DAYS,
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("face_server detenido.")


app = FastAPI(
    title="EMBEBIDOS_1 — Face Security Server",
    description="Servidor FastAPI (Fase 6): recibe fotos del UNO Q, reconoce (stub), "
    "almacena, notifica (stub) y sirve la API a la app Kotlin.",
    version="0.6.0",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------- #
# CORS — abierto para red local / proyecto académico.
# --------------------------------------------------------------------------- #
_origins = ["*"] if config.CORS_ORIGINS.strip() == "*" else [
    o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,  # con "*" no se permiten credentials; queda explícito
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Middleware de logging de acceso
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Loguea cada request en el formato:
        timestamp | client_ip | METHOD path | status | latency_ms

    Inputs:  request entrante + siguiente handler.
    Outputs: la response (sin modificar), tras medir la latencia.
    """
    start = time.perf_counter()
    client_ip = request.client.host if request.client else "-"
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        # Aun si el handler explota, dejamos constancia en el log de acceso.
        latency_ms = int((time.perf_counter() - start) * 1000)
        access_logger.error(
            "%s | %s | %s %s | 500 | %d ms",
            datetime.now(timezone.utc).isoformat(),
            client_ip,
            request.method,
            request.url.path,
            latency_ms,
        )
        raise
    latency_ms = int((time.perf_counter() - start) * 1000)
    access_logger.info(
        "%s | %s | %s %s | %d | %d ms",
        datetime.now(timezone.utc).isoformat(),
        client_ip,
        request.method,
        request.url.path,
        status,
        latency_ms,
    )
    return response


# --------------------------------------------------------------------------- #
# Middleware de API key (endurecimiento para despliegue en la nube)
# --------------------------------------------------------------------------- #
# Endpoints sensibles (escritura / control) que exigen X-API-Key cuando
# config.API_KEY está definida. Se comparan (método, path) — los path params se
# tratan con prefijo (p. ej. DELETE /enroll/{name}).
#
# DECISIÓN PM (ampliación post-hardening): quedan LIBRES SOLO los meta y el
# polling de los dispositivos:
#   GET /, /docs, /redoc, /openapi.json, GET /state y GET /capture-request.
# Justificación: GET /state (Arduino, ~5 s) y GET /capture-request (ESP32-CAM,
# ~1.5 s) se sondean muy seguido y no exponen secretos (solo flags de control).
# El resto de lecturas (eventos, fotos, enrolados, estado de dispositivos,
# last-result) sí exponen información personal o de operación, así que en modo
# prod exigen X-API-Key igual que las mutaciones. En modo dev (API_KEY vacía)
# todo sigue libre.
_PROTECTED: tuple[tuple[str, str], ...] = (
    ("POST", "/verify"),
    ("POST", "/enroll"),
    ("DELETE", "/enroll/"),   # prefijo: DELETE /enroll/{name}
    ("POST", "/arm"),
    ("POST", "/disarm"),
    ("POST", "/fcm/register"),
    ("POST", "/device/heartbeat"),
    ("GET", "/device/status"),
    ("GET", "/photos/"),      # prefijo: GET /photos/{photo_id}
    ("GET", "/events"),
    ("DELETE", "/events"),    # destructivo: borrar historial
    ("GET", "/enrolled"),
    # Coordinación sin cables (Parte 1, Ing3):
    ("POST", "/intrusion"),     # control: lo llama el UNO Q
    ("GET", "/last-result"),    # expone resultado de reconocimiento (datos personales)
    ("POST", "/telegram/test"),  # acción de envío real (para la GUI)
    # NOTA: GET /capture-request queda LIBRE a propósito (polling del ESP32-CAM).
)


def _is_protected(method: str, path: str) -> bool:
    """True si (method, path) corresponde a un endpoint sensible que exige API key."""
    # POST /enroll vs DELETE /enroll/{name}: distinguir por método + prefijo.
    for m, p in _PROTECTED:
        if method != m:
            continue
        if p.endswith("/"):
            if path.startswith(p):
                return True
        elif path == p:
            return True
    return False


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """
    Exige el header `X-API-Key` en endpoints sensibles cuando hay API key.

    Comportamiento:
        - config.API_KEY vacía (modo dev): no exige nada → no rompe el server
          local actual ni la app que aún no manda key.
        - config.API_KEY definida (modo prod): si la ruta es sensible y el header
          falta o no coincide → 401. Lecturas/meta quedan libres (ver _PROTECTED).
    """
    if config.API_KEY and _is_protected(request.method, request.url.path):
        provided = request.headers.get("x-api-key", "")
        if provided != config.API_KEY:
            # Este middleware corre por fuera del de logging (se añade después),
            # así que dejamos constancia del 401 aquí para no perderlo en el access log.
            client_ip = request.client.host if request.client else "-"
            access_logger.warning(
                "%s | %s | %s %s | 401 | api_key",
                datetime.now(timezone.utc).isoformat(),
                client_ip,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"error": True, "detail": "API key inválida o ausente"},
            )
    return await call_next(request)


# --------------------------------------------------------------------------- #
# Modelos de request (bodies JSON)
# --------------------------------------------------------------------------- #
class ArmBody(BaseModel):
    """Body de POST /arm — flag armado/desarmado."""
    armed: bool


class FcmRegisterBody(BaseModel):
    """Body de POST /fcm/register — token de la app."""
    token: str


class HeartbeatBody(BaseModel):
    """
    Body de POST /device/heartbeat — latido de un dispositivo físico.

    Campos:
        device_id: str (requerido) — identificador del dispositivo
                   (p. ej. "esp32cam" o "unoq").
        camera_ok: bool (opcional)  — la ESP32-CAM reporta si su cámara responde.
        wifi_rssi: int  (opcional)  — RSSI WiFi en dBm (negativo).
        fw:        str  (opcional)  — versión de firmware del dispositivo.
    """
    device_id: str
    camera_ok: bool | None = None
    wifi_rssi: int | None = None
    fw: str | None = None


# --------------------------------------------------------------------------- #
# Helpers de estado armado/desarmado (persistido en JSON simple)
# --------------------------------------------------------------------------- #
import json  # noqa: E402  (import local agrupado con su helper para claridad)


# Estado por defecto del sistema (todos los campos que viven en STATE_FILE).
# Campos de coordinación sin cables (Parte 1, Ing3):
#   capture_pending: bool  — hay una intrusión esperando captura del ESP32-CAM.
#   capture_ts:      str|None — ISO8601 UTC de la última intrusión que disparó la captura.
#   last_result:     dict|None — último resultado de /verify {match,person,confidence,photo_id,ts}.
#   result_seq:      int   — contador incremental; sube en cada /verify para que el
#                            UNO Q distinga un resultado nuevo de uno ya visto.
#   intruder_notified: bool — en el episodio actual ya se envió la alerta de
#                            intruso (rate-limit: 1 aviso por episodio, no por frame).
_DEFAULT_STATE: dict = {
    "armed": False,
    "last_event_ts": None,
    "capture_pending": False,
    "capture_ts": None,
    "last_result": None,
    "result_seq": 0,
    "intruder_notified": False,
}


def _read_state_raw() -> dict:
    """
    Lee el estado COMPLETO del sistema desde STATE_FILE, fusionado con los
    defaults para garantizar que TODOS los campos existan siempre.

    Outputs: dict con al menos las claves de _DEFAULT_STATE. Si el archivo no
             existe o está corrupto, devuelve una copia de _DEFAULT_STATE.
             Nunca lanza: cualquier campo ausente se rellena con su default.
    """
    state = dict(_DEFAULT_STATE)
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            state.update({k: data.get(k, state[k]) for k in state})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    # Normalización defensiva de tipos clave.
    state["armed"] = bool(state.get("armed", False))
    state["capture_pending"] = bool(state.get("capture_pending", False))
    state["intruder_notified"] = bool(state.get("intruder_notified", False))
    try:
        state["result_seq"] = int(state.get("result_seq", 0))
    except (TypeError, ValueError):
        state["result_seq"] = 0
    return state


def _write_state_raw(state: dict) -> None:
    """
    Persiste el dict de estado COMPLETO en STATE_FILE (preserva todos los campos).

    Inputs:  state — dict completo a escribir (debe contener las claves de estado).
    Outputs: ninguno (efecto secundario: archivo JSON en disco; crea la carpeta padre).
    """
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _read_state() -> dict:
    """
    Lee el estado público del sistema (armado + último evento) desde STATE_FILE.

    Outputs: dict { "armed": bool, "last_event_ts": str|None } — formato histórico
             consumido por GET /state (Arduino + app). No expone los campos
             internos de coordinación; usar _read_state_raw para esos.
    """
    raw = _read_state_raw()
    return {"armed": raw["armed"], "last_event_ts": raw["last_event_ts"]}


def _write_state(armed: bool, last_event_ts: str | None) -> None:
    """
    Persiste armed + last_event_ts preservando el resto de campos del estado.

    Reescribe SOLO armed y last_event_ts sobre el estado actual completo, de modo
    que capture_pending/capture_ts/last_result/result_seq se conserven intactos.
    """
    state = _read_state_raw()
    state["armed"] = armed
    state["last_event_ts"] = last_event_ts
    _write_state_raw(state)


def _clear_transient(state: dict) -> None:
    """Resetea en `state` los campos transitorios de coordinación (no persistentes
    entre 'episodios'): disparo pendiente, último resultado y rate-limit de intruso.
    NO toca armed/last_event_ts ni el historial de eventos (DB)."""
    state["capture_pending"] = False
    state["capture_ts"] = None
    state["last_result"] = None
    state["intruder_notified"] = False


def _set_armed(armed: bool) -> dict:
    """
    Cambia el flag armado y LIMPIA el estado transitorio (disparo pendiente,
    último resultado, rate-limit). Así, armar empieza sin disparos viejos y
    desarmar (sistema OFF, también vía app) cancela cualquier captura pendiente.
    Conserva el último evento. Devuelve el estado público.
    """
    state = _read_state_raw()
    state["armed"] = armed
    _clear_transient(state)
    _write_state_raw(state)
    return _read_state()


def _touch_last_event(ts: str) -> None:
    """Actualiza el timestamp del último evento sin tocar el flag armado."""
    current = _read_state()
    _write_state(current["armed"], ts)


def _set_capture_pending(ts: str) -> dict:
    """
    Marca capture_pending=True con la marca de tiempo de la intrusión (idempotente).

    Inputs:  ts — ISO8601 UTC de la intrusión detectada por el UNO Q.
    Outputs: el estado completo resultante. Llamadas repetidas solo refrescan
             capture_ts (no acumulan estado); preserva armed/last_event_ts/last_result/seq.
    """
    state = _read_state_raw()
    # Un nuevo episodio (no estaba pendiente) reinicia el rate-limit de intruso.
    if not state.get("capture_pending"):
        state["intruder_notified"] = False
    state["capture_pending"] = True
    state["capture_ts"] = ts
    _write_state_raw(state)
    return state


def _consume_capture_with_result(result: dict) -> bool:
    """
    Guarda el resultado de /verify (sube result_seq) y decide capture_pending.

    Loop "intruso hasta propietario": SOLO una cara AUTORIZADA (match) consume la
    intrusión → capture_pending=False. Si NO hay match, se MANTIENE pending para
    que el ESP32 siga capturando y reanalizando hasta que aparezca el propietario.
    result_seq sube siempre para que el UNO Q detecte cada resultado como nuevo.
    Preserva armed/last_event_ts/capture_ts.

    Inputs:  result — dict { match, person, confidence, photo_id, ts }.
    Outputs: notify_intruder — True solo en la PRIMERA detección de intruso del
             episodio (rate-limit de alertas; evita spam de Telegram/FCM por frame).
    """
    state = _read_state_raw()
    is_match = bool(result.get("match"))
    armed = bool(state.get("armed"))
    # Loop "intruso hasta propietario" SOLO mientras el sistema esté ARMADO.
    # Si está DESARMADO (el usuario apagó la vigilancia), una captura tardía NO
    # debe re-activar el loop: capture_pending=False corta el re-disparo del ESP32.
    state["capture_pending"] = (not is_match) and armed
    state["result_seq"] = int(state.get("result_seq", 0)) + 1
    enriched = dict(result)
    enriched["seq"] = state["result_seq"]
    state["last_result"] = enriched
    notify_intruder = False
    if armed and not is_match and not state.get("intruder_notified"):
        state["intruder_notified"] = True
        notify_intruder = True
    _write_state_raw(state)
    return notify_intruder


# --------------------------------------------------------------------------- #
# Helpers de estado de dispositivos (heartbeats persistidos en JSON simple)
# --------------------------------------------------------------------------- #
def _load_device_status() -> dict:
    """
    Lee el estado de dispositivos desde DEVICE_STATUS_FILE.

    Outputs: dict { device_id: { "last_seen": str ISO8601, "camera_ok"?,
             "wifi_rssi"?, "fw"? } }. Si el archivo no existe, está corrupto o
             no contiene un objeto JSON, devuelve dict vacío (nunca lanza).
    """
    try:
        with open(config.DEVICE_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_device_status(status: dict) -> None:
    """
    Persiste el dict de estado de dispositivos en DEVICE_STATUS_FILE.

    Inputs:  status — dict completo { device_id: {...} } a escribir.
    Outputs: ninguno (efecto secundario: archivo JSON en disco; crea la carpeta
             padre si hiciera falta).
    """
    config.DEVICE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.DEVICE_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


async def _insert_event(
    ts: str, match: bool, person: str, confidence: float, photo_id: str, latency_ms: int
) -> None:
    """Inserta un evento en la tabla SQLite `events`."""
    async with aiosqlite.connect(config.EVENTS_DB) as db:
        await db.execute(
            "INSERT INTO events (ts, match, person, confidence, photo_id, latency_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, 1 if match else 0, person, confidence, photo_id, latency_ms),
        )
        await db.commit()


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/", tags=["meta"])
async def root() -> dict:
    """Endpoint raíz: health-check rápido con info básica del servidor."""
    return {
        "service": "EMBEBIDOS_1 Face Security Server",
        "version": "0.6.0",
        "phase": 6,
        "docs": "/docs",
    }


@app.post("/verify", tags=["recognition"])
async def verify(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Imagen JPEG capturada por el Arduino"),
) -> dict:
    """
    Recibe una foto, la guarda, la verifica (stub) y registra el evento.

    Flujo:
        1. Guarda la imagen en storage/photos/{ISO8601}_{person}.jpg.
           (Como el nombre se decide tras reconocer, se usa primero un nombre
            provisional con la marca de tiempo y luego se renombra con la persona.)
        2. Llama recognition.verify() (stub Fase 6).
        3. Persiste el evento en SQLite y actualiza last_event_ts.
        4. Dispara telegram_service.send_alert y fcm_service.notify en
           BackgroundTasks (no bloquean la respuesta).

    Inputs (multipart):
        file: UploadFile — el JPEG.
    Outputs (dict):
        { match, person, confidence, photo_id, latency_ms }
    """
    t0 = time.perf_counter()

    # Marca de tiempo segura para nombre de archivo (sin ':' por Windows).
    now = datetime.now(timezone.utc)
    ts_iso = now.isoformat()
    ts_fs = now.strftime("%Y%m%dT%H%M%S%fZ")  # compatible con Windows

    # 1) Guardado provisional en disco.
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    tmp_name = f"{ts_fs}_pending.jpg"
    tmp_path = config.PHOTOS_DIR / tmp_name
    with open(tmp_path, "wb") as f:
        f.write(raw)

    # 2) Reconocimiento REAL (Fase 7: DeepFace + ArcFace, similitud coseno).
    result = recognition.verify(str(tmp_path))
    match = bool(result.get("match", False))
    person = result.get("person", "unknown")
    confidence = float(result.get("confidence", 0.0))
    # Señal de caso edge "sin cara" (recognition.verify la incluye cuando no detecta
    # ninguna cara). Se propaga al cliente para cumplir el contrato del exit gate.
    error = result.get("error")

    # Renombrar con la persona resuelta → photo_id final.
    safe_person = "".join(c for c in person if c.isalnum() or c in ("-", "_")) or "unknown"
    photo_id = f"{ts_fs}_{safe_person}.jpg"
    final_path = config.PHOTOS_DIR / photo_id
    try:
        tmp_path.rename(final_path)
    except OSError:
        # Si el rename falla (p. ej. colisión), conservamos el provisional.
        photo_id = tmp_name
        final_path = tmp_path

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 3) Persistencia del evento + estado.
    await _insert_event(ts_iso, match, person, confidence, photo_id, latency_ms)
    _touch_last_event(ts_iso)

    # 3b) Coordinación sin cables (Parte 1, Ing3): guardar el resultado como
    #     last_result y apagar capture_pending (esta captura consumió la
    #     intrusión). result_seq sube para que el UNO Q lo vea como nuevo.
    #     NO altera el formato de la respuesta de /verify (solo estado interno).
    notify_intruder = _consume_capture_with_result(
        {
            "match": match,
            "person": person,
            "confidence": confidence,
            "photo_id": photo_id,
            "ts": ts_iso,
        }
    )

    # 4) Notificaciones en background (no bloquean la respuesta al Arduino).
    #    En el loop "intruso hasta propietario" el ESP32 hace muchas capturas
    #    seguidas; para no spamear, la alerta de intruso (no-match) se envía solo
    #    en la PRIMERA del episodio (notify_intruder). El acceso autorizado
    #    (match) siempre se notifica.
    if match or notify_intruder:
        background_tasks.add_task(
            telegram_service.send_alert, match, person, confidence, str(final_path)
        )
        background_tasks.add_task(fcm_service.notify, match, person, confidence, photo_id)

    response = {
        "match": match,
        "person": person,
        "confidence": confidence,
        "photo_id": photo_id,
        "latency_ms": latency_ms,
    }
    # Incluir "error" solo cuando aplique (p. ej. "no_face"), sin ensuciar el caso normal.
    if error:
        response["error"] = error
    return response


@app.post("/enroll", tags=["enrollment"])
async def enroll(
    name: str = Form(..., description="Nombre de la persona a enrolar"),
    file: UploadFile = File(..., description="Foto de la persona (JPEG)"),
) -> dict:
    """
    Enrola una persona a partir de una foto.

    Flujo:
        1. Guarda la foto en storage/photos/enroll_{ISO8601}_{name}.jpg.
        2. Delega en enrollment.enroll() (stub Fase 6).

    Inputs (form):
        name: str          — nombre/clave de la persona.
        file: UploadFile   — la foto.
    Outputs (dict):
        { enrolled, person, n_photos }
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    now = datetime.now(timezone.utc)
    ts_fs = now.strftime("%Y%m%dT%H%M%S%fZ")
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "person"
    photo_name = f"enroll_{ts_fs}_{safe_name}.jpg"
    photo_path = config.PHOTOS_DIR / photo_name
    with open(photo_path, "wb") as f:
        f.write(raw)

    result = await enrollment.enroll(name, [str(photo_path)])
    return result


@app.get("/enrolled", tags=["enrollment"])
async def list_enrolled() -> list[dict]:
    """
    Lista las personas enroladas.

    Outputs: lista de { name, n_embeddings, enrolled_at }.
    """
    return await enrollment.list_enrolled()


@app.delete("/enroll/{name}", tags=["enrollment"])
async def delete_enroll(name: str) -> dict:
    """
    Borra una persona enrolada.

    Inputs:  name — nombre de la persona (path param).
    Outputs: { deleted: bool }.
    """
    deleted = await enrollment.delete(name)
    return {"deleted": deleted}


@app.get("/events", tags=["events"])
async def list_events(page: int = 1, limit: int = 20) -> dict:
    """
    Devuelve el historial de eventos paginado (más recientes primero).

    Inputs (query):
        page:  número de página (1-based).
        limit: tamaño de página.
    Outputs (dict):
        { items: [...], total, page, limit }
        Cada item: { id, ts, match, person, confidence, photo_id, latency_ms }.
    """
    page = max(1, page)
    limit = max(1, min(limit, 200))  # cota defensiva
    offset = (page - 1) * limit

    async with aiosqlite.connect(config.EVENTS_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) AS c FROM events") as cur:
            row = await cur.fetchone()
            total = row["c"] if row else 0
        async with db.execute(
            "SELECT id, ts, match, person, confidence, photo_id, latency_ms "
            "FROM events ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()

    items = [
        {
            "id": r["id"],
            "ts": r["ts"],
            "match": bool(r["match"]),
            "person": r["person"],
            "confidence": r["confidence"],
            "photo_id": r["photo_id"],
            "latency_ms": r["latency_ms"],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}


@app.delete("/events", tags=["events"])
async def clear_events() -> dict:
    """
    Borra TODO el historial de eventos y las fotos asociadas a esos eventos.

    No toca a las personas enroladas ni sus fotos (esas usan otro prefijo y no
    están en la tabla de eventos). Operación idempotente.

    Outputs (dict): { cleared: true, deleted_events: int, deleted_photos: int }.
    """
    async with aiosqlite.connect(config.EVENTS_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT photo_id FROM events") as cur:
            rows = await cur.fetchall()
        async with db.execute("SELECT COUNT(*) AS c FROM events") as cur:
            crow = await cur.fetchone()
            total = crow["c"] if crow else 0
        await db.execute("DELETE FROM events")
        await db.commit()

    deleted_photos = 0
    for r in rows:
        pid = r["photo_id"]
        if not pid:
            continue
        photo = config.PHOTOS_DIR / pid
        try:
            if photo.is_file():
                photo.unlink()
                deleted_photos += 1
        except OSError:
            pass  # un archivo que no se pudo borrar no debe romper la operación

    logger.info("Historial de eventos borrado: %d eventos, %d fotos.",
                total, deleted_photos)
    return {"cleared": True, "deleted_events": total, "deleted_photos": deleted_photos}


@app.get("/photos/{photo_id}", tags=["events"])
async def get_photo(photo_id: str):
    """
    Devuelve la imagen JPEG de un evento/enrolamiento.

    Inputs:  photo_id — nombre de archivo (path param).
    Outputs: FileResponse image/jpeg, o 404 si no existe.

    Seguridad: se valida que el path resuelto quede dentro de PHOTOS_DIR para
    evitar path traversal (../).
    """
    # Resolución segura dentro de PHOTOS_DIR.
    candidate = (config.PHOTOS_DIR / photo_id).resolve()
    photos_root = config.PHOTOS_DIR.resolve()
    if photos_root not in candidate.parents and candidate != photos_root:
        raise HTTPException(status_code=400, detail="photo_id inválido")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return FileResponse(str(candidate), media_type="image/jpeg")


@app.post("/arm", tags=["control"])
async def arm(body: ArmBody) -> dict:
    """
    Arma o desarma el sistema según el flag recibido.

    Inputs (JSON):  { armed: bool }.
    Outputs (dict): { armed: bool } (estado resultante).
    """
    state = _set_armed(body.armed)
    return {"armed": state["armed"]}


@app.post("/disarm", tags=["control"])
async def disarm() -> dict:
    """
    Atajo para desarmar el sistema (equivalente a POST /arm {armed:false}).

    Outputs (dict): { armed: false }.
    """
    state = _set_armed(False)
    return {"armed": state["armed"]}


@app.get("/state", tags=["control"])
async def get_state() -> dict:
    """
    Devuelve el estado del sistema.

    Outputs (dict): { armed: bool, last_event_ts: str|None }.
    Consumido por el Arduino (polling cada 5 s) y por la app.
    """
    return _read_state()


# --------------------------------------------------------------------------- #
# Coordinación "sin cables" UNO Q ↔ ESP32-CAM (Parte 1, Ing3)
#   Flujo:
#     1. UNO Q detecta intrusión (láser cortado) → POST /intrusion (capture_pending=True).
#     2. ESP32-CAM sondea GET /capture-request (~1.5 s); si pending → captura y POST /verify.
#     3. POST /verify guarda last_result y apaga capture_pending (ver handler /verify).
#     4. UNO Q sondea GET /last-result (cada pocos s) y acciona LEDs según el seq nuevo.
# --------------------------------------------------------------------------- #
@app.post("/intrusion", tags=["coordination"])
async def intrusion() -> dict:
    """
    Marca una intrusión pendiente de captura (lo llama el UNO Q al cortarse el láser).

    Pone capture_pending=True con capture_ts = ahora (ISO8601 UTC). Es idempotente:
    varias llamadas seguidas solo refrescan capture_ts (no acumulan estado).

    Inputs:  ninguno (sin body).
    Outputs (dict): { ok: true, ts } donde ts es la marca de la intrusión.
    """
    ts = datetime.now(timezone.utc).isoformat()
    _set_capture_pending(ts)
    return {"ok": True, "ts": ts}


@app.get("/capture-request", tags=["coordination"])
async def capture_request() -> dict:
    """
    Indica al ESP32-CAM si hay una captura pendiente (polling cada ~1.5 s).

    Lectura simple del estado. Endpoint LIBRE (sin API key) por sondearse muy
    seguido, igual que GET /state.

    Outputs (dict): { pending: bool, ts: str|None }
        pending — True si hay una intrusión esperando captura.
        ts      — capture_ts de esa intrusión (None si no hay pendiente).
    """
    state = _read_state_raw()
    return {"pending": state["capture_pending"], "ts": state["capture_ts"]}


@app.get("/last-result", tags=["coordination"])
async def last_result() -> dict:
    """
    Devuelve el último resultado de reconocimiento (lo sondea el UNO Q).

    El resultado incluye un `seq` incremental para que el UNO Q distinga un
    resultado nuevo de uno ya procesado (acciona LEDs solo ante un seq mayor).

    Outputs (dict):
        - { none: true } si aún no hay ningún resultado.
        - { match, person, confidence, photo_id, ts, seq } con el último resultado.
    """
    state = _read_state_raw()
    result = state.get("last_result")
    if not result:
        return {"none": True}
    return result


@app.post("/telegram/test", tags=["coordination"])
async def telegram_test() -> dict:
    """
    Envía un mensaje de prueba por Telegram con el token/chat_id actuales (para la GUI).

    Reusa TelegramService.send_alert (sin foto → fallback a sendMessage de texto).
    Si faltan credenciales en .env/config, responde { ok:false, detail } sin romper.

    Inputs:  ninguno (usa config.TELEGRAM_TOKEN / TELEGRAM_CHAT_ID).
    Outputs (dict): { ok: bool, detail: str }.
    """
    if not telegram_service.token or not telegram_service.chat_id:
        return {
            "ok": False,
            "detail": "Telegram no configurado: falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en .env",
        }
    try:
        # match=True / confianza dummy → mensaje de prueba reconocible; sin foto.
        ok = await telegram_service.send_alert(
            True, "PRUEBA (Telegram test)", 1.0, ""
        )
    except Exception as exc:  # noqa: BLE001 — el endpoint nunca debe romper
        return {"ok": False, "detail": f"Error enviando a Telegram: {type(exc).__name__}: {exc}"}
    if ok:
        return {"ok": True, "detail": "Mensaje de prueba enviado a Telegram"}
    return {"ok": False, "detail": "Telegram no aceptó el mensaje (ver logs del servidor)"}


@app.post("/fcm/register", tags=["fcm"])
async def fcm_register(body: FcmRegisterBody) -> dict:
    """
    Registra un token FCM de la app para push notifications.

    Inputs (JSON):  { token: str }.
    Outputs (dict): { registered: bool }.
    """
    registered = fcm_service.register_token(body.token)
    if not registered:
        raise HTTPException(status_code=400, detail="Token inválido")
    return {"registered": registered}


@app.post("/device/heartbeat", tags=["device"])
async def device_heartbeat(body: HeartbeatBody) -> dict:
    """
    Registra el latido de un dispositivo físico (ESP32-CAM o UNO Q).

    Guarda/actualiza en DEVICE_STATUS_FILE la entrada del device con los campos
    opcionales que reporte (camera_ok, wifi_rssi, fw) + `last_seen` en ISO8601
    UTC del momento de recepción. Los campos opcionales NO reportados en este
    latido no se conservan de latidos anteriores: cada heartbeat reemplaza la
    entrada completa del device (estado fresco, sin datos rancios).

    Inputs (JSON):  { device_id: str, camera_ok?: bool, wifi_rssi?: int, fw?: str }.
    Outputs (dict): { ok: true, device_id }.
    Errores: 422 si falta device_id (Pydantic); 400 si viene vacío/en blanco.
    """
    device_id = body.device_id.strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id no puede estar vacío")

    entry: dict = {"last_seen": datetime.now(timezone.utc).isoformat()}
    if body.camera_ok is not None:
        entry["camera_ok"] = body.camera_ok
    if body.wifi_rssi is not None:
        entry["wifi_rssi"] = body.wifi_rssi
    if body.fw is not None:
        entry["fw"] = body.fw

    status = _load_device_status()
    status[device_id] = entry
    _save_device_status(status)
    return {"ok": True, "device_id": device_id}


@app.get("/device/status", tags=["device"])
async def device_status() -> dict:
    """
    Devuelve el estado online/offline de los dispositivos que reportan heartbeat.

    Un device está `online` si su `last_seen` es más reciente que
    config.DEVICE_OFFLINE_AFTER_S segundos respecto a ahora (UTC). Entradas con
    `last_seen` ausente o no parseable se reportan offline (defensivo). Si nunca
    hubo heartbeats (archivo inexistente), devuelve { devices: {} }.

    Outputs (dict):
        { devices: { <device_id>: { online: bool, last_seen: str|None,
                                    camera_ok?, wifi_rssi?, fw? } } }
    Consumido por la app Kotlin (pantalla de estado del sistema).
    """
    now = datetime.now(timezone.utc)
    devices: dict = {}
    for device_id, entry in _load_device_status().items():
        if not isinstance(entry, dict):
            continue  # entrada corrupta: se ignora sin romper la respuesta
        last_seen = entry.get("last_seen")
        online = False
        if isinstance(last_seen, str):
            try:
                seen_dt = datetime.fromisoformat(last_seen)
                if seen_dt.tzinfo is None:
                    seen_dt = seen_dt.replace(tzinfo=timezone.utc)
                online = (now - seen_dt).total_seconds() < config.DEVICE_OFFLINE_AFTER_S
            except ValueError:
                online = False  # timestamp ilegible → offline
        info = {"online": online, "last_seen": last_seen}
        # Propagar solo los campos opcionales presentes en el último heartbeat.
        for key in ("camera_ok", "wifi_rssi", "fw"):
            if key in entry:
                info[key] = entry[key]
        devices[device_id] = info
    return {"devices": devices}


# --------------------------------------------------------------------------- #
# Manejo uniforme de errores HTTP (JSON consistente).
# --------------------------------------------------------------------------- #
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Devuelve los HTTPException como JSON { error, detail } uniforme."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "detail": exc.detail},
    )


# --------------------------------------------------------------------------- #
# Arranque directo: `python main.py` (equivalente a uvicorn main:app).
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )

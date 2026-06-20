# ============================================================================
#  cloud_bridge.py  -  EMBEBIDOS_1 / Fase 5 (v3)  -  Bridge UNO Q <-> servidor
#  Ing 2 (firmware embedded)
# ----------------------------------------------------------------------------
#  Corre como hilo demonio dentro de la app de App Lab (lado Linux). Modelo
#  DEFINITIVO: SIN cables a la ESP32; la coordinacion con el servidor de
#  reconocimiento se hace AQUI. Tareas:
#
#    1) EVENTO MCU -> servidor:  cuando el MCU confirma una intrusion emite la
#       linea 'EVT:INTRUSION'. La leemos (ver "ENTRADA MCU -> python" abajo) y
#       hacemos POST {SERVER_HOST}/intrusion.
#    2) RESULTADO servidor -> MCU:  poll GET {SERVER_HOST}/last-result cada
#       RESULT_POLL_S (2 s). Cuando llega un 'seq' mayor al ultimo visto,
#       enviamos al MCU 'RES:MATCH' (match=true) o 'RES:INTRUDER' (match=false).
#    3) SYNC app -> MCU:  poll GET {SERVER_HOST}/state cada POLL_S (5 s); si
#       'armed' cambio, reenvia ARM o DISARM al MCU.
#    4) HEARTBEAT:  POST {SERVER_HOST}/device/heartbeat cada HB_S (15 s) con
#       {"device_id":"unoq","fw":FW} y header X-API-Key (si esta configurada).
#
#  CONFIG: /app/cloud.json (copiar cloud.json.example):
#      { "SERVER_HOST": "http://192.168.100.23:8000", "API_KEY": "",
#        "POLL_S": 5, "RESULT_POLL_S": 2, "HB_S": 15 }
#  Si cloud.json no existe o SERVER_HOST es placeholder, el bridge queda en
#  espera (reintenta leer la config cada 30 s) sin romper el portal WiFi.
#  En modo dev (API_KEY vacio) NO se manda el header X-API-Key.
#
#  ENVIO python -> MCU (dos vias, en orden):
#    a) RPC del RouterBridge: el sketch registra Bridge.provide("arm"/"disarm"/
#       "res_match"/"res_intruder"). Del lado python, arduino.app_utils expone
#       Bridge; se intenta Bridge.call(...) y variantes.
#    b) FALLBACK (patron archivo+watcher de F4): escribe /app/mcu_request.json
#       y host/fs_mcu_watch.sh (en el host) reenvia la linea al Monitor del MCU.
#
#  ENTRADA MCU -> python ('EVT:INTRUSION'), dos vias (cualquiera que aparezca):
#    a) RPC del RouterBridge: si el runtime expone Bridge.provide/subscribe del
#       lado python, registramos un handler 'intrusion' (forward-compatible).
#    b) FALLBACK (patron archivo+watcher, simetrico a fs_mcu_watch.sh):
#       host/fs_mcu_event_watch.sh tail-ea el Monitor del MCU y, al ver
#       'EVT:INTRUSION', escribe /app/mcu_event.json; este modulo lo lee.
#
#  Solo usa stdlib (urllib) para HTTP: sin dependencias extra en el contenedor.
# ============================================================================
import json
import os
import ssl
import threading
import time
import urllib.request

FW_VERSION = "5.1.0-f5"
DEVICE_ID = "unoq"

# Fail-safe: polls /last-result fallidos consecutivos para declarar el servidor
# "caido" (Desmontado) y apagar el MCU. 3 x RESULT_POLL_S(2s) ~= 6 s.
SERVER_FAIL_THRESHOLD = 3

_PLACEHOLDERS = {"", "REEMPLAZAR", "tu-dominio.duckdns.org", "<SERVER_HOST>"}

_app_dir = "/app"
_log_prefix = "[cloud_bridge]"


def _log(msg: str) -> None:
    print(f"{_log_prefix} {msg}", flush=True)


# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------
def _load_config() -> dict | None:
    """Lee /app/cloud.json. None si falta o esta con placeholders."""
    path = os.path.join(_app_dir, "cloud.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    host = str(cfg.get("SERVER_HOST", "")).strip()
    if host in _PLACEHOLDERS:
        return None
    cfg["SERVER_HOST"] = host
    cfg.setdefault("API_KEY", "")
    # Tiempos de respuesta: result_poll bajo = el LED reacciona casi al instante;
    # state_poll medio = arm/disarm se reflejan rapido sin saturar.
    cfg.setdefault("POLL_S", 3)
    cfg.setdefault("RESULT_POLL_S", 0.8)
    cfg.setdefault("HB_S", 15)
    return cfg


# ---------------------------------------------------------------------------
#  HTTP (stdlib). HTTPS con CA del sistema; http:// permitido para pruebas LAN.
# ---------------------------------------------------------------------------
def _request(url: str, method: str = "GET", payload: dict | None = None,
             api_key: str = "", timeout: float = 6.0) -> dict | None:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:                       # modo dev (vacio) -> NO manda el header
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context() if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except Exception as exc:  # red caida, DNS, 4xx/5xx, JSON invalido...
        _log(f"{method} {url} fallo: {exc!r}")
        return None


# ---------------------------------------------------------------------------
#  Envio python -> MCU
# ---------------------------------------------------------------------------
_bridge_obj = None
_bridge_checked = False


def _get_bridge():
    """Intenta obtener el objeto Bridge (RPC) de arduino.app_utils, una vez."""
    global _bridge_obj, _bridge_checked
    if _bridge_checked:
        return _bridge_obj
    _bridge_checked = True
    try:
        import arduino.app_utils as app_utils
        _bridge_obj = getattr(app_utils, "Bridge", None)
        if _bridge_obj is None:
            _log("arduino.app_utils no expone 'Bridge': se usara el fallback archivo")
        else:
            _log(f"Bridge RPC disponible: {type(_bridge_obj)!r}")
    except Exception as exc:
        _log(f"import arduino.app_utils fallo ({exc!r}): fallback archivo")
        _bridge_obj = None
    return _bridge_obj


# Mapa comando logico -> nombre RPC registrado por el sketch (Bridge.provide).
_RPC_NAME = {
    "ARM": "arm",
    "DISARM": "disarm",
    "RES:MATCH": "res_match",
    "RES:INTRUDER": "res_intruder",
}


def _send_via_bridge(command: str) -> bool:
    """Via (a): RPC. El sketch registro Bridge.provide('arm'/'disarm'/'res_*')."""
    bridge = _get_bridge()
    if bridge is None:
        return False
    rpc_name = _RPC_NAME.get(command)
    if rpc_name is None:
        return False
    for meth in ("call", "call_no_result", "notify"):
        fn = getattr(bridge, meth, None)
        if not callable(fn):
            continue
        try:
            fn(rpc_name)
            _log(f"MCU <- {command} via Bridge.{meth}('{rpc_name}') OK")
            return True
        except Exception as exc:
            _log(f"Bridge.{meth}('{rpc_name}') fallo: {exc!r}")
    return False


def _send_via_file(command: str) -> bool:
    """Via (b): patron archivo+watcher de F4 (host/fs_mcu_watch.sh).

    El watcher reenvia el campo 'cmd' tal cual al Monitor del MCU; el parser
    serial del sketch entiende ARM/DISARM/RES:MATCH/RES:INTRUDER.
    """
    path = os.path.join(_app_dir, "mcu_request.json")
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"cmd": command, "ts": int(time.time())}, fh)
        os.replace(tmp, path)
        _log(f"MCU <- {command} via mcu_request.json (watcher del host)")
        return True
    except OSError as exc:
        _log(f"no se pudo escribir mcu_request.json: {exc!r}")
        return False


def send_mcu(command: str) -> bool:
    """Envia ARM/DISARM/RES:MATCH/RES:INTRUDER al MCU. RPC primero; archivo fallback."""
    if _send_via_bridge(command):
        return True
    return _send_via_file(command)


# ---------------------------------------------------------------------------
#  Entrada MCU -> python:  'EVT:INTRUSION'
# ---------------------------------------------------------------------------
#  Via fallback (simetrica a fs_mcu_watch.sh): host/fs_mcu_event_watch.sh
#  tail-ea el Monitor del MCU y escribe mcu_event.json con {"evt","seq","ts"}.
#  Aqui leemos ese archivo y disparamos a lo sumo una vez por 'seq'.
_last_event_seq = -1


def _poll_mcu_event() -> str | None:
    """Devuelve el nombre del evento nuevo del MCU (p.ej. 'INTRUSION') o None."""
    global _last_event_seq
    path = os.path.join(_app_dir, "mcu_event.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            ev = json.load(fh)
    except (OSError, ValueError):
        return None
    seq = int(ev.get("seq", 0))
    if seq <= _last_event_seq:
        return None
    _last_event_seq = seq
    return str(ev.get("evt", "")).strip().upper()


# ---------------------------------------------------------------------------
#  Entrada MCU -> python via RPC (PRIMARIA):  Bridge.notify("intrusion")
# ---------------------------------------------------------------------------
#  El sketch hace Bridge.notify("intrusion") al confirmar el corte del haz.
#  Aqui registramos el handler con Bridge.provide("intrusion", _on_intrusion)
#  (mismo patron oficial que home-climate-monitoring). El handler solo levanta
#  un Event; el POST /intrusion lo hace el bucle (que ya tiene la cfg cargada),
#  para no tocar HTTP/SSL dentro del callback RPC. Esto NO depende de scripts
#  host (App Lab no los arranca); el archivo mcu_event.json queda como fallback.
_intrusion_event = threading.Event()


def _on_intrusion(*_args, **_kwargs) -> None:
    """Callback RPC invocado por el MCU (Bridge.notify('intrusion'))."""
    _log("MCU -> intrusion (RPC)")
    _intrusion_event.set()


def _register_intrusion_rpc() -> bool:
    """Registra Bridge.provide('intrusion', _on_intrusion). Una vez, en start()."""
    bridge = _get_bridge()
    if bridge is None:
        _log("Bridge no disponible: la intrusion usara el fallback de archivo "
             "(mcu_event.json + watcher host)")
        return False
    fn = getattr(bridge, "provide", None)
    if not callable(fn):
        _log("Bridge sin metodo 'provide': intrusion por fallback de archivo")
        return False
    try:
        fn("intrusion", _on_intrusion)
        _log("Bridge.provide('intrusion') registrado (MCU -> python por RPC)")
        return True
    except Exception as exc:
        _log(f"Bridge.provide('intrusion') fallo: {exc!r}")
        return False


# ---------------------------------------------------------------------------
#  Bucle principal del bridge
# ---------------------------------------------------------------------------
def _loop() -> None:
    cfg = None
    last_sent_armed = None      # ultimo 'armed' reenviado al MCU (None = nunca)
    last_result_seq = None      # ultimo 'seq' de /last-result reenviado al MCU
    server_fail = 0             # polls /last-result fallidos consecutivos
    forced_off = False          # True tras apagar el MCU por servidor caido
    next_poll = 0.0
    next_result_poll = 0.0
    next_hb = 0.0

    while True:
        now = time.monotonic()

        if cfg is None:
            cfg = _load_config()
            if cfg is None:
                _log("cloud.json ausente o con placeholder; reintento en 30 s "
                     "(el portal WiFi sigue operativo)")
                time.sleep(30)
                continue
            _log(f"config OK: SERVER_HOST={cfg['SERVER_HOST']} "
                 f"poll={cfg['POLL_S']}s result_poll={cfg['RESULT_POLL_S']}s "
                 f"hb={cfg['HB_S']}s api_key={'SI' if cfg['API_KEY'] else 'NO'}")
            base = cfg["SERVER_HOST"]
            if not base.startswith("http"):
                base = "http://" + base   # LAN dev por defecto (sin TLS)
            cfg["_BASE"] = base.rstrip("/")

        # --- 0) Intrusion del MCU -> POST /intrusion ------------------------
        #   Via PRIMARIA: RPC (Bridge.notify('intrusion') -> _intrusion_event).
        #   Via FALLBACK: archivo mcu_event.json (watcher host, si se usa).
        intrusion = False
        if _intrusion_event.is_set():
            _intrusion_event.clear()
            _log("intrusion (RPC) -> POST /intrusion")
            intrusion = True
        elif _poll_mcu_event() == "INTRUSION":
            _log("EVT:INTRUSION (archivo) -> POST /intrusion")
            intrusion = True
        if intrusion:
            _request(cfg["_BASE"] + "/intrusion", method="POST",
                     payload={"device_id": DEVICE_ID, "ts": int(time.time())},
                     api_key=cfg["API_KEY"])

        # --- 1) Resultado del servidor + FAIL-SAFE "servidor caido = OFF" ----
        #   El poll de /last-result (frecuente, 2 s) hace de detector de salud.
        #   Si el servidor NO responde varios ciclos, se considera "Desmontado"
        #   y se apaga el MCU (DISARM) SIN tocar el 'armed' del servidor; al
        #   volver el servidor, /state re-sincroniza y re-arma (retoma armado).
        if now >= next_result_poll:
            next_result_poll = now + float(cfg["RESULT_POLL_S"])
            # timeout corto: este poll hace de detector de salud; con timeout
            # largo, declarar "servidor caido" tardaria demasiado.
            res = _request(cfg["_BASE"] + "/last-result", timeout=2.5)
            if res is None:
                server_fail += 1
                if server_fail >= SERVER_FAIL_THRESHOLD and not forced_off:
                    _log(f"servidor no responde ({server_fail} intentos) -> "
                         "apagando UNO Q (DISARM); el 'armed' se conserva")
                    send_mcu("DISARM")
                    forced_off = True
                    last_sent_armed = None     # forzar resync de ARM/DISARM al volver
                    last_result_seq = None     # y re-aceptar resultados nuevos
            else:
                if forced_off:
                    _log("servidor de vuelta -> resync (re-arma segun /state)")
                    forced_off = False
                server_fail = 0
                if "seq" in res:
                    seq = res.get("seq")
                    if seq != last_result_seq:
                        cmd = "RES:MATCH" if bool(res.get("match")) else "RES:INTRUDER"
                        _log(f"/last-result seq={seq} match={res.get('match')} -> {cmd}")
                        if send_mcu(cmd):
                            last_result_seq = seq
                        # si fallo, se reintenta (last_result_seq no avanza)

        # --- 2) Sync app: GET /state -> ARM/DISARM si cambio ----------------
        if now >= next_poll:
            next_poll = now + float(cfg["POLL_S"])
            state = _request(cfg["_BASE"] + "/state")
            if state is not None and "armed" in state:
                armed = bool(state["armed"])
                if armed != last_sent_armed:
                    cmd = "ARM" if armed else "DISARM"
                    _log(f"/state armed={armed} (antes={last_sent_armed}) -> {cmd}")
                    if send_mcu(cmd):
                        last_sent_armed = armed

        # --- 3) Heartbeat ----------------------------------------------------
        if now >= next_hb:
            next_hb = now + float(cfg["HB_S"])
            _request(cfg["_BASE"] + "/device/heartbeat", method="POST",
                     payload={"device_id": DEVICE_ID, "fw": FW_VERSION},
                     api_key=cfg["API_KEY"])

        time.sleep(0.5)


def start(app_dir: str = "/app") -> threading.Thread:
    """Lanza el bridge como hilo demonio. Lo llama python/main.py."""
    global _app_dir
    _app_dir = app_dir
    # Registrar la via PRIMARIA de intrusion (RPC) antes de arrancar el bucle.
    # Debe hacerse en el hilo principal, antes de App.run() (patron de ejemplos).
    _register_intrusion_rpc()
    th = threading.Thread(target=_loop, name="cloud_bridge", daemon=True)
    th.start()
    _log(f"hilo iniciado (app_dir={app_dir})")
    return th

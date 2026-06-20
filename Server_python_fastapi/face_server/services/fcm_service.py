"""
services/fcm_service.py — Push notifications a la app Kotlin vía FCM (FASE 9 — REAL).

Implementación real con firebase-admin:
    - Inicializa firebase-admin UNA sola vez (singleton de módulo) con el
      serviceAccountKey (config.FCM_CREDENTIALS_PATH). Si el archivo no existe,
      loguea un warning y degrada a no-op (NO rompe el servidor).
    - `notify()` construye un mensaje (notification + data) y lo envía a TODOS los
      tokens registrados en storage/fcm_tokens.json (messaging.send por token).
      Limpia tokens inválidos (UNREGISTERED / INVALID_ARGUMENT) del store.
    - `register_token()` / `list_tokens()` persisten los tokens en el JSON.

Seguridad: el serviceAccountKey vive SOLO en secrets/. Nunca se loguea su
contenido; como mucho se loguea el project_id (no es secreto).

Robustez: cualquier fallo de FCM NO debe romper /verify (notify corre en
BackgroundTasks). Por eso todo el envío está envuelto en try/except.
"""

import json
import logging
import os
from datetime import datetime, timezone

import config

logger = logging.getLogger("fcm")

# Errores de firebase-admin que indican que un token ya no sirve y debe limpiarse.
_INVALID_TOKEN_ERRORS = ("UNREGISTERED", "INVALID_ARGUMENT", "SENDER_ID_MISMATCH")

# --------------------------------------------------------------------------- #
# Inicialización singleton de firebase-admin (a nivel de módulo).
# --------------------------------------------------------------------------- #
_firebase_ready: bool = False
_firebase_project_id: str | None = None

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    _FIREBASE_IMPORTED = True
except ImportError:  # pragma: no cover - firebase-admin no instalado
    firebase_admin = None  # type: ignore
    credentials = None  # type: ignore
    messaging = None  # type: ignore
    _FIREBASE_IMPORTED = False


def _init_firebase() -> None:
    """
    Inicializa la app de firebase-admin una sola vez (idempotente).

    Si el serviceAccountKey no existe o firebase-admin no está instalado, deja
    el servicio en modo no-op (loguea warning) sin lanzar excepción.
    """
    global _firebase_ready, _firebase_project_id

    if _firebase_ready:
        return

    if not _FIREBASE_IMPORTED:
        logger.warning("[fcm] firebase-admin no instalado → notify() en modo no-op.")
        return

    cred_path = config.FCM_CREDENTIALS_PATH
    if not cred_path or not os.path.isfile(cred_path):
        logger.warning(
            "[fcm] serviceAccountKey no encontrado en la ruta configurada "
            "→ notify() en modo no-op."
        )
        return

    try:
        # Reutiliza la default app si ya existe (p. ej. otro import la creó).
        try:
            app = firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate(cred_path)
            app = firebase_admin.initialize_app(cred)
        _firebase_project_id = app.project_id
        _firebase_ready = True
        logger.info(
            "[fcm] firebase-admin inicializado (project_id=%s).", _firebase_project_id
        )
    except Exception as exc:  # noqa: BLE001 - degradar sin romper el server
        logger.warning("[fcm] No se pudo inicializar firebase-admin (%s) → no-op.", exc)


# Intento de init al importar el módulo (no rompe si falla).
_init_firebase()


class FCMService:
    """Servicio de notificaciones push real (firebase-admin + persistencia de tokens)."""

    def __init__(self) -> None:
        """Carga la ruta de credenciales y asegura el archivo de tokens."""
        self.credentials_path: str = config.FCM_CREDENTIALS_PATH
        self.tokens_file = config.FCM_TOKENS_FILE
        self._ensure_store()
        # Asegura init (por si el import-time falló y luego se colocó la credencial).
        _init_firebase()

    # ------------------------------------------------------------------ #
    # Persistencia de tokens
    # ------------------------------------------------------------------ #
    def _ensure_store(self) -> None:
        """Crea el JSON de tokens (lista vacía) si no existe."""
        self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.tokens_file.exists():
            self._write_tokens([])

    def _read_tokens(self) -> list[str]:
        """Lee la lista de tokens FCM registrados. Devuelve [] si está corrupto."""
        try:
            with open(self.tokens_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_tokens(self, tokens: list[str]) -> None:
        """Escribe la lista de tokens FCM."""
        self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tokens_file, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)

    def register_token(self, token: str) -> bool:
        """
        Registra un token FCM de la app (idempotente, sin duplicados).

        Inputs:  token — el registration token que envía la app Kotlin.
        Outputs: True si quedó registrado (nuevo o ya existente y válido),
                 False si el token es vacío/inválido.
        """
        if not token or not token.strip():
            return False
        tokens = self._read_tokens()
        if token not in tokens:
            tokens.append(token)
            self._write_tokens(tokens)
        return True

    def list_tokens(self) -> list[str]:
        """Devuelve la lista de tokens FCM registrados."""
        return self._read_tokens()

    def _remove_tokens(self, bad_tokens: set[str]) -> None:
        """Elimina del store los tokens inválidos detectados durante el envío."""
        if not bad_tokens:
            return
        remaining = [t for t in self._read_tokens() if t not in bad_tokens]
        self._write_tokens(remaining)

    # ------------------------------------------------------------------ #
    # Envío de notificaciones
    # ------------------------------------------------------------------ #
    async def notify(
        self,
        match: bool,
        person: str,
        confidence: float,
        photo_id: str,
    ) -> bool:
        """
        Envía un push a todos los tokens registrados vía firebase-admin (FASE 9).

        Inputs:
            match:      True acceso autorizado / False intruso.
            person:     nombre reconocido o "unknown".
            confidence: confianza [0..1].
            photo_id:   id (nombre de archivo) de la foto del evento.
        Outputs:
            bool — True si se intentó el envío a >=1 token sin excepción global;
                   False si está en modo no-op o si todo el envío falló.

        Garantía: cualquier excepción se captura y se loguea; NUNCA propaga
        (notify corre en BackgroundTasks y no debe tumbar /verify).
        """
        ts = datetime.now(timezone.utc).isoformat()
        conf_pct = f"{confidence * 100:.1f}%"

        # Construcción de title/body según resultado.
        if match:
            title = "🟢 Acceso autorizado: " + (person or "desconocido")
            body = f"Persona reconocida con confianza {conf_pct}."
        else:
            title = "🔴 Intruso detectado"
            body = f"Persona no reconocida (confianza {conf_pct})."

        if not _firebase_ready:
            logger.warning(
                "[fcm] no-op (firebase no inicializado) | %s | %s | %s | photo_id=%s",
                ts, title, body, photo_id,
            )
            return False

        tokens = self._read_tokens()
        if not tokens:
            logger.info("[fcm] Sin tokens registrados; nada que enviar.")
            return False

        # Payload data: todos los valores DEBEN ser string (contrato FCM).
        data = {
            "photo_id": str(photo_id),
            "person": str(person),
            "confidence": str(confidence),
            "match": "true" if match else "false",
            "type": "verify_event",
        }
        notification = messaging.Notification(title=title, body=body)

        ok = 0
        failed = 0
        bad_tokens: set[str] = set()

        for token in tokens:
            try:
                message = messaging.Message(
                    notification=notification,
                    data=data,
                    token=token,
                )
                messaging.send(message)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                # Detectar tokens inválidos para limpiarlos. firebase-admin lanza
                # subclases de FirebaseError; usamos el nombre del error/exc.
                err_code = getattr(exc, "code", "") or ""
                exc_name = type(exc).__name__
                marker = f"{err_code} {exc_name}".upper()
                if any(e in marker for e in _INVALID_TOKEN_ERRORS):
                    bad_tokens.add(token)
                # No logueamos el token completo (puede considerarse sensible).
                logger.warning("[fcm] envío fallido (%s).", exc_name)

        self._remove_tokens(bad_tokens)

        logger.info(
            "[fcm] %s | %s | %s | photo_id=%s → OK=%d FALLA=%d (limpiados=%d)",
            ts, title, body, photo_id, ok, failed, len(bad_tokens),
        )
        return ok > 0

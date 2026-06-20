"""
services/telegram_service.py — Notificaciones Telegram (FASE 8 — REAL).

Implementación real con `httpx` async contra la Bot API de Telegram:
    - `sendPhoto` (foto del evento + caption) cuando hay foto válida.
    - `sendMessage` (solo texto) como fallback si no hay foto.
    - Mensajes distintos según `match` (intruso vs autorizado).
    - Timeout 3 s, 1 reintento si falla.
    - TOKEN y CHAT_ID desde config (.env), NUNCA hardcodeados ni logueados.

Se ejecuta dentro de un `BackgroundTask` de FastAPI, de modo que NUNCA bloquee
la respuesta HTTP al Arduino. Cualquier fallo se loguea y retorna False sin
propagar excepciones.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

import config

logger = logging.getLogger("telegram")

# El logger interno de httpx loguea la URL completa en nivel INFO, lo que
# expondría el token (va embebido en la URL de la Bot API). Lo silenciamos a
# WARNING para que el token NUNCA aparezca en los logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

_API_BASE = "https://api.telegram.org"
_TIMEOUT_S = 3.0
_MAX_ATTEMPTS = 2  # 1 envío + 1 reintento


class TelegramService:
    """Servicio de alertas por Telegram (Fase 8, implementación real)."""

    def __init__(self) -> None:
        """Carga TOKEN/CHAT_ID desde config (.env). Nunca se loguean."""
        self.token: str = config.TELEGRAM_TOKEN
        self.chat_id: str = config.TELEGRAM_CHAT_ID

    def _build_caption(self, match: bool, person: str, confidence: float) -> str:
        """Construye el caption/texto de la alerta según el formato del exit gate."""
        ts = datetime.now(timezone.utc).isoformat()
        pct = confidence * 100
        if match:
            return (
                f"🟢 ACCESO AUTORIZADO — {ts}\n"
                f"Persona: {person}\n"
                f"Confianza: {pct:.1f}%"
            )
        return (
            f"🔴 INTRUSO DETECTADO — {ts}\n"
            f"Persona: Desconocido\n"
            f"Confianza: {pct:.1f}%"
        )

    async def _post_with_retry(self, method: str, **kwargs) -> bool:
        """
        Hace POST a `https://api.telegram.org/bot<token>/<method>` con
        timeout 3 s y 1 reintento. Devuelve True si la API responde ok:true.

        El token va en la URL pero NUNCA se loguea (solo se loguea el método).
        """
        url = f"{_API_BASE}/bot{self.token}/{method}"
        last_err = ""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                    resp = await client.post(url, **kwargs)
                data = resp.json()
                if resp.status_code == 200 and data.get("ok") is True:
                    logger.info(
                        "telegram %s OK (intento %d/%d)", method, attempt, _MAX_ATTEMPTS
                    )
                    return True
                # Respuesta no-ok: no exponer token; sí el motivo de Telegram.
                last_err = f"status={resp.status_code} desc={data.get('description')}"
            except Exception as exc:  # timeout, red, etc.
                last_err = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "telegram %s falló (intento %d/%d): %s",
                method,
                attempt,
                _MAX_ATTEMPTS,
                last_err,
            )
        logger.error("telegram %s falló tras %d intentos", method, _MAX_ATTEMPTS)
        return False

    async def send_alert(
        self,
        match: bool,
        person: str,
        confidence: float,
        photo_path: str,
    ) -> bool:
        """
        Envía una alerta con foto al chat de Telegram configurado.

        Inputs:
            match:      True si fue acceso autorizado, False si intruso.
            person:     nombre reconocido o "unknown"/"Desconocido".
            confidence: confianza [0..1].
            photo_path: ruta a la foto del evento (si no es válida, fallback texto).
        Outputs:
            bool — True si Telegram respondió ok:true, False en cualquier fallo.
        """
        if not self.token or not self.chat_id:
            logger.warning(
                "telegram no configurado (falta token o chat_id en .env) — "
                "alerta no enviada"
            )
            return False

        caption = self._build_caption(match, person, confidence)

        # Caso con foto válida → sendPhoto.
        if photo_path and os.path.isfile(photo_path):
            try:
                with open(photo_path, "rb") as fh:
                    photo_bytes = fh.read()
            except OSError as exc:
                logger.warning("no se pudo leer la foto (%s) — fallback a texto", exc)
                photo_bytes = None
            if photo_bytes:
                files = {"photo": ("event.jpg", photo_bytes, "image/jpeg")}
                payload = {"chat_id": self.chat_id, "caption": caption}
                return await self._post_with_retry(
                    "sendPhoto", data=payload, files=files
                )

        # Fallback: solo texto → sendMessage.
        logger.info("telegram: sin foto válida, enviando solo texto")
        payload = {"chat_id": self.chat_id, "text": caption}
        return await self._post_with_retry("sendMessage", data=payload)

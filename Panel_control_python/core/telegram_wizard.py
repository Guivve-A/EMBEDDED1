"""
core/telegram_wizard.py — Asistente de configuración de Telegram para la GUI.

Pasos del wizard (cada uno marca un check verde en la GUI):
    1. get_me(token)        -> valida el bot (getMe) y devuelve @username.
    2. (usuario abre Telegram y escribe cualquier cosa al bot)
    3. detect_chat_id(token)-> getUpdates -> extrae el chat_id del último mensaje.
    4. send_test(token,chat)-> sendMessage de prueba (ENVÍA TELEGRAM REAL).
    5. save_to_env(token,chat) -> escribe TELEGRAM_TOKEN / TELEGRAM_CHAT_ID en el
       .env del servidor, preservando el resto del archivo.

Cada función devuelve (ok: bool, info: str) para que la GUI muestre éxito/fallo
con texto claro. El TOKEN nunca se loguea en claro hacia el log de la GUI (se
enmascara en los mensajes de retorno).

VERIFICACIÓN: en la verificación headless solo se llama get_me() con el token
del .env (NO send_test, para no spamear el chat real).
"""

from __future__ import annotations

import re

import requests

from . import paths

_API = "https://api.telegram.org"
_TIMEOUT = 8.0


def _mask_token(token: str) -> str:
    """Enmascara el token para mensajes (deja ver solo el id numérico previo a ':')."""
    if ":" in token:
        head = token.split(":", 1)[0]
        return f"{head}:***"
    return "***"


def get_me(token: str) -> tuple[bool, str]:
    """
    Valida el bot con getMe.

    Inputs:  token del bot (de @BotFather).
    Outputs: (True, "@username") si el bot es válido; (False, motivo) si no.
    Nunca lanza (errores de red -> (False, texto)).
    """
    token = (token or "").strip()
    if not token:
        return False, "Token vacío. Pégalo desde @BotFather."
    if not re.match(r"^\d+:[A-Za-z0-9_\-]+$", token):
        return False, "El token no tiene el formato esperado (NNNN:XXXX)."
    try:
        resp = requests.get(f"{_API}/bot{token}/getMe", timeout=_TIMEOUT)
        data = resp.json()
    except requests.RequestException as exc:
        return False, f"Error de red llamando a Telegram: {exc}"
    except ValueError:
        return False, "Respuesta no-JSON de Telegram."
    if resp.status_code == 200 and data.get("ok"):
        result = data.get("result", {})
        username = result.get("username", "?")
        name = result.get("first_name", "")
        return True, f"@{username}" + (f" ({name})" if name else "")
    desc = data.get("description", f"HTTP {resp.status_code}")
    return False, f"Bot inválido: {desc}"


def detect_chat_id(token: str) -> tuple[bool, str]:
    """
    Obtiene el chat_id del último mensaje recibido por el bot (getUpdates).

    Requiere que el usuario YA le haya escrito algo al bot desde su Telegram.
    Inputs:  token del bot.
    Outputs: (True, "<chat_id>") con el id del chat más reciente;
             (False, motivo) si no hay mensajes o falla.
    Toma el chat del update más reciente (mensaje normal, editado o de canal).
    """
    token = (token or "").strip()
    if not token:
        return False, "Token vacío."
    try:
        resp = requests.get(f"{_API}/bot{token}/getUpdates", timeout=_TIMEOUT)
        data = resp.json()
    except requests.RequestException as exc:
        return False, f"Error de red: {exc}"
    except ValueError:
        return False, "Respuesta no-JSON de Telegram."
    if not (resp.status_code == 200 and data.get("ok")):
        desc = data.get("description", f"HTTP {resp.status_code}")
        return False, f"getUpdates falló: {desc}"

    updates = data.get("result", [])
    if not updates:
        return False, ("No hay mensajes. Abre Telegram, busca tu bot y envíale "
                       "cualquier texto; luego reintenta 'Detectar mi chat'.")
    # Recorre del más reciente al más antiguo buscando un chat válido.
    for upd in reversed(updates):
        for key in ("message", "edited_message", "channel_post", "my_chat_member"):
            obj = upd.get(key)
            if isinstance(obj, dict):
                chat = obj.get("chat", {})
                chat_id = chat.get("id")
                if chat_id is not None:
                    who = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
                    suffix = f" ({who})" if who else ""
                    return True, f"{chat_id}{suffix}"
    return False, "Updates recibidos pero sin chat_id legible. Reescribe al bot."


def parse_chat_id(chat_str: str) -> str:
    """Extrae el chat_id numérico (con signo) de un string que puede traer '(nombre)'."""
    m = re.match(r"\s*(-?\d+)", chat_str or "")
    return m.group(1) if m else (chat_str or "").strip()


def send_test(token: str, chat_id: str) -> tuple[bool, str]:
    """
    Envía un mensaje de prueba REAL por Telegram (sendMessage).

    OJO: esto SÍ envía un mensaje al chat. Inputs: token + chat_id (numérico).
    Outputs: (True, "enviado") o (False, motivo). Nunca lanza.
    """
    token = (token or "").strip()
    chat_id = parse_chat_id(chat_id)
    if not token or not chat_id:
        return False, "Faltan token o chat_id."
    text = (
        "EMBEBIDOS_1 — Panel de Control: prueba de Telegram correcta. "
        "Tu bot ya puede enviar alertas de seguridad."
    )
    try:
        resp = requests.post(
            f"{_API}/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=_TIMEOUT,
        )
        data = resp.json()
    except requests.RequestException as exc:
        return False, f"Error de red: {exc}"
    except ValueError:
        return False, "Respuesta no-JSON de Telegram."
    if resp.status_code == 200 and data.get("ok"):
        return True, "Mensaje de prueba enviado. Revisa tu Telegram."
    desc = data.get("description", f"HTTP {resp.status_code}")
    return False, f"Telegram rechazó el mensaje: {desc}"


def save_to_env(token: str, chat_id: str) -> tuple[bool, str]:
    """
    Escribe TELEGRAM_TOKEN / TELEGRAM_CHAT_ID en el .env del servidor.

    Preserva el resto del archivo: si las claves existen, las reemplaza; si no,
    las añade al final. Crea el .env si no existiera. NO loguea el token en claro.

    Inputs:  token + chat_id (se normaliza el chat_id a numérico).
    Outputs: (True, "guardado en <ruta>") o (False, motivo).
    """
    token = (token or "").strip()
    chat_id = parse_chat_id(chat_id)
    if not token or not chat_id:
        return False, "Faltan token o chat_id para guardar."

    env_path = paths.SERVER_ENV_FILE
    try:
        if env_path.is_file():
            with open(env_path, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        else:
            lines = []
    except OSError as exc:
        return False, f"No se pudo leer el .env: {exc}"

    def _upsert(lines_in: list[str], key: str, value: str) -> list[str]:
        """Reemplaza la línea 'key=...' (incluida si está comentada como '# key=') o la añade."""
        pat = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
        replaced = False
        out: list[str] = []
        for ln in lines_in:
            if pat.match(ln) and not replaced:
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            out.append(f"{key}={value}")
        return out

    lines = _upsert(lines, "TELEGRAM_TOKEN", token)
    lines = _upsert(lines, "TELEGRAM_CHAT_ID", chat_id)

    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(env_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        import os

        os.replace(tmp, env_path)
    except OSError as exc:
        return False, f"No se pudo escribir el .env: {exc}"

    return True, (f"Guardado en {env_path}. Reinicia el servidor (Desmontar + "
                  "Montar) para que tome el nuevo token/chat.")


if __name__ == "__main__":
    # Verificación headless: SOLO get_me() con el token del .env. NO envía mensajes.
    print("== telegram_wizard self-test (solo getMe; sin enviar mensajes) ==")
    token = ""
    try:
        with open(paths.SERVER_ENV_FILE, "r", encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip().startswith("TELEGRAM_TOKEN="):
                    token = ln.split("=", 1)[1].strip()
                    break
    except OSError:
        pass
    if not token:
        print("No hay TELEGRAM_TOKEN en el .env; nada que validar.")
    else:
        ok, info = get_me(token)
        print(f"get_me({_mask_token(token)}) -> ok={ok} info={info}")

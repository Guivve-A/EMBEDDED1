"""
core/netinfo.py — Información de red de la PC para el Panel de Control.

Funciones:
    local_ip()          — IP IPv4 "principal" de la PC en la LAN (la que verán
                          ESP32-CAM / UNO Q / app). Robusta sin internet.
    all_ipv4()          — todas las IPv4 no-loopback detectadas.
    looks_dhcp(ip)      — heurística: ¿esta IP parece asignada por DHCP?
    suggest_static(ip)  — sugiere una IP estática "alta" en la misma /24
                          (p. ej. .200) para fijarla en el router/adaptador.

Sin dependencias externas (solo stdlib socket). No abre conexiones reales:
para descubrir la IP de salida usa el truco del socket UDP "conectado" a una IP
pública (no envía paquetes), con varios fallbacks.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys

# Flag para que el subprocess de netsh no abra ventana de consola en Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _ip_via_udp() -> str | None:
    """
    Descubre la IP de salida abriendo un socket UDP "conectado" a 8.8.8.8.

    No se envía ningún paquete (UDP connect solo fija la ruta); funciona aunque
    no haya internet, siempre que exista una ruta por defecto. Devuelve None si
    falla por completo.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def all_ipv4() -> list[str]:
    """
    Lista de IPv4 no-loopback del host (puede incluir VPN / virtuales).

    Combina getaddrinfo(hostname) con el descubrimiento por UDP, deduplica y
    descarta 127.* . Nunca lanza (devuelve [] si no encuentra nada).
    """
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    udp = _ip_via_udp()
    if udp and not udp.startswith("127.") and udp not in found:
        # La IP por UDP es la de la ruta por defecto: ponla primera (la "buena").
        found.insert(0, udp)
    return found


def local_ip() -> str:
    """
    Mejor IPv4 de la PC en la LAN (la que se pone en ESP32/UNO Q/app).

    Prioriza la ruta por defecto (UDP). Si todo falla, devuelve 127.0.0.1 para
    no romper la GUI (con un aviso visible en pantalla a cargo del llamador).
    """
    udp = _ip_via_udp()
    if udp:
        return udp
    ips = all_ipv4()
    return ips[0] if ips else "127.0.0.1"


def looks_dhcp(ip: str) -> bool:
    """
    Heurística simple: ¿la IP parece DHCP (no fijada manualmente)?

    No hay forma 100% fiable de saberlo solo desde la IP, así que devolvemos
    True salvo que sea claramente inutilizable (loopback / link-local 169.254.*).
    El objetivo es ANIMAR al usuario a fijar IP estática, no afirmarlo con
    certeza: la GUI muestra el aviso como recomendación, no como diagnóstico.
    """
    if not ip or ip.startswith("127.") or ip.startswith("169.254."):
        return True
    return True  # por defecto recomendamos fijarla; ver docstring


def suggest_static(ip: str) -> str:
    """
    Sugiere una IP estática "alta" en la misma /24 que `ip`.

    P. ej. 192.168.1.37 -> 192.168.1.200. Las direcciones altas suelen quedar
    fuera del pool DHCP típico de los routers domésticos, reduciendo colisiones.
    Si `ip` no es una IPv4 con 4 octetos, devuelve el placeholder genérico.
    """
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return "192.168.1.200"
    return f"{parts[0]}.{parts[1]}.{parts[2]}.200"


# --------------------------------------------------------------------------- #
# Detección de la red WiFi ACTUAL (Windows: netsh wlan show interfaces)
# --------------------------------------------------------------------------- #
#
# El parseo es robusto a español E inglés porque NO depende de la traducción
# exacta de cada etiqueta: localiza la clave por una lista de alias conocidos y
# parte la línea por el PRIMER ':' (las salidas de netsh tienen siempre la forma
# "    Etiqueta            : valor"). Para distinguir "SSID" de "BSSID"/"AP BSSID"
# se exige que la etiqueta sea exactamente "SSID" (no contenga "BSSID").
#
# La banda se toma de la línea "Banda"/"Band" si existe; si el idioma/driver no
# la trae, se INFIERE del canal: 1–14 -> 2.4 GHz, >=32 -> 5 GHz (los canales 5GHz
# en Windows van 36..165; usamos >=32 como umbral conservador).

# Alias de etiquetas (en minúsculas, sin acentos relevantes ya normalizados).
_WIFI_LABELS: dict[str, tuple[str, ...]] = {
    "state": ("estado", "state"),
    "ssid": ("ssid",),                       # se filtra BSSID aparte
    "band": ("banda", "band"),
    "channel": ("canal", "channel"),
    "signal": ("senal", "signal", "seal"),  # 'seal' = 'señal' tras quitar no-ASCII
    "radio": ("tipo de radio", "radio type", "radio"),
}


def _norm(s: str) -> str:
    """
    Normaliza una etiqueta para comparar de forma robusta a la codificación.

    netsh puede entregar acentos/ñ como caracteres no-ASCII o como el carácter de
    reemplazo U+FFFD según la codepage. Para no depender de eso: pasa a minúsculas,
    sustituye los acentos comunes y FINALMENTE descarta todo lo no-ASCII. Así:
        "Señal" -> "seal", "Canal" -> "canal", "Banda" -> "banda".
    """
    s = s.strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n")):
        s = s.replace(a, b)
    # Quita cualquier byte no-ASCII residual (p. ej. U+FFFD de la ñ mal decodificada).
    return "".join(ch for ch in s if ord(ch) < 128).strip()


def _band_from_channel(channel: str | None) -> str:
    """Infiere la banda a partir del número de canal WiFi."""
    if not channel:
        return "desconocida"
    m = re.search(r"\d+", channel)
    if not m:
        return "desconocida"
    ch = int(m.group(0))
    if 1 <= ch <= 14:
        return "2.4 GHz"
    if ch >= 32:
        return "5 GHz"
    return "desconocida"


def _normalize_band(raw: str | None, channel: str | None) -> str:
    """Normaliza el texto de banda de netsh ('2,4 GHz' / '5 GHz') o cae al canal."""
    if raw:
        low = raw.lower().replace(",", ".")
        if "2.4" in low or "2,4" in raw:
            return "2.4 GHz"
        if low.strip().startswith("5") or " 5 " in (" " + low + " ") or "5 ghz" in low:
            return "5 GHz"
        if "6 ghz" in low or low.strip().startswith("6"):
            return "6 GHz"
    return _band_from_channel(channel)


def current_wifi() -> dict:
    """
    Devuelve un dict con la red WiFi a la que está conectada esta PC (Windows).

    Ejecuta `netsh wlan show interfaces` y parsea (robusto a español/inglés):
        connected (bool), ssid, band ("2.4 GHz"/"5 GHz"/"desconocida"),
        channel, signal (% como str), radio, state, ip (IP local).

    Nunca lanza. Fuera de Windows o sin WiFi/adaptador devuelve connected=False
    (con un campo `error` explicando el motivo). La IP local SIEMPRE se incluye
    (vía local_ip()) aunque la conexión sea por cable.
    """
    result: dict = {
        "connected": False,
        "ssid": "",
        "band": "desconocida",
        "channel": "",
        "signal": "",
        "radio": "",
        "state": "",
        "ip": local_ip(),
        "error": "",
    }

    if sys.platform != "win32":
        result["error"] = "Detección WiFi solo soportada en Windows (netsh)."
        return result

    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        result["error"] = "netsh no encontrado."
        return result
    except subprocess.TimeoutExpired:
        result["error"] = "`netsh wlan show interfaces` excedió el tiempo."
        return result
    except OSError as exc:  # noqa: BLE001 — nunca debe romper la GUI
        result["error"] = f"Error ejecutando netsh: {exc}"
        return result

    text = (out.stdout or "") + "\n" + (out.stderr or "")
    band_raw: str | None = None

    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        label, _, value = raw_line.partition(":")
        label_n = _norm(label)
        value = value.strip()
        if not label_n:
            continue

        # SSID: aceptar SOLO la etiqueta exacta "ssid" (excluye bssid/ap bssid).
        if label_n == "ssid":
            result["ssid"] = value
            continue
        if "bssid" in label_n:
            continue

        if any(label_n == a or label_n.endswith(" " + a) for a in _WIFI_LABELS["state"]):
            result["state"] = value
        elif any(a in label_n for a in _WIFI_LABELS["band"]):
            band_raw = value
        elif any(label_n == a or label_n.startswith(a) for a in _WIFI_LABELS["channel"]):
            # "Canal" / "Channel" — evitar capturar otras líneas que contengan la palabra.
            if label_n in ("canal", "channel"):
                result["channel"] = value
        elif any(a in label_n for a in _WIFI_LABELS["signal"]):
            result["signal"] = value
        elif "radio" in label_n:
            result["radio"] = value

    # Conectado si netsh reportó SSID y/o estado "conectado/connected".
    state_low = result["state"].lower()
    has_ssid = bool(result["ssid"])
    connected = has_ssid or state_low in ("conectado", "connected")
    result["connected"] = connected

    if connected:
        result["band"] = _normalize_band(band_raw, result["channel"])
    else:
        if not result["error"]:
            result["error"] = "Sin conexión WiFi (cable o adaptador inactivo)."

    return result


if __name__ == "__main__":
    ip = local_ip()
    print("local_ip()       :", ip)
    print("all_ipv4()       :", all_ipv4())
    print("looks_dhcp(ip)   :", looks_dhcp(ip))
    print("suggest_static() :", suggest_static(ip))
    print("current_wifi()   :", current_wifi())

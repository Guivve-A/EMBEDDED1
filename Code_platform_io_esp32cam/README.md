# ESP32-CAM — Cámara cliente del sistema de seguridad (fw 2.0.0)

Firmware para **AI-Thinker ESP32-CAM** (sensor OV2640, shield **ESP32-CAM-MB**
para flasheo por USB). Rol: cámara cliente del sistema EMBEBIDOS_1.

```
UNO Q (láser+LDR) ──D4──► GPIO13   trigger de captura
GPIO14 ──► UNO Q D9                pulso 1 s = MATCH (persona autorizada)
GPIO15 ──► UNO Q D10               pulso 1 s = INTRUSO
                  │
                  ▼
flash GPIO4 + captura OV2640 ──► HTTPS POST /verify (X-API-Key)
                                 servidor FastAPI en Oracle Cloud
                                 + heartbeat /device/heartbeat cada 15 s
```

**Fail-safe:** si no hay WiFi, el servidor no responde o el JSON es inválido,
se pulsa INTRUSO (mejor una falsa alarma que una intrusión silenciosa).

## Cableado hacia el Arduino UNO Q

| ESP32-CAM | UNO Q | Función |
|---|---|---|
| GPIO13 | D4 | Trigger de captura (UNO Q → ESP32) |
| GPIO14 | D9 | Resultado MATCH (ESP32 → UNO Q) |
| GPIO15 | D10 | Resultado INTRUSO (ESP32 → UNO Q) |
| GND | GND | Tierra común (obligatoria) |
| 5V | 5V | Alimentación (o USB propio de la ESP32) |

Ambas placas trabajan a 3.3 V en sus GPIO: conexión directa, sin divisores.

## Estructura de `src/`

| Archivo | Contenido |
|---|---|
| `config.h.example` | Plantilla de configuración (host, API key, pines, tiempos) |
| `config.h` | Tu copia real con secretos — **en .gitignore, no se commitea** |
| `ca_cert.h` | Raíz ISRG Root X1 (Let's Encrypt) para validar TLS |
| `camera.{h,cpp}` | Init OV2640 (pinout AI-Thinker) + captura JPEG |
| `wifi_portal.{h,cpp}` | Portal AP de configuración + STA con 2 redes en NVS |
| `uploader.{h,cpp}` | POST /verify multipart + heartbeat (HTTPS, X-API-Key) |
| `main.cpp` | Setup + loop no bloqueante (trigger → verify → pulso) |

## 1. Crear `config.h`

```bash
copy src\config.h.example src\config.h     # Windows
```

Edita `src/config.h` y rellena:

- `USE_TLS` — `0` para demo local (HTTP) o `1` para nube (HTTPS). Ver
  **1bis. Modo demo local vs nube** más abajo.
- `SERVER_HOST` — IP de la PC (local) o dominio real (nube, p. ej. `tuproyecto.duckdns.org`).
- `SERVER_PORT` — `8000` (local) o `443` (nube).
- `API_KEY` — vacío en local; la clave del deploy de Oracle Cloud en nube.
- (Opcional) `TLS_INSECURE 1` solo si necesitas depurar problemas de
  certificado: cifra el canal pero **no** valida la identidad del servidor.
  En producción déjalo en `0` (usa la raíz ISRG Root X1 embebida).

## 1bis. Modo demo local vs nube (`USE_TLS`)

El firmware soporta dos transportes, seleccionables con `USE_TLS` en
`config.h`. El resto del flujo (multipart, parseo JSON, fail-safe INTRUDER,
flash, pulsos) es idéntico en ambos modos.

| Parámetro     | LOCAL (demo, `USE_TLS 0`)        | NUBE (`USE_TLS 1`)                  |
|---------------|----------------------------------|-------------------------------------|
| Transporte    | HTTP plano (`WiFiClient`)        | HTTPS (`WiFiClientSecure` + cert)   |
| `SERVER_HOST` | IP local de la PC (`192.168.x.x`)| dominio (`embebidos.duckdns.org`)   |
| `SERVER_PORT` | `8000` (FastAPI dev)             | `443` (Nginx)                       |
| `API_KEY`     | `""` (vacío; el dev no la exige) | clave real (se envía `X-API-Key`)   |
| NTP           | omitido (no se valida cert)      | requerido (validación del cert TLS) |
| Cert ISRG     | no se compila ni enlaza          | embebido (`ca_cert.h`)              |

El header `X-API-Key` solo se envía si `strlen(API_KEY) > 0`, por eso en
local con `API_KEY ""` no se manda y el server dev no lo exige.

**Para la demo local** deja en `config.h`:

```c
#define USE_TLS       0
#define SERVER_HOST   "192.168.100.23"   // IP de TU PC en la red local
#define SERVER_PORT   8000
#define API_KEY       ""
```

> La IP local de la PC es **DHCP y puede cambiar**. Antes de la demo, fija
> una IP estática en la PC (o reserva DHCP en el router) o reajusta
> `SERVER_HOST` y vuelve a flashear. Verifica con `ipconfig` y arranca el
> server con `uvicorn ... --host 0.0.0.0 --port 8000`.

**Para volver a la nube** cambia a:

```c
#define USE_TLS       1
#define SERVER_HOST   "embebidos.duckdns.org"
#define SERVER_PORT   443
#define API_KEY       "TU_API_KEY_REAL"
```

## 2. Compilar y flashear (shield ESP32-CAM-MB)

1. Monta la ESP32-CAM sobre el shield MB y conéctalo por USB.
2. Compila y sube:

```bash
pio run -e esp32cam -t upload
```

El shield MB automatiza el modo de programación (no hace falta puentear IO0
a GND; si una placa se resiste, mantén pulsado IO0/BOOT al iniciar la subida).

3. Monitor serie:

```bash
pio device monitor -b 115200
```

## 3. Configurar WiFi (portal `FaceCam_Setup`)

En el **primer boot** (o si se borraron las credenciales) la cámara levanta
el AP:

- SSID: `FaceCam_Setup` · Contraseña: `facecam1234`
- Conéctate desde el móvil y abre **http://192.168.4.1**
- Ingresa la red principal y (opcional) una de respaldo → *Guardar*.
- La cámara se reinicia y queda en modo cliente (STA) permanentemente.

Notas:
- `GET /reset` en el portal borra las credenciales guardadas.
- Si ambas redes fallan 3 ciclos seguidos en operación, el portal se reabre
  automáticamente (las credenciales se conservan en NVS).
- En modo portal **no** se procesan triggers del UNO Q.

## 4. Prueba de banco (sin UNO Q)

1. Flashea, configura WiFi y abre el monitor serie.
2. Espera el log `[OK] Operativo...` y verifica que el heartbeat reporte
   `heartbeat OK` (el servidor debe estar accesible).
3. **Puentea GPIO13 a 3.3V un instante** (cable dupont): debe verse el flash,
   el log `[TRIG] Disparo recibido...`, la captura y el resultado del POST.
4. Comprueba el pulso de resultado (1 s) en GPIO14 o GPIO15 con un LED de
   prueba (con resistencia) o multímetro.
5. En el servidor: el evento aparece en `GET /events` y la alerta llega por
   Telegram/FCM según corresponda.

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| `[NTP] AVISO: sin hora válida` | Sin salida a internet; la validación TLS fallará. Revisa la red o usa `TLS_INSECURE 1` para aislar el problema. |
| `/verify respondió 401` | `API_KEY` incorrecta en `config.h`. |
| `fallo de conexión` en cada POST | `SERVER_HOST` mal escrito, puerto 443 cerrado, o certificado no emitido por Let's Encrypt (la raíz embebida es ISRG Root X1). |
| Triggers fantasma al arrancar | Ya mitigado: se ignoran los primeros 3 s tras el boot (`BOOT_IGNORE_TRIGGER_MS`). |
| Cámara no detectada | Revisa el asiento del flex del OV2640; el firmware sigue arrancando y reporta `camera_ok=false` por heartbeat. |

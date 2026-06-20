# FaceSecurity — Fase 5 (v2): versión DEFINITIVA del Arduino UNO Q

Proyecto **Arduino App Lab** para el **Arduino UNO Q** (EMBEBIDOS_1, Ing 2).
Integra todo el lado UNO Q del sistema tras el pivote v2 (vuelve la ESP32-CAM):

- **MCU (sketch/)**: LDR analógica autocalibrada (A0) + láser KY-008 (D7) +
  buzzer (D8) + LEDs (D5/D6) + **disparo de captura a la ESP32-CAM (D4)** +
  **resultado MATCH/INTRUDER (D9/D10)** con timeout fail-safe de 15 s.
- **Linux (python/ + host/)**: portal WiFi AP de F4 **intacto** (`:7000`) +
  **bridge cloud** nuevo: sondea `GET /state` del servidor cada 5 s y reenvía
  `ARM`/`DISARM` al MCU; manda heartbeat `{"device_id":"unoq"}` cada 15 s.

---

## 1. Cableado completo

### 1a. Componentes locales del UNO Q (forma UNO R3)

| Pin | Función | Componente | Notas |
|-----|---------|------------|-------|
| D13 | LED "vivo" (blink 500 ms) | LED onboard | sin cableado |
| D7  | Salida: enciende el haz | Láser KY-008 | S→D7, +→5V (según módulo), −→GND |
| **A0** | **Entrada ANALÓGICA: LDR** | Fotorresistencia | ver divisor abajo |
| D8  | Salida: buzzer | Buzzer activo | + a D8, − a GND |
| D5  | LED VERDE (armado 1 Hz / match) | LED verde | + R 220 Ω a GND |
| D6  | LED ROJO (alarma) | LED rojo | + R 220 Ω a GND |
| D3  | Botón reset WiFi (hold 3 s) | Pulsador | `INPUT_PULLUP`, otro extremo a GND |

**Divisor de la LDR (A0):**

```
3.3V ──── LDR ────┬──── A0 (UNO Q)
                  │
                 10 kΩ
                  │
                 GND
```

Con el haz del láser sobre la LDR la lectura de A0 es ALTA; al cortarse el haz,
CAE. El firmware **autocalibra al boot** (3 s de promedio con el haz puesto) y
declara "haz roto" cuando la lectura baja del **60 %** de esa línea base
(`LDR_DROP_PCT` en `sketch/config.h`). **Apunta el láser a la LDR ANTES de
encender/arrancar la app** y evita que el sol incida directo sobre la LDR.

### 1b. Los 4 cables hacia la ESP32-CAM (ambas placas son 3.3 V lógicos)

| # | De | A | Función |
|---|----|---|---------|
| 1 | UNO Q **D4** | ESP32-CAM **GPIO13** | TRIGGER: pulso 200 ms = "captura ya" |
| 2 | ESP32-CAM **GPIO14** | UNO Q **D9** | RESULT MATCH: pulso ~1 s = autorizado |
| 3 | ESP32-CAM **GPIO15** | UNO Q **D10** | RESULT INTRUDER: pulso ~1 s = intruso |
| 4 | UNO Q **GND** | ESP32-CAM **GND** | tierra común (OBLIGATORIO) |

Alimentación de la ESP32-CAM: **UNO Q 5V → ESP32-CAM 5V** (o su propio USB con
el shield MB; en ese caso igual conecta el GND común).

> D9/D10 se configuran como `INPUT_PULLDOWN` (lo soporta el core
> `arduino:zephyr` / ArduinoCore-API del STM32U585). Si en una revisión futura
> del core no compilara, cambia `RESULT_PIN_MODE` a `INPUT` en
> `sketch/config.h` y agrega una **resistencia externa de 10 kΩ a GND** en D9
> y otra en D10.

---

## 2. Máquina de estados (MCU)

```
DISARMED ──ARM──► ARMED (verde 1 Hz)
ARMED ── haz cortado ≥200 ms ──► buzzer ON + pulso 200 ms D4 ──► WAIT_RESULT
WAIT_RESULT ── flanco D9 (MATCH) ───► buzzer OFF + verde FIJO 3 s ──► ARMED
WAIT_RESULT ── flanco D10 (INTRUDER) ► ALARM: rojo FIJO + buzzer ── DISARM ──► DISARMED
WAIT_RESULT ── 15 s sin resultado ──► ALARM fail-safe: rojo PARPADEANTE + buzzer
DISARM (serial/cloud) desde cualquier estado: silencia todo ──► DISARMED
```

Comandos por el **Monitor** de App Lab (una línea + Enter):
`ARM` | `DISARM` | `CAL` (recalibra la LDR, 3 s con el haz puesto) | `STATUS`.

---

## 3. Cómo iniciar la app desde App Lab

La app queda staged en `~/ArduinoApps/face_security_f5` del UNO Q, así que
**aparece sola en la GUI de App Lab**:

1. Abre **Arduino App Lab** con el UNO Q conectado por USB.
2. Busca **"FaceSecurity F5 (definitiva)"** (icono 🛡️) y pulsa **Start**.
   App Lab compila el sketch, lo flashea y arranca el lado Linux.
3. Abre el **Monitor**: verás `Boot F5: calibrando LDR...` y luego
   `Boot OK - F5` con la `baseline` medida. (Mantén el haz sobre la LDR
   durante esos ~3 s.)

**Ayudante de host del portal WiFi** (igual que F4, una sola vez por sesión de
configuración; por ADB o SSH al UNO Q):

```bash
cd ~/ArduinoApps/face_security_f5/host
chmod +x fs_wifi.sh fs_wifi_watch.sh fs_mcu_watch.sh
./fs_wifi.sh ap-up                                        # AP FaceSecurity_Setup
nohup ./fs_wifi_watch.sh >/tmp/fs_wifi_watch.log 2>&1 &   # aplica lo guardado
```

Portal: `http://10.42.0.1:7000` (red `FaceSecurity_Setup`, clave `setup1234`).
Si el UNO Q ya tiene redes guardadas de F4, **no hace falta repetir nada**: los
perfiles de NetworkManager persisten.

---

## 4. Configurar el bridge cloud (`cloud.json`)

El bridge lee `cloud.json` en la **raíz de la app** (junto a `app.yaml`).
No está versionado; créalo desde la plantilla:

```bash
cd ~/ArduinoApps/face_security_f5
cp cloud.json.example cloud.json
nano cloud.json     # SERVER_HOST = dominio DuckDNS del deploy; API_KEY = la del deploy
```

Mientras `cloud.json` no exista o tenga placeholders, el bridge espera (lo
reintenta cada 30 s) **sin afectar al portal WiFi ni al MCU**. Con config
válida:

- cada **5 s**: `GET https://<SERVER_HOST>/state` → si `armed` cambió, envía
  `ARM`/`DISARM` al MCU;
- cada **15 s**: `POST /device/heartbeat {"device_id":"unoq","fw":"5.0.0-f5"}`
  con header `X-API-Key`.

**Vía python→MCU:** primaria = **RPC del RouterBridge** (el sketch registra
`Bridge.provide("arm"/"disarm"/"cal")` y el python llama `Bridge.call(...)` de
`arduino.app_utils`). Si el runtime de App Lab no expone ese objeto, el bridge
cae solo al **patrón archivo+watcher de F4**: escribe `mcu_request.json` y el
host lo reenvía con `host/fs_mcu_watch.sh` (lanzarlo igual que el watcher
WiFi). El log de la app dice qué vía quedó activa (`[cloud_bridge] ...`).

---

## 5. Prueba de banco (sin ESP32-CAM ni servidor)

1. **Arranque:** Start en App Lab → Monitor muestra la calibración y
   `Boot OK - F5` con `baseline`/`threshold`. `STATUS` muestra `beam=OK`.
2. **Armar:** escribe `ARM` → LED verde parpadea a 1 Hz.
3. **Intrusión (tapar la LDR):** cubre la LDR (o corta el haz) ≥200 ms →
   **buzzer suena de inmediato** y D4 emite un **pulso de 200 ms** (verifícalo
   con un LED+resistencia de D4 a GND, o con multímetro en modo pico). El
   Monitor imprime `INTRUSION DETECTED ... esperando resultado (15 s)`.
4. **Simular MATCH:** puentea **D9 a 3.3 V** un instante → buzzer OFF, verde
   FIJO 3 s y vuelve a parpadear (re-armado).
5. **Repite la intrusión y simula INTRUDER:** puentea **D10 a 3.3 V** → rojo
   FIJO + buzzer continuos. `DISARM` silencia todo.
6. **Timeout fail-safe:** repite la intrusión y NO puentees nada → a los 15 s
   el rojo queda **PARPADEANTE** + buzzer (distinto del caso intruso). `DISARM`.
7. **Recalibración:** si cambia la luz ambiente, `CAL` con el haz puesto.
8. **Botón WiFi:** mantener D3 3 s → `RESET_REQUEST` en el Monitor (el watcher
   WiFi borra las redes y vuelve al AP).

Prueba del bridge sin Oracle: apunta `SERVER_HOST` a la PC en la LAN
(`"SERVER_HOST": "http://192.168.100.23:8000"`) con el server FastAPI local
corriendo; al cambiar `armed` con `POST /arm` / `POST /disarm`, el MCU debe
armarse/desarmarse solo (míralo en el Monitor).

---

## 6. Estructura de la app

```
face_security_f5/
├── app.yaml               # metadatos App Lab: brick web_ui + puerto 7000
├── cloud.json.example     # plantilla del bridge (SERVER_HOST/API_KEY) — versionada
├── .gitignore             # cloud.json + archivos de runtime NO se versionan
├── sketch/
│   ├── sketch.ino         # máquina de estados + trigger/result + comandos
│   ├── config.h           # pines, tiempos, umbral LDR (punto único de config)
│   ├── laser_sensor.h/.cpp# LDR analógica + autocalibración (debounce de F2 intacto)
│   ├── alerts.h/.cpp      # buzzer (F2) + patrones de LED no bloqueantes
│   └── sketch.yaml        # perfil de build (arduino:zephyr)
├── python/
│   ├── main.py            # portal WiFi F4 (intacto) + arranque del bridge
│   └── cloud_bridge.py    # poll /state + heartbeat + envío ARM/DISARM al MCU
├── host/                  # SOLO lado Linux del UNO Q (fuera del contenedor)
│   ├── fs_wifi.sh         # motor WiFi nmcli (de F4, sin cambios)
│   ├── fs_wifi_watch.sh   # aplica lo que el portal guarda (ruta f5)
│   └── fs_mcu_watch.sh    # FALLBACK python→MCU (solo si el RPC no está)
└── assets/
    ├── index.html         # portal (negro/oro, de F4)
    └── app.js             # lógica del portal (de F4)
```

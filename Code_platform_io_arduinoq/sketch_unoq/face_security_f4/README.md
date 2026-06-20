# FaceSecurity — Fase 4: WiFi modo AP + Portal de configuracion + 2 redes persistentes

Proyecto **Arduino App Lab** para el **Arduino UNO Q** (EMBEBIDOS_1, Ing 2).
Levanta un **Access Point de configuracion** y un **portal web** para guardar
**2 redes WiFi** (primaria + respaldo); al guardar, el dispositivo **conmuta a
modo cliente**. Un **boton fisico** borra las redes y vuelve al AP.

---

## 0. Lo mas importante que debes saber (arquitectura real del UNO Q)

El UNO Q **no es un ESP32**. Es **hibrido**: un micro **STM32U585** (donde corre
el *sketch*) **+ un lado Linux (Qualcomm)** que es **quien tiene el WiFi**.

> **El WiFi NO se controla desde el sketch del MCU.** No existe `WiFi.h` para el
> sketch del UNO Q. El AP, las 2 redes y el cambio a cliente se gestionan en el
> **lado Linux** con **NetworkManager** (`nmcli`), y el portal se sirve con el
> **brick `web_ui`** de App Lab. El sketch del MCU solo coordina **LEDs de
> estado** y el **boton de reset**.

Equivalencias con el plan original (que estaba pensado para ESP32):

| Plan original (ESP32)            | Realidad en el UNO Q (lado Linux)                          |
|----------------------------------|------------------------------------------------------------|
| AP en `192.168.4.1`              | NetworkManager modo *shared* → gateway **`10.42.0.1`**     |
| Portal HTTP en `:80`             | Brick `web_ui` (FastAPI/Uvicorn) en **`:7000`**            |
| Guardar 2 redes en **EEPROM**    | **2 perfiles persistentes de NetworkManager** (la "EEPROM")|
| `ESP.restart()` → cliente        | `nmcli connection up` del perfil primario (autoconnect)    |
| Boton reset borra EEPROM         | `fs_wifi.sh reset` borra los perfiles y reactiva el AP     |

**Portal de configuracion (en modo AP):** `http://10.42.0.1:7000`

---

## 1. Tabla de pinout completa del proyecto

Forma **UNO R3** (pines `D0..D13`, `A0..A5`). Los pines digitales de abajo ya se
**validaron en hardware** en F1/F2 (el sketch compilo y corrio con estos alias).
Conecta cada LED con su resistencia (≈220 Ω) a GND, y el boton entre el pin y GND.

| Pin    | Funcion                         | Componente            | Fase | Notas de cableado |
|--------|---------------------------------|-----------------------|------|-------------------|
| D13    | LED "vivo" (blink 500 ms)       | LED onboard           | F1   | Es el LED de la placa; no requiere cableado |
| D7     | Salida: enciende el haz laser   | Modulo laser emisor   | F2   | Activo en ALTO (`HIGH` enciende). Alim. segun modulo |
| D2     | Entrada: receptor del haz       | Receptor IR / fototr. | F2   | `INPUT_PULLUP`. Haz roto = `HIGH`. D2 soporta interrupciones |
| D8     | Salida: buzzer                  | Buzzer activo         | F2   | Activo en ALTO. Otro extremo a GND |
| **D5** | **LED VERDE** (ON = CLIENTE/OK) | LED verde             | F4/F5| **+ R 220 Ω a GND**. Encendido = conectado a tu red |
| **D6** | **LED ROJO** (ON = AP/sin red)  | LED rojo              | F4/F5| **+ R 220 Ω a GND**. Encendido = modo AP / sin red |
| **D3** | **BOTON RESET** (mantener 3 s)  | Pulsador              | F4   | `INPUT_PULLUP`, **otro extremo a GND**. 3 s = borra redes → AP |
| 5V/GND | Alimentacion                    | Fuente / USB          | —    | GND comun para todos los componentes |

### Camara OV7670 (Fase 3 — pendiente de definir)

El OV7670 es **paralelo** (D0–D7, PCLK, HREF, VSYNC, XCLK, SIOD, SIOC, RESET,
PWDN). En la forma UNO R3 **no caben** como pines `D22..D37`: ese mapeo del
`config.h` del proyecto PlatformIO es **placeholder y NO valido** para el UNO Q.
El bus de camara real depende del conector/DCMI que exponga el core Zephyr del
UNO Q y **se definira en F3**. **No cablees la camara con esos numeros.**

> Pines **ocupados** por F2/F4/F5: D2, D3, D5, D6, D7, D8, D13. Para F3 quedan
> libres D0, D1, D4, D9–D12 y A0–A5, pero el OV7670 necesita ~16 lineas: muy
> probablemente la camara ira por un **conector dedicado**, no por estos pines.
> Se decide en F3.

---

## 2. Como cargar el proyecto desde Arduino App Lab (GUI)

La app ya quedo instalada en el UNO Q en `~/ArduinoApps/face_security_f4`, asi
que **aparece sola en App Lab**. Pasos:

1. Abre **Arduino App Lab** en tu PC (con el UNO Q conectado por USB).
2. En la lista de apps, busca **"FaceSecurity F4 (WiFi setup)"** (icono 🔒).
3. Pulsa **Run / Start**. App Lab compila el sketch del MCU, lo flashea y
   arranca el portal web (brick `web_ui`) en el lado Linux.
4. Abre el **Monitor Serial** de App Lab para ver `Boot OK - F4` y el banner de
   pinout. (El Serial del UNO Q solo se ve con la app corriendo.)

> **Importante (paso unico) — habilitar el motor WiFi del lado Linux.**
> El portal corre en un contenedor que **no puede tocar el WiFi del host**. Por
> eso hay un pequeno ayudante de host que aplica los cambios con `nmcli`.
> Lanzalo **una vez** (por ADB o SSH al UNO Q) y dejalo corriendo mientras
> configuras:
>
> ```bash
> cd ~/ArduinoApps/face_security_f4/host
> chmod +x fs_wifi.sh fs_wifi_watch.sh
> ./fs_wifi.sh ap-up                 # levanta el AP FaceSecurity_Setup
> nohup ./fs_wifi_watch.sh >/tmp/fs_wifi_watch.log 2>&1 &   # aplica lo que guardes
> ```
>
> (Los archivos `host/` tambien estan versionados en la PC, ver seccion 5.)

---

## 3. Como validar la Fase 4 (paso a paso)

1. **Levanta el AP.** En el UNO Q: `./host/fs_wifi.sh ap-up`.
   Verifica con `./host/fs_wifi.sh status` que `wlan0` quedo en el AP y con IP
   `10.42.0.1`.
2. **Conecta tu celular** a la red WiFi **`FaceSecurity_Setup`** (clave
   `setup1234`).
3. **Abre el portal**: navega a **`http://10.42.0.1:7000`**. Veras el formulario
   (paleta negro/oro) con "Red primaria" y "Red de respaldo (opcional)".
4. **Llena 2 redes** (al menos la primaria) y pulsa **"Guardar y conectar"**.
   - El portal escribe la solicitud; el ayudante de host crea **2 perfiles
     NetworkManager** y conmuta a **cliente**.
   - El **AP `FaceSecurity_Setup` desaparece** (el radio pasa a cliente): es lo
     esperado. Reconectate a tu WiFi normal.
5. **Comprueba la conexion**: en el UNO Q `./host/fs_wifi.sh status` debe mostrar
   `wlan0` conectado a tu red y una IP de tu LAN. El **LED verde (D5)** queda
   encendido si el MCU recibio `MODE CLIENT`.
6. **Persistencia ("EEPROM"):** reinicia el UNO Q (o `nmcli` se reactiva solo).
   `./host/fs_wifi.sh has-creds` devuelve **SI** y NetworkManager reconecta solo
   a la red guardada. Las redes sobreviven reinicios.
7. **Reset de fabrica:** manten el **boton D3 unos 3 s** → el Serial imprime
   `RESET_REQUEST` y el LED onboard parpadea rapido. Ejecuta
   `./host/fs_wifi.sh reset` (o el watcher lo hace si recibe la accion): borra
   las 2 redes y vuelve a **modo AP**. (Sin el boton cableado puedes probar el
   reset directamente con `./host/fs_wifi.sh reset`.)

> **Sin hardware cableado todavia:** puedes validar TODO lo de red sin LEDs ni
> boton — pasos 1–6 y el reset por `fs_wifi.sh reset`. Los LEDs (D5/D6) y el
> boton (D3) solo afectan el feedback fisico, no la logica WiFi.

---

## 4. Estructura de la app

```
face_security_f4/
├── app.yaml              # metadatos App Lab: brick web_ui + puerto 7000
├── python/main.py        # portal web (lado Linux): sirve assets + API REST
├── assets/
│   ├── index.html        # formulario del portal (negro/oro, CSS en linea)
│   └── app.js            # logica del portal (fetch a /api/status,/save,/reset)
├── sketch/
│   ├── sketch.ino        # MCU: LEDs de estado + boton reset + Serial
│   ├── config.h          # pines y constantes del sketch
│   └── sketch.yaml       # perfil de build (arduino:zephyr)
└── host/                 # SOLO lado Linux (no es del MCU ni del contenedor)
    ├── fs_wifi.sh        # motor WiFi real con nmcli (AP, save, client, reset)
    └── fs_wifi_watch.sh  # aplica lo que el portal guarda (puente contenedor→host)
```

Flujo de una configuracion:
`portal (contenedor)` → escribe `wifi_request.json` → `fs_wifi_watch.sh (host)`
→ `fs_wifi.sh save` (`nmcli`) → 2 perfiles NM + cliente → `wifi_status.json` →
el portal muestra el nuevo estado.

---

## 5. Comandos del motor WiFi (`host/fs_wifi.sh`)

```bash
./fs_wifi.sh status                       # estado del radio y la conexion
./fs_wifi.sh ap-up                        # levanta el AP de setup
./fs_wifi.sh ap-down                      # baja el AP
./fs_wifi.sh save SSID1 PASS1 SSID2 PASS2 # guarda 2 redes y conmuta a cliente
./fs_wifi.sh client-up                    # conecta al primario (o backup)
./fs_wifi.sh has-creds                    # exit 0 si hay redes guardadas
./fs_wifi.sh reset                        # borra redes y vuelve a AP
```

`PASS2`/`SSID2` pueden ir vacios (`""`) si no quieres red de respaldo.

---

## 6. Notas y limites

- **Un solo radio WiFi.** El UNO Q no puede estar en AP y en cliente a la vez;
  por eso, al guardar, el AP se cae y el dispositivo entra a tu red. Es normal.
- **Permisos.** El usuario `arduino` gestiona WiFi con `nmcli` **sin sudo**
  (grupo `netdev` + polkit). No hace falta contrasena para AP/perfiles.
- **Por que un ayudante de host.** Las apps de App Lab corren en contenedor sin
  acceso a NetworkManager; el ayudante de host es el puente minimo y seguro.
- **F5** (cliente + POST `/verify`) reusa estos perfiles: una vez en modo
  cliente, el envio de la foto al servidor lo hace el lado Linux (ver F5).

# Panel de Control — EMBEBIDOS_1 (CustomTkinter)

GUI de escritorio "plug & play" que orquesta **todo** el sistema de seguridad
con botones grandes, semáforos de estado por componente, barras de progreso y un
área de log "Mostrar registros". Look oscuro/moderno (negro absoluto + oro,
identidad visual del proyecto).

No es un servicio: es el **panel del operador** para montar el servidor,
configurar Telegram, detectar/flashear el ESP32-CAM y configurar el Arduino
UNO Q, sin tocar la terminal.

---

## 1. Requisitos previos

- **Python 3.11** (se reutiliza el del servidor:
  `Server_python_fastapi\face_server\.venv\Scripts\python.exe`, o crea uno propio).
- **adb** en `…\Android\Sdk\platform-tools\adb.exe` (para el UNO Q).
- **PlatformIO** (`pio`) en `…\.platformio\penv\Scripts\pio.exe` (para flashear el
  ESP32-CAM).
- El servidor FastAPI ya instalado en su venv (este panel solo lo lanza/para).

Si `adb`/`pio` no están en la ruta esperada, el panel los busca en el `PATH`.

---

## 2. Instalación de dependencias

Reutilizando el venv del servidor (recomendado):

```powershell
& "..\Server_python_fastapi\face_server\.venv\Scripts\python.exe" -m pip install -r requirements_gui.txt
```

O con un venv propio del panel:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_gui.txt
```

---

## 3. Cómo se lanza

```powershell
& "..\Server_python_fastapi\face_server\.venv\Scripts\python.exe" app.py
```

(o `<tu_python> Panel_control_python\app.py` desde la raíz del repo).

---

## 4. Qué hace cada panel

| # | Panel | Acción | Llama a |
|---|-------|--------|---------|
| 1 | **Servidor** | Montar/Desmontar uvicorn; espera health `GET /` | `core/server_ctrl.py` → `uvicorn main:app` (venv) |
| 2 | **Red** | Muestra/copia la IP de la PC; sugiere IP estática | `core/netinfo.py` |
| 3 | **Telegram** | Wizard: validar bot → detectar chat → prueba → guardar `.env` | `core/telegram_wizard.py` → getMe / getUpdates / sendMessage |
| 4 | **App** | Instrucciones de instalación + QR con `http://IP:8000` | `qrcode` |
| 5 | **ESP32-CAM** | Semáforo COM + flasheo con log en vivo | `core/esp32_config.py` → `pio run -e esp32cam -t upload` |
| 6 | **Arduino UNO Q** | Config WiFi (2 redes) + `cloud.json` por ADB | `core/unoq_config.py` → adb push + `fs_wifi.sh` |
| 7 | **Registros** | Log común con timestamp, ocultable | — |

### Detección automática

Un hilo en segundo plano sondea cada ~3 s:
- **ESP32-CAM**: puerto COM con chip CP210x/CH340/CH9102 (pyserial; fallback `pio device list`).
- **UNO Q**: `adb devices` (ignora el teléfono Samsung `R58X30WSJNP`).

Los botones 5 y 6 se habilitan solo si el dispositivo está conectado. La UI
nunca se congela: todas las acciones largas corren en hilos y reportan progreso
por una cola hacia el hilo de Tk.

---

## 5. Estructura

```
Panel_control_python/
  app.py                 # ventana CustomTkinter (paneles + log + threading)
  core/
    __init__.py
    paths.py             # rutas absolutas del proyecto (fuente única)
    netinfo.py           # IP local + sugerencia de IP estática
    server_ctrl.py       # start/stop uvicorn + health-check
    devices.py           # detección ESP32 (COM) y UNO Q (adb)
    esp32_config.py      # flasheo pio con stream de progreso
    unoq_config.py       # cloud.json + adb push + fs_wifi.sh
    telegram_wizard.py   # getMe → getUpdates → sendMessage → .env
    guicfg.py            # persistencia de la config de la GUI
  requirements_gui.txt
  README.md
  gui_config.json        # (se crea al usar la GUI; no versionar secretos)
```

---

## 6. Notas

- **Telegram "Enviar prueba" envía un mensaje REAL** al chat detectado.
- **"Guardar en .env"** modifica `Server_python_fastapi\face_server\.env`
  (claves `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID`); reinicia el servidor (Desmontar
  + Montar) para que tome el cambio.
- El panel **no** modifica el firmware, la app ni el código del servidor: solo
  lanza procesos y empuja configuración.
- Al cerrar la ventana, si el servidor lo había lanzado esta GUI, se detiene.
```

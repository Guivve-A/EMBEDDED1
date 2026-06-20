# Face Security Server (FastAPI) — EMBEBIDOS_1

Servidor Python que corre en la PC del proyecto **EMBEBIDOS_1**. Recibe las fotos
capturadas por el **Arduino UNO Q** (cámara OV7670), las almacena, ejecuta el
reconocimiento facial y sirve la API REST que consumen el Arduino (Ing 2) y la
app Kotlin (Ing 1). También dispara alertas Telegram + push FCM.

> **Estado: FASE 7 cerrada** — API completa + almacenamiento (F6) y **motor de
> reconocimiento REAL** (DeepFace + ArcFace, embeddings 512-d, similitud coseno,
> enrolamiento). Telegram y FCM siguen como **stubs** funcionales (devuelven datos
> fake coherentes y loguean); se implementan en las Fases 8 y 9. Ver la sección
> **"Fase 7 — Reconocimiento facial"** más abajo para enrolar y para los detalles de
> Keras 3 / descarga del modelo.

---

## Requisitos

- **Python 3.11+** (probado con 3.11.9 en Windows 11).
- Dependencias en `requirements.txt`. Las de Fase 6 + Fase 7 (DeepFace/ArcFace)
  están **activas**; Telegram (F8) y Firebase (F9) siguen comentadas.
- **Primera inferencia:** DeepFace descarga el modelo **ArcFace (~130 MB)** a
  `~/.deepface/weights/arcface_weights.h5`. Requiere internet la primera vez (ver la
  sección de Fase 7 si la descarga automática falla en Windows).

## Instalación

### Windows (PowerShell)

```powershell
cd Server_python_fastapi\face_server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # luego edita .env si necesitas
```

### Linux / macOS (bash)

```bash
cd Server_python_fastapi/face_server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuración

Toda la configuración vive en `.env` (cargado por `config.py`). **No se hardcodea
nada** en el código. Variables clave:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Interfaz de escucha (0.0.0.0 = accesible desde la LAN). |
| `PORT` | `8000` | Puerto HTTP. |
| `THRESHOLD` | `0.6` | Umbral de reconocimiento (se usa de verdad en Fase 7). |
| `CORS_ORIGINS` | `*` | Orígenes CORS permitidos. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | vacío | Secretos Telegram (Fase 8). |
| `FCM_CREDENTIALS_PATH` | `secrets/serviceAccountKey.json` | Credencial Firebase (Fase 9). |

`.env` y `secrets/` están en `.gitignore`: **nunca se commitean**.

## Cómo levantar el servidor

```powershell
# Opción A (recomendada, con autoreload en desarrollo)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Opción B (arranque directo)
python main.py
```

- **Swagger UI (OpenAPI):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health-check:** http://localhost:8000/

> Para que el **Arduino** y la **app** lleguen al servidor, usa la IP de la PC en
> la LAN (no `localhost`). Averíguala con `ipconfig` (Windows). Ejemplo:
> `http://192.168.1.50:8000`. Asegúrate de permitir el puerto 8000 en el firewall
> de Windows.

---

## Contrato de endpoints

| Método | Ruta | Body / Params | Respuesta |
|--------|------|---------------|-----------|
| `GET`    | `/` | — | info del servicio |
| `POST`   | `/verify` | multipart `file` | `{match, person, confidence, photo_id, latency_ms}` |
| `POST`   | `/enroll` | form `name`, `file` | `{enrolled, person, n_photos}` |
| `GET`    | `/enrolled` | — | `[{name, n_embeddings, enrolled_at}]` |
| `DELETE` | `/enroll/{name}` | — | `{deleted}` |
| `GET`    | `/events` | `?page=1&limit=20` | `{items, total, page, limit}` |
| `GET`    | `/photos/{photo_id}` | — | `image/jpeg` |
| `POST`   | `/arm` | `{armed: bool}` | `{armed}` |
| `POST`   | `/disarm` | — | `{armed: false}` |
| `GET`    | `/state` | — | `{armed, last_event_ts}` |
| `POST`   | `/fcm/register` | `{token}` | `{registered}` |

---

## Ejemplos curl

> En PowerShell, `curl` es un alias de `Invoke-WebRequest`. Para que estos
> ejemplos funcionen tal cual, usa **`curl.exe`** (el binario real, incluido en
> Windows 10/11) o ejecútalos desde Git Bash / WSL.

### POST /verify — enviar una foto (lo que hace el Arduino)

```bash
curl.exe -X POST -F "file=@test.jpg" http://localhost:8000/verify
# → {"match":true,"person":"Guillermo","confidence":0.83,"photo_id":"2026...Z_Guillermo.jpg","latency_ms":4}
```

### POST /enroll — registrar una persona (lo que hace la app)

```bash
curl.exe -X POST -F "name=Guillermo" -F "file=@guillermo.jpg" http://localhost:8000/enroll
# → {"enrolled":true,"person":"Guillermo","n_photos":1}
```

### GET /enrolled — listar personas

```bash
curl.exe http://localhost:8000/enrolled
# → [{"name":"Guillermo","n_embeddings":1,"enrolled_at":"2026-06-01T..."}]
```

### DELETE /enroll/{name} — borrar persona

```bash
curl.exe -X DELETE http://localhost:8000/enroll/Guillermo
# → {"deleted":true}
```

### GET /events — historial paginado

```bash
curl.exe "http://localhost:8000/events?page=1&limit=20"
# → {"items":[{"id":1,"ts":"...","match":true,"person":"...","confidence":0.83,"photo_id":"...","latency_ms":4}],"total":1,"page":1,"limit":20}
```

### GET /photos/{photo_id} — descargar la foto de un evento

```bash
curl.exe http://localhost:8000/photos/2026...Z_Guillermo.jpg --output evento.jpg
```

### POST /arm , POST /disarm , GET /state — control del sistema

```bash
curl.exe -X POST -H "Content-Type: application/json" -d "{\"armed\":true}" http://localhost:8000/arm
# → {"armed":true}

curl.exe -X POST http://localhost:8000/disarm
# → {"armed":false}

curl.exe http://localhost:8000/state
# → {"armed":false,"last_event_ts":"2026-06-01T..."}
```

### POST /fcm/register — registrar token push (lo que hace la app al instalar)

```bash
curl.exe -X POST -H "Content-Type: application/json" -d "{\"token\":\"dummy-token-123\"}" http://localhost:8000/fcm/register
# → {"registered":true}
```

---

## Estructura del proyecto

```
face_server/
├── main.py                 # FastAPI app + todos los endpoints + middleware logging
├── config.py               # carga .env (python-dotenv) + constantes (sin hardcoding)
├── .env.example            # plantilla de config/secretos (copiar a .env)
├── .gitignore              # ignora .env, secrets/, storage de runtime, __pycache__, *.pkl, *.db
├── requirements.txt        # deps Fase 6 activas; F7/F8/F9 comentadas
├── README.md               # este archivo
├── services/
│   ├── recognition.py      # FaceRecognitionService REAL (DeepFace + ArcFace, F7)
│   ├── enrollment.py       # wrapper async sobre recognition (inferencia en thread)
│   ├── telegram_service.py # STUB send_alert (TODO Fase 8)
│   └── fcm_service.py      # STUB notify + register_token real (TODO Fase 9)
├── enroll_cli.py           # CLI de enrolamiento por directorio de fotos (F7)
└── storage/
    ├── photos/             # fotos guardadas {ISO8601}_{person}.jpg (gitignored)
    ├── events.db           # SQLite con el historial de eventos (se crea al arrancar)
    ├── embeddings.pkl      # dict {name: vector_512 L2-normalizado} (real desde F7)
    ├── enrolled_index.json # metadata de personas enroladas (nombre, nº fotos, fecha)
    ├── fcm_tokens.json     # tokens push registrados
    └── state.json          # {armed, last_event_ts}
```

## Logging

Cada request se loguea con el middleware en el formato:

```
timestamp | client_ip | METHOD path | status | latency_ms
```

Ejemplo:

```
2026-06-01T12:00:00.000000+00:00 | 127.0.0.1 | POST /verify | 200 | 5 ms
```

## Fase 7 — Reconocimiento facial (DeepFace + ArcFace)

El motor vive en `services/recognition.py` (clase `FaceRecognitionService`):

| Aspecto | Valor |
|---------|-------|
| Modelo | **ArcFace** (embedding de **512** dimensiones) |
| Detector de cara | **opencv** (`DEEPFACE_DETECTOR`) |
| Métrica | **similitud coseno** sobre embeddings L2-normalizados |
| Umbral | `THRESHOLD = 0.6` (config / `.env`) — match si `sim >= 0.6` |
| Galería | `storage/embeddings.pkl` = `{ nombre: vector_512 }` + `enrolled_index.json` |

Casos que devuelve `POST /verify` (y el método `verify`):

```jsonc
// cara reconocida
{"match": true,  "person": "Guillermo", "confidence": 0.88, "photo_id": "...", "latency_ms": 700}
// cara NO reconocida (bajo umbral)
{"match": false, "person": "unknown",   "confidence": 0.31, "photo_id": "...", "latency_ms": 690}
// NO se detecta cara en la imagen
{"match": false, "person": "unknown",   "confidence": 0.0,  "photo_id": "...", "latency_ms": 25, "error": "no_face"}
```

### ⚠️ Keras 3 — `TF_USE_LEGACY_KERAS=1` (obligatorio)

El entorno trae `keras==3.14.1` (dependencia transitiva de TensorFlow 2.21).
**DeepFace no funciona con Keras 3**: hay que forzar `tf-keras` (Keras 2, ya
instalado) exportando `TF_USE_LEGACY_KERAS=1` **antes** de importar TensorFlow/DeepFace.
El código ya lo fija al inicio de `recognition.py`, `enroll_cli.py` y del script de
verificación (`os.environ.setdefault("TF_USE_LEGACY_KERAS","1")`), así que al
arrancar con `uvicorn main:app` o con `python enroll_cli.py` **no hay que hacer nada
extra**. Si lanzas tu propio script que importe deepface, fija esa variable primero.

### Descarga del modelo ArcFace (~130 MB)

La **primera** inferencia descarga `arcface_weights.h5` (~130 MB) a
`~/.deepface/weights/` (en Windows: `C:\Users\<usuario>\.deepface\weights\`). Por eso
la primera llamada a `/verify` tarda ~10-17 s (carga + construcción del grafo); las
siguientes son de ~0.7 s en CPU.

> **Gotcha Windows (resuelto en el código):** el logger de DeepFace imprime mensajes
> con emojis. En consolas `cp1252` eso lanza `UnicodeEncodeError` y DeepFace lo
> reporta como "fallo al descargar el modelo". `recognition.py` reconfigura
> `stdout/stderr` a UTF-8 al cargarse para evitarlo. Si aun así la descarga
> automática falla (firewall/proxy), descarga el archivo manualmente:
> ```powershell
> curl.exe -L -o "$env:USERPROFILE\.deepface\weights\arcface_weights.h5" `
>   https://github.com/serengil/deepface_models/releases/download/v1.0/arcface_weights.h5
> ```

### Enrolar una persona (CLI)

```powershell
# Recomendado: >= 10 fotos con variación de ángulo/iluminación, una cara por foto.
python enroll_cli.py --name "Guillermo" --photos .\fotos_guillermo\
python enroll_cli.py --name "Guillermo" --photos .\fotos_guillermo\ --replace  # sustituye en vez de fusionar
python enroll_cli.py --list                                                     # lista enrolados
```

El CLI recorre el directorio (`.jpg/.jpeg/.png/.bmp/.webp`), valida cara por foto,
promedia los embeddings válidos, los L2-normaliza y los guarda. Imprime un resumen
con fotos válidas vs rechazadas. También se puede enrolar de a una foto vía la app
con `POST /enroll` (form `name` + `file`).

## Validación de sintaxis (sin instalar dependencias)

```powershell
python -m py_compile config.py main.py services\recognition.py services\enrollment.py services\telegram_service.py services\fcm_service.py enroll_cli.py
```

## Roadmap de fases siguientes

- **Fase 7:** HECHA — `recognition.py` real con DeepFace + ArcFace (embeddings
  512-d, similitud coseno, `enroll_cli.py`). Deps activas en `requirements.txt`.
- **Fase 8:** `telegram_service.py` real con `httpx` (sendPhoto, retry, timeout).
- **Fase 9:** `fcm_service.py` real con `firebase-admin` + `serviceAccountKey.json`.

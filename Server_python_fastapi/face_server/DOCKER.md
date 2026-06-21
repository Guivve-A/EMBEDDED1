# Servidor EMBEBIDOS_1 en Docker (portable a cualquier computadora)

El servidor de reconocimiento facial + alertas se empaqueta en un contenedor para
que corra **igual en cualquier computadora** (Windows, Linux o Mac) sin instalar
Python 3.11, TensorFlow ni DeepFace a mano. La imagen ya trae los modelos
(ArcFace + RetinaFace) pre-descargados.

> El **Panel de Control** (`Panel_control_python`) NO se conteneriza: es una app
> de escritorio que flashea hardware por USB/ADB, así que vive en la PC del
> operador. El contenedor es el **servidor** al que apuntan la ESP32-CAM, el
> UNO Q, la app Android y, si quieres, el propio panel.

## Requisitos en la máquina destino
- **Docker Desktop** (Windows/Mac) o **Docker Engine + plugin compose** (Linux).
- Nada más: ni Python, ni venv, ni dependencias.

## Puesta en marcha (3 pasos)
Desde esta carpeta (`Server_python_fastapi/face_server`):

```bash
# 1) Crear el archivo de configuración (Telegram/FCM son opcionales).
#    Windows PowerShell:  Copy-Item .env.example .env
#    Linux/Mac:           cp .env.example .env
#    Edita .env si quieres alertas de Telegram; si lo dejas vacío, igual funciona.

# 2) (Opcional) Coloca secrets/serviceAccountKey.json si vas a usar FCM.

# 3) Construir y levantar:
docker compose up -d --build
```

La primera construcción descarga TensorFlow/DeepFace y los pesos (varios minutos
y ~4 GB de imagen). Las siguientes veces arranca en segundos.

- **Comprobar que está vivo:** abre `http://localhost:8000/` (responde un JSON) o
  `http://localhost:8000/docs`.
- **Ver logs:** `docker compose logs -f`
- **Detener:** `docker compose down` (los datos quedan en `./storage`).

## Conectar los dispositivos
Los dispositivos de la LAN usan la **IP de la computadora** que corre el
contenedor (no `localhost`), siempre en el puerto **8000**:

- ESP32-CAM / UNO Q / app Android → `http://<IP-de-esta-PC>:8000`
- Averigua la IP: `ipconfig` (Windows) / `ip a` (Linux). Todos deben estar en la
  **misma red WiFi de 2.4 GHz**.

## Datos persistentes
Todo lo que el sistema genera vive en `./storage` (montado como volumen):
`embeddings.pkl`, `enrolled_index.json`, `photos/`, `events.db`, `state.json`.
Puedes borrar y recrear el contenedor sin perder los rostros enrolados ni el
historial.

## Convivencia con el Panel de Control
Puedes usar el panel **como cliente** del contenedor:
- Si el contenedor ya está activo en el 8000, al pulsar **"Montar servidor"** el
  panel detecta que ya está sano y no lanza otro (no hay conflicto de puerto).
- **"Armar/Desarmar"**, **"Validar Intruso"**, Telegram, etc. funcionan igual
  porque hablan con el 8000.
- No uses **"Desmontar servidor"** del panel con el contenedor: para apagarlo usa
  `docker compose down`.

## Notas
- El servidor corre en **CPU** (sin GPU); suficiente para este proyecto.
- Para cambiar el umbral o el detector sin reconstruir: edita `.env`
  (`THRESHOLD`, `DEEPFACE_DETECTOR`, `CONSENSUS_FRAMES`, …) y reinicia:
  `docker compose up -d`.
- Secretos: `.env` y `secrets/` **nunca** se hornean en la imagen; se montan en
  runtime. No subas esos archivos a un registro público.

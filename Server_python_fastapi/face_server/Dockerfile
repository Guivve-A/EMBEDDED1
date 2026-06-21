# =============================================================================
#  Dockerfile — Servidor FastAPI EMBEBIDOS_1 (reconocimiento facial + alertas)
# -----------------------------------------------------------------------------
#  Imagen autocontenida para que el servidor corra IGUAL en cualquier computadora
#  (Windows/Linux/Mac) sin instalar Python 3.11, TensorFlow ni DeepFace a mano.
#
#  - Base: python:3.11-slim (misma versión que el entorno probado, 3.11.x).
#  - Pre-descarga los pesos de ArcFace + RetinaFace → 1ª verificación sin esperas.
#  - Los SECRETOS (.env, secrets/) y los DATOS (storage/) NO se hornean en la
#    imagen: se montan en runtime (ver docker-compose.yml).
#
#  Build:  docker build -t embebidos1-face-server .
#  Run:    docker run --rm -p 8000:8000 --env-file .env \
#                 -v "$(pwd)/storage:/app/storage" \
#                 -v "$(pwd)/secrets:/app/secrets:ro" embebidos1-face-server
#  (Recomendado: usar docker-compose.yml → `docker compose up`.)
# =============================================================================
FROM python:3.11-slim

# Entorno: sin buffer (logs en vivo), sin .pyc, y Keras 2 vía tf-keras
# (TF_USE_LEGACY_KERAS=1 es OBLIGATORIO porque entra keras 3 transitivo con TF).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TF_USE_LEGACY_KERAS=1 \
    TF_CPP_MIN_LOG_LEVEL=3 \
    DEEPFACE_HOME=/root

# Librerías de sistema que necesitan OpenCV (libGL/glib) + curl para los pesos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependencias Python primero (capa cacheable: solo se reinstala si cambia
#    requirements.txt, no en cada cambio de código).
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 2) Pre-descarga de pesos de los modelos a la ruta que usa DeepFace
#    (DEEPFACE_HOME=/root → /root/.deepface/weights). Hace la imagen offline-ready
#    y evita que la 1ª /verify se quede esperando ~250 MB de descarga.
RUN mkdir -p /root/.deepface/weights && \
    curl -fL -o /root/.deepface/weights/arcface_weights.h5 \
        https://github.com/serengil/deepface_models/releases/download/v1.0/arcface_weights.h5 && \
    curl -fL -o /root/.deepface/weights/retinaface.h5 \
        https://github.com/serengil/deepface_models/releases/download/v1.0/retinaface.h5

# 3) Código de la aplicación (lo que cambia a menudo → última capa).
COPY . /app

# El servidor escucha en 8000 (se publica al host en compose/run).
EXPOSE 8000

# storage/ persistente: se monta como volumen en runtime (datos fuera de la imagen).
VOLUME ["/app/storage"]

# Health-check: GET / debe responder 200. start-period amplio porque cargar el
# modelo de IA en el arranque tarda unos segundos.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/',timeout=4).status==200 else 1)"

# Bind 0.0.0.0 para que el ESP32-CAM / UNO Q / app de la LAN lleguen al servidor.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

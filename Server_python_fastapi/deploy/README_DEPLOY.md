# Despliegue del Face Server en Oracle Cloud Always Free (ARM aarch64)

Guía paso a paso para desplegar el servidor FastAPI (`face_server/`) en una VM
**Oracle Cloud Always Free A1.Flex (Ampere ARM, Ubuntu 22.04)**, detrás de
**Nginx + HTTPS (Let's Encrypt)** con dominio **DuckDNS**, protegido por **API
key** y con **borrado automático de fotos**.

> Convención: el usuario por defecto de la imagen Ubuntu de Oracle es `ubuntu`.
> Todas las rutas de ejemplo cuelgan de `/home/ubuntu/EMBEBIDOS_1/...`. Si usas
> otro usuario/carpeta, ajusta `embebidos.service` y `nginx.conf`.

---

## 0. Resumen de la arquitectura de despliegue

```
Internet ──HTTPS:443──► Nginx (certbot/Let's Encrypt) ──proxy──► 127.0.0.1:8000
                         server_name <sub>.duckdns.org           uvicorn (systemd)
                                                                 main:app (FastAPI)
```

- uvicorn escucha SOLO en `127.0.0.1:8000` (no expuesto directo a Internet).
- Nginx termina TLS y hace reverse proxy.
- `embebidos.service` mantiene uvicorn vivo (`Restart=always`).
- El acceso a endpoints sensibles requiere el header `X-API-Key`.

---

## 1. Crear la VM A1.Flex (Ampere ARM) Ubuntu 22.04

1. Oracle Cloud Console → **Compute → Instances → Create instance**.
2. **Image & shape**: Canonical **Ubuntu 22.04**; Shape → **Ampere → VM.Standard.A1.Flex**
   (Always Free: hasta 4 OCPU / 24 GB RAM). Para DeepFace/TF recomiendo
   **2-4 OCPU y >= 8 GB RAM** (TensorFlow es pesado al cargar).
3. Sube tu **clave SSH pública** (o deja que genere una y descárgala).
4. Crea la instancia y anota su **IP pública**.

### Abrir puertos 80 y 443

**(a) Security List (firewall de Oracle, OBLIGATORIO):**
VCN → Subnet → **Security List** → *Add Ingress Rules*:
- Source `0.0.0.0/0`, IP Protocol **TCP**, Destination port **80**.
- Source `0.0.0.0/0`, IP Protocol **TCP**, Destination port **443**.

**(b) Firewall del SO.** Ubuntu de Oracle suele traer reglas `iptables`. Lo más
simple es usar `ufw`:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```
> Si tras esto el puerto sigue cerrado, revisa `sudo iptables -L -n` (la imagen de
> Oracle a veces tiene reglas REJECT en la cadena INPUT antes de ufw; en ese caso:
> `sudo netfilter-persistent flush` o edita `/etc/iptables/rules.v4`).

---

## 2. Dependencias base del sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
                    build-essential git nginx \
                    libgl1 libglib2.0-0          # libs nativas que necesita opencv-python
```
> `libgl1` y `libglib2.0-0` evitan el clásico `ImportError: libGL.so.1` de OpenCV
> en servidores headless.

Comprueba la versión:
```bash
python3.11 --version    # Python 3.11.x
```

---

## 3. Traer el código

Opción git:
```bash
cd /home/ubuntu
git clone <URL_DEL_REPO> EMBEBIDOS_1
cd EMBEBIDOS_1/Server_python_fastapi/face_server
```
Opción scp (desde tu PC, si no hay repo):
```bash
scp -r Server_python_fastapi ubuntu@<IP_PUBLICA>:/home/ubuntu/EMBEBIDOS_1/
```
> NO subas `.env` ni `secrets/serviceAccountKey.json` por git (están en
> `.gitignore`). Los creas en el servidor (pasos 5 y 6).

---

## 4. Crear el venv e instalar dependencias — VALIDAR TensorFlow/DeepFace en aarch64

Este es el **punto crítico** del despliegue en ARM. TensorFlow publica wheels
oficiales para `aarch64`/`manylinux` para Python 3.11, así que normalmente
`pip install` funciona; pero si tu combinación de versión/arquitectura no tiene
wheel, hay fallbacks.

```bash
cd /home/ubuntu/EMBEBIDOS_1/Server_python_fastapi/face_server
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# Intento principal: instalar todo el requirements.txt tal cual.
pip install -r requirements.txt
```

### Test de validación (HAZLO antes de seguir)
```bash
export TF_USE_LEGACY_KERAS=1
python -c "import tensorflow, deepface; print('OK', tensorflow.__version__)"
```
- Si imprime `OK 2.21.0` → TensorFlow/DeepFace funcionan en tu ARM: continúa.
- Warmup real (descarga ArcFace ~130 MB la 1ª vez):
  ```bash
  python -c "from deepface import DeepFace; DeepFace.build_model('ArcFace'); print('ARCFACE OK')"
  ```

### Si `tensorflow==2.21.0` NO instala en aarch64 (fallbacks, en orden)

1. **Deja que pip elija la versión de TF compatible con tu ARM:**
   ```bash
   pip install -r requirements.txt --no-deps        # instala lo demás
   pip install tensorflow                           # versión que sí tenga wheel aarch64
   pip install tf-keras                              # Keras 2 (DeepFace lo exige con TF_USE_LEGACY_KERAS=1)
   ```
   Luego re-ejecuta el test de validación. (DeepFace tolera un rango amplio de
   versiones de TF; lo importante es que `import tensorflow` y `build_model('ArcFace')`
   funcionen.)

2. **Si no hay wheel de TF para tu combinación**, prueba el paquete optimizado para
   ARM de AWS:
   ```bash
   pip install tensorflow-cpu-aws
   pip install tf-keras
   ```
   (Es el build de TF para aarch64 que usa AWS Graviton; mismo `import tensorflow`.)

3. **Último recurso: Docker.** Usa una imagen con TF para ARM y monta el código:
   ```bash
   sudo apt install -y docker.io
   # Dentro del contenedor: instala deepface + el resto y corre uvicorn.
   # (Si llegas aquí, ajusta embebidos.service para lanzar `docker run` en vez de uvicorn.)
   ```
   Imágenes base útiles: `python:3.11-slim` (instalando TF dentro) o una imagen TF
   oficial multi-arch. Mantén el puerto interno 8000 y el `EnvironmentFile` con el
   `.env`.

> Verifica siempre al final con:
> `python -c "import tensorflow, deepface; print('OK')"`

Comprueba que no hay conflictos de dependencias:
```bash
pip check
```

---

## 5. Crear el `.env` de producción (con API_KEY)

Genera una API key aleatoria:
```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

Crea `face_server/.env` (a partir de `.env.example`):
```bash
cp .env.example .env
nano .env
```
Rellena al menos:
```ini
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=*                       # o el origen de tu app si quieres cerrarlo
LOG_LEVEL=INFO

DEEPFACE_MODEL=ArcFace
DEEPFACE_DETECTOR=opencv
THRESHOLD=0.6

# Pega aquí la API key generada arriba:
API_KEY=PEGA_TU_API_KEY_AQUI
PHOTO_RETENTION_DAYS=7
PHOTO_CLEANUP_INTERVAL_HOURS=6

# Telegram (del usuario):
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```
> Nota: como `embebidos.service` arranca uvicorn con `--host 127.0.0.1`, el `HOST`
> del `.env` no se usa para el bind (el flag manda). Da igual el valor; lo importante
> es que uvicorn quede en localhost detrás de Nginx.

---

## 6. Subir el secreto de Firebase

Copia tu `serviceAccountKey.json` a `face_server/secrets/`:
```bash
mkdir -p secrets
# desde tu PC:
scp secrets/serviceAccountKey.json ubuntu@<IP_PUBLICA>:/home/ubuntu/EMBEBIDOS_1/Server_python_fastapi/face_server/secrets/
chmod 600 secrets/serviceAccountKey.json
```
`config.FCM_CREDENTIALS_PATH` usa por defecto la ruta absoluta
`BASE_DIR/secrets/serviceAccountKey.json`, así que no hace falta tocar el `.env`.

---

## 7. DuckDNS: subdominio → IP pública

1. Entra en https://www.duckdns.org , inicia sesión y crea un subdominio
   (p. ej. `embebidos-fs`).
2. Apunta el subdominio a la **IP pública** de la VM (campo *current ip*).
3. (Recomendado) cron de refresco de IP, por si cambia:
   ```bash
   mkdir -p ~/duckdns
   echo 'echo url="https://www.duckdns.org/update?domains=embebidos-fs&token=TU_TOKEN&ip=" | curl -k -o ~/duckdns/duck.log -K -' > ~/duckdns/duck.sh
   chmod 700 ~/duckdns/duck.sh
   (crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
   ```
Verifica:
```bash
dig +short embebidos-fs.duckdns.org      # debe devolver tu IP pública
```

---

## 8. Nginx (reverse proxy)

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/embebidos
# EDITA server_name con tu subdominio real:
sudo nano /etc/nginx/sites-available/embebidos     # TU_SUBDOMINIO.duckdns.org
sudo ln -s /etc/nginx/sites-available/embebidos /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 9. HTTPS con certbot (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d embebidos-fs.duckdns.org   # usa tu subdominio
```
- certbot edita `nginx.conf` añadiendo `listen 443 ssl`, las rutas de los certs y
  el redirect 80 → 443.
- Renovación automática: ya queda un timer systemd. Pruébalo con
  `sudo certbot renew --dry-run`.

---

## 10. systemd: habilitar y arrancar el servicio

```bash
sudo cp deploy/embebidos.service /etc/systemd/system/embebidos.service
# Si tu usuario/rutas difieren de /home/ubuntu, edítalo:
sudo nano /etc/systemd/system/embebidos.service
sudo systemctl daemon-reload
sudo systemctl enable --now embebidos
systemctl status embebidos          # debe estar "active (running)"
journalctl -u embebidos -f          # logs: verás "Warmup ... OK" y "face_server iniciado"
```

---

## 11. Verificación con curl (con y sin API key)

Health (libre, debe responder 200):
```bash
curl -s https://embebidos-fs.duckdns.org/
```

Estado (GET /state libre):
```bash
curl -s https://embebidos-fs.duckdns.org/state
```

Endpoint sensible SIN API key → **401**:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://embebidos-fs.duckdns.org/disarm
# → 401
```

Endpoint sensible CON API key → **200**:
```bash
curl -s -X POST https://embebidos-fs.duckdns.org/disarm \
     -H "X-API-Key: PEGA_TU_API_KEY_AQUI"
# → {"armed": false}
```

Prueba de /verify con una foto:
```bash
curl -s -X POST https://embebidos-fs.duckdns.org/verify \
     -H "X-API-Key: PEGA_TU_API_KEY_AQUI" \
     -F "file=@/ruta/a/una_foto.jpg"
```

> Recuerda: el firmware (Ing 2) y la app (Ing 1) deben enviar el header
> `X-API-Key: <valor>` en los endpoints sensibles cuando el server corre con
> `API_KEY` definida. En modo dev (`API_KEY` vacía) no es necesario.

---

## 12. Mantenimiento

- Logs: `journalctl -u embebidos -f`
- Reiniciar tras cambios: `sudo systemctl restart embebidos`
- Borrado de fotos: automático (tarea del lifespan, cada
  `PHOTO_CLEANUP_INTERVAL_HOURS` borra > `PHOTO_RETENTION_DAYS`). En los logs verás
  `Limpieza de fotos: N archivo(s) ... borrado(s).`
- Cambiar la API key: edita `.env` y `sudo systemctl restart embebidos`.

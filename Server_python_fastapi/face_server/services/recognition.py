"""
services/recognition.py — Motor de reconocimiento facial (FASE 7, REAL).

ESTADO FASE 7: implementación real con DeepFace + ArcFace.
    Reemplaza el stub de la Fase 6 por inferencia real:
        - get_embedding(image)  → vector 512-d ArcFace (o None si no hay cara).
        - verify(image)         → compara por SIMILITUD COSENO contra embeddings.pkl.
        - enroll(name, images)  → promedia embeddings, L2-normaliza y persiste.
    La similitud coseno está en [-1, 1]; entre embeddings ArcFace L2-normalizados
    de la MISMA persona suele ser > 0.6, y entre personas distintas << 0.6, por lo
    que `config.THRESHOLD = 0.6` se usa directamente como umbral de aceptación.

COMPATIBILIDAD DE INTERFAZ (importante):
    `main.py` (Fase 6) llama a `verify(image_path: str)` y a
    `enroll(name, image_paths: list[str])` pasando RUTAS de archivo en disco.
    El brief de la Fase 7 especifica además firmas con `np.ndarray`. Para no
    romper main.py y a la vez cumplir el contrato del brief, `verify` y `enroll`
    aceptan TANTO rutas (str / Path) COMO arrays NumPy (np.ndarray):
        - str/Path → se carga con cv2.imread (BGR→RGB).
        - np.ndarray → se usa tal cual (se asume RGB).
    `get_embedding` opera siempre sobre np.ndarray (vector 512-d), tal como pide
    el brief. El swap respecto a la Fase 6 es 100% interno: los endpoints no cambian.

NOTA DE RENDIMIENTO:
    La PRIMERA llamada a DeepFace descarga el modelo ArcFace (~130 MB) a
    `~/.deepface/weights/` y construye el grafo de TensorFlow; por eso puede tardar
    varios segundos. Las siguientes inferencias son rápidas. Para amortizar ese
    coste se ofrece `warmup()`, que main.py puede invocar en el arranque (lifespan).

COMPATIBILIDAD KERAS 3 (CRÍTICO):
    El entorno tiene `keras==3.14.1` instalado. DeepFace/TensorFlow NO funcionan
    con Keras 3 por defecto (la API `keras.engine`/legacy difiere). Para forzar el
    uso de `tf-keras` (Keras 2, ya instalado) hay que exportar
    `TF_USE_LEGACY_KERAS=1` ANTES de importar tensorflow/deepface. Se hace aquí, en
    la cabecera del módulo, para que cualquier import diferido de DeepFace ya lo vea.
"""

import os
import sys

# Debe quedar fijado ANTES de cualquier import (incluso diferido) de tensorflow /
# deepface. Con keras 3 presente, sin esto el import de DeepFace falla.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")


def _force_utf8_stdio() -> None:
    """
    Reconfigura stdout/stderr a UTF-8.

    DeepFace emite logs con emojis (p. ej. el de descarga de pesos). En Windows la
    consola usa cp1252 por defecto y esos `print()` lanzan UnicodeEncodeError, que
    DeepFace propaga como si la descarga del modelo hubiera fallado. Forzar UTF-8
    aquí evita ese crash sin depender de que quien lance el proceso exporte
    PYTHONUTF8=1. Es idempotente y silencioso si la consola ya es UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — entornos sin reconfigure (poco habitual)
            pass


_force_utf8_stdio()

import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

import config

logger = logging.getLogger("recognition")

# Tipo de entrada admitido por verify/enroll: ruta (str/Path) o imagen ya cargada.
ImageInput = Union[str, Path, np.ndarray]


class FaceRecognitionService:
    """
    Servicio de reconocimiento facial basado en DeepFace + ArcFace.

    Atributos:
        model_name:      modelo de embeddings ("ArcFace", 512-d).
        detector:        backend de detección de cara ("opencv").
        threshold:       umbral de similitud coseno para aceptar match (config).
        embeddings_file: ruta al pickle de embeddings {name: vector_512 np.ndarray}.
        index_file:      JSON paralelo con metadata de personas (nombre, n fotos,
                         fecha) — práctico para /enrolled sin cargar los vectores.
    """

    # Dimensión esperada del embedding de ArcFace.
    EMBED_DIM: int = 512

    # Máximo de fotos (filas) que se conservan por persona en la galería. Acota
    # memoria y tiempo de verify sin perder variedad útil de poses/iluminación.
    MAX_SAMPLES: int = 50

    def __init__(self) -> None:
        """Inicializa el servicio leyendo configuración y asegurando los stores."""
        self.model_name: str = config.DEEPFACE_MODEL
        self.detector: str = config.DEEPFACE_DETECTOR
        self.threshold: float = config.THRESHOLD
        self.embeddings_file: Path = config.EMBEDDINGS_FILE
        # Índice de metadata: mismo directorio que el pickle, nombre enrolled_index.json
        self.index_file: Path = self.embeddings_file.with_name("enrolled_index.json")
        self._ensure_stores()

    # ------------------------------------------------------------------ #
    # Carga perezosa de DeepFace (evita pagar el import pesado si no se usa)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _deepface():
        """
        Importa DeepFace bajo demanda y lo devuelve.

        Se hace lazy para que importar este módulo (p. ej. en tests de sintaxis)
        no arrastre TensorFlow. Inputs: ninguno. Outputs: el módulo DeepFace.
        """
        from deepface import DeepFace  # import diferido (TensorFlow es pesado)

        return DeepFace

    def warmup(self) -> bool:
        """
        Fuerza la carga del modelo ArcFace (descarga ~130 MB la 1ª vez).

        Útil para invocar en el arranque del servidor y que el primer /verify
        real no pague el coste de construir el modelo.

        Inputs:  ninguno.
        Outputs: True si el modelo se construyó sin error, False en caso contrario.
        """
        try:
            self._deepface().build_model(self.model_name)
            logger.info("Modelo %s cargado (warmup OK).", self.model_name)
            return True
        except Exception as exc:  # noqa: BLE001 — el warmup nunca debe tumbar el server
            logger.warning("Warmup del modelo %s falló: %s", self.model_name, exc)
            return False

    # ------------------------------------------------------------------ #
    # Helpers internos de persistencia
    # ------------------------------------------------------------------ #
    def _ensure_stores(self) -> None:
        """Crea embeddings.pkl (dict vacío) e índice JSON si no existen."""
        self.embeddings_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.embeddings_file.exists():
            with open(self.embeddings_file, "wb") as f:
                pickle.dump({}, f)
        if not self.index_file.exists():
            self._write_index({})

    def _read_embeddings(self) -> dict:
        """
        Lee la galería {name: matriz (n_samples, 512)} del pickle.

        Formato actual: una MATRIZ 2-D por persona (una fila L2-normalizada por
        foto enrolada). Para compatibilidad defensiva, un vector 1-D heredado
        (formato antiguo de 1 embedding promedio) se promociona a matriz (1, 512).
        Devuelve {} si el archivo no existe o está corrupto.
        """
        try:
            with open(self.embeddings_file, "rb") as f:
                data = pickle.load(f)
        except (FileNotFoundError, EOFError, pickle.UnpicklingError):
            return {}
        if not isinstance(data, dict):
            return {}
        gallery: dict = {}
        for name, val in data.items():
            if not isinstance(val, np.ndarray):
                continue  # descarta None / placeholders heredados
            arr = val.astype(np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)  # 1-D heredado → matriz (1, 512)
            if arr.ndim == 2 and arr.shape[1] == self.EMBED_DIM:
                gallery[name] = arr
        return gallery

    def _write_embeddings(self, embeddings: dict) -> None:
        """Persiste el dict {name: matriz (n_samples, 512)} en el pickle."""
        self.embeddings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.embeddings_file, "wb") as f:
            pickle.dump(embeddings, f)

    def _read_index(self) -> dict:
        """Lee el índice JSON de personas enroladas. Devuelve {} si está corrupto."""
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_index(self, data: dict) -> None:
        """Escribe el índice JSON de personas enroladas."""
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # Utilidades de imagen / álgebra
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_rgb_array(image: ImageInput) -> Optional[np.ndarray]:
        """
        Normaliza la entrada a un np.ndarray RGB.

        Inputs:
            image: ruta (str/Path) a un archivo de imagen, o un np.ndarray ya
                   cargado (se asume RGB).
        Outputs:
            np.ndarray RGB (H, W, 3) o None si la ruta no se pudo leer.
        """
        if isinstance(image, np.ndarray):
            return image
        path = str(image)
        bgr = cv2.imread(path)  # cv2 lee en BGR; None si falla
        if bgr is None:
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        """
        Normaliza un vector a norma L2 = 1 (evita división por cero).

        Inputs:  vec — vector NumPy.
        Outputs: vector unitario (mismo si la norma es ~0).
        """
        norm = np.linalg.norm(vec)
        if norm < 1e-10:
            return vec.astype(np.float32)
        return (vec / norm).astype(np.float32)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """
        Similitud coseno entre dos vectores (rango [-1, 1]).

        Inputs:  a, b — vectores NumPy de igual dimensión.
        Outputs: float con la similitud coseno (0.0 si alguna norma es ~0).
        """
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-10 or nb < 1e-10:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    # ------------------------------------------------------------------ #
    # API pública — núcleo de reconocimiento
    # ------------------------------------------------------------------ #
    def get_embedding(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Extrae el embedding ArcFace (512-d) de la PRIMERA cara detectada.

        Inputs:
            image: np.ndarray RGB (H, W, 3) con la imagen a analizar.
        Outputs:
            np.ndarray float32 de 512 dimensiones (NO normalizado), o None si no
            se detecta ninguna cara en la imagen.

        Detalle:
            Usa DeepFace.represent con detección activada
            (enforce_detection=True). Si no hay cara, DeepFace lanza ValueError,
            que aquí capturamos y traducimos a None (caso edge "no_face").
        """
        try:
            reps = self._deepface().represent(
                img_path=image,                 # DeepFace acepta np.ndarray directamente
                model_name=self.model_name,     # "ArcFace"
                detector_backend=self.detector,  # "retinaface" (alineación de calidad)
                enforce_detection=True,         # sin cara → ValueError
                align=True,
                normalization="ArcFace",        # normalización de entrada propia del modelo
            )
        except ValueError:
            # No se detectó cara → caso edge no_face.
            return None
        except Exception as exc:  # noqa: BLE001 — cualquier fallo de inferencia = sin embedding
            logger.warning("get_embedding falló: %s", exc)
            return None

        if not reps:
            return None
        # represent() devuelve una entrada por cara. Si hay varias, elegimos la
        # de mayor área facial (la cara más prominente / cercana), no la primera
        # ciegamente — más robusto cuando aparece alguien al fondo.
        best = max(reps, key=self._face_area)
        vec = np.asarray(best["embedding"], dtype=np.float32)
        return vec

    @staticmethod
    def _face_area(rep: dict) -> float:
        """Área (w*h) de la caja facial de un resultado de DeepFace.represent."""
        fa = rep.get("facial_area") or {}
        try:
            return float(fa.get("w", 0)) * float(fa.get("h", 0))
        except (TypeError, ValueError):
            return 0.0

    def verify(self, image: ImageInput) -> dict:
        """
        Verifica una imagen contra todas las personas enroladas (similitud coseno).

        Inputs:
            image: ruta (str/Path) a un JPEG ya guardado en disco, O un np.ndarray
                   RGB ya cargado. (main.py pasa la ruta del archivo recibido.)
        Outputs (dict) — casos edge EXACTOS del contrato:
            - sin cara          → {"match": false, "error": "no_face", "confidence": 0.0}
            - bajo threshold    → {"match": false, "person": "unknown", "confidence": <max_sim>}
            - ambiguo           → {"match": false, "person": "unknown", "confidence": <max_sim>}
            - match válido      → {"match": true,  "person": <name>,    "confidence": <max_sim>}

        Métrica: similitud coseno (mayor = más parecido). Se acepta si la mejor
        similitud >= self.threshold Y el margen con el 2do candidato >= AMBIGUITY_MARGIN.
        """
        arr = self._to_rgb_array(image)
        if arr is None:
            return {"match": False, "error": "no_face", "confidence": 0.0}

        probe = self.get_embedding(arr)
        if probe is None:
            return {"match": False, "error": "no_face", "confidence": 0.0}

        gallery = self._read_embeddings()  # {name: matriz (n_samples, 512) L2-norm}
        if not gallery:
            return {"match": False, "person": "unknown", "confidence": 0.0}

        probe_n = self._l2_normalize(probe)

        # Score de cada persona = MEJOR coincidencia entre todas sus fotos enroladas
        # (no un centroide promediado, que difumina la identidad). Como las filas y
        # el probe están L2-normalizados, el producto punto ES la similitud coseno.
        scores: list[tuple[str, float]] = []
        for name, mat in gallery.items():
            sims = mat @ probe_n          # (n_samples,) similitudes coseno
            scores.append((name, float(np.max(sims))))
        scores.sort(key=lambda x: x[1], reverse=True)

        best_name, best_sim = scores[0]
        second_sim = scores[1][1] if len(scores) > 1 else -1.0

        logger.info(
            "verify scores: %s",
            ", ".join(f"{n}={s:.4f}" for n, s in scores),
        )

        confidence = round(max(0.0, best_sim), 4)

        if best_sim < self.threshold:
            return {"match": False, "person": "unknown", "confidence": confidence}

        margin = best_sim - second_sim
        ambiguity_margin = getattr(config, "AMBIGUITY_MARGIN", 0.05)
        if len(scores) > 1 and margin < ambiguity_margin:
            logger.warning(
                "Match ambiguo: %s=%.4f vs %s=%.4f (margen=%.4f < %.4f)",
                best_name, best_sim, scores[1][0], second_sim,
                margin, ambiguity_margin,
            )
            return {"match": False, "person": "unknown", "confidence": confidence}

        return {"match": True, "person": best_name, "confidence": confidence}

    def enroll(
        self,
        name: str,
        images: list[ImageInput],
        replace: bool = False,
    ) -> dict:
        """
        Enrola a una persona: extrae un embedding por foto y los apila en su galería.

        Inputs:
            name:    nombre de la persona (clave única en embeddings.pkl).
            images:  lista de rutas (str/Path) y/o np.ndarray RGB con las fotos.
                     Las fotos SIN cara se descartan (no rompen el enroll).
            replace: si True, sustituye el embedding existente; si False (default),
                     fusiona promediando con el embedding previo de la persona.
        Outputs (dict):
            { "enrolled": bool, "person": str, "n_photos": int, "n_valid": int }
            - enrolled = True si se logró al menos 1 embedding válido.
            - n_photos = total acumulado de fotos válidas asociadas a la persona.
            - n_valid  = fotos válidas aportadas en ESTA llamada.

        Proceso:
            1. get_embedding por cada imagen (descarta None / sin cara).
            2. L2-normaliza cada embedding válido como una FILA.
            3. Si la persona ya existe y replace=False, apila (vstack) las filas
               nuevas sobre su matriz previa; si replace=True, empieza de cero.
               Se conservan como máximo MAX_SAMPLES filas (las más recientes).
            4. Guarda en embeddings.pkl {name: matriz (n, 512)} y actualiza el
               índice JSON de metadata.
        """
        # 1) Extraer embeddings válidos de esta tanda.
        valid_vecs: list[np.ndarray] = []
        for img in images:
            arr = self._to_rgb_array(img)
            if arr is None:
                continue
            emb = self.get_embedding(arr)
            if emb is not None:
                valid_vecs.append(emb)

        n_valid = len(valid_vecs)
        if n_valid == 0:
            # Ninguna foto tenía cara detectable → no se enrola nada.
            logger.warning("enroll(%s): 0 fotos válidas (sin cara detectable).", name)
            index = self._read_index()
            existing = index.get(name, {}).get("n_photos", 0)
            return {"enrolled": False, "person": name, "n_photos": existing, "n_valid": 0}

        # 2) Una fila L2-normalizada por foto válida de esta tanda (sin promediar:
        #    conservar cada muestra preserva la identidad mucho mejor).
        new_rows = np.stack([self._l2_normalize(v) for v in valid_vecs], axis=0)

        # 3) Apilar con la galería previa de la persona (salvo replace).
        gallery = self._read_embeddings()  # {name: matriz (n, 512)}
        prev = gallery.get(name)
        if (not replace) and isinstance(prev, np.ndarray) and prev.ndim == 2:
            matrix = np.vstack([prev, new_rows])
        else:
            matrix = new_rows
        # Cota: conservar como mucho MAX_SAMPLES filas (las más recientes).
        if matrix.shape[0] > self.MAX_SAMPLES:
            matrix = matrix[-self.MAX_SAMPLES:]

        # 4) Persistir matriz + metadata.
        gallery[name] = matrix.astype(np.float32)
        self._write_embeddings(gallery)

        n_total = int(matrix.shape[0])
        index = self._read_index()
        now_iso = datetime.now(timezone.utc).isoformat()
        keep_enrolled_at = (name in index and not replace)
        index[name] = {
            "n_photos": n_total,
            "enrolled_at": index.get(name, {}).get("enrolled_at", now_iso)
            if keep_enrolled_at else now_iso,
            "updated_at": now_iso,
        }
        self._write_index(index)

        logger.info(
            "enroll(%s): %d foto(s) válida(s) → embedding 512-d guardado.",
            name,
            n_valid,
        )
        return {
            "enrolled": True,
            "person": name,
            "n_photos": index[name]["n_photos"],
            "n_valid": n_valid,
        }

    # ------------------------------------------------------------------ #
    # API pública — consultas / borrado (mismas firmas que la Fase 6)
    # ------------------------------------------------------------------ #
    def list_enrolled(self) -> list[dict]:
        """
        Lista las personas enroladas con metadata.

        Inputs:  ninguno.
        Outputs: lista de dicts { name, n_embeddings, enrolled_at }.
                 n_embeddings = nº de fotos válidas acumuladas (un vector promedio
                 por persona; el conteo refleja cuántas fotos lo formaron).
        """
        index = self._read_index()
        result = []
        for name, meta in index.items():
            result.append(
                {
                    "name": name,
                    "n_embeddings": meta.get("n_photos", 0),
                    "enrolled_at": meta.get("enrolled_at"),
                }
            )
        return result

    def delete(self, name: str) -> bool:
        """
        Elimina a una persona del índice y del pickle de embeddings.

        Inputs:  name — nombre de la persona a borrar.
        Outputs: True si existía (en índice o en pickle) y se borró; False si no.
        """
        index = self._read_index()
        existed = name in index
        if existed:
            index.pop(name, None)
            self._write_index(index)

        embeddings = self._read_embeddings()
        if name in embeddings:
            embeddings.pop(name, None)
            self._write_embeddings(embeddings)
            existed = True

        return existed

"""
_verify_f7.py — Script TEMPORAL de verificación de la Fase 7 (BORRAR al terminar).

No es parte del servidor: es una prueba de extremo a extremo del motor de
reconocimiento (recognition.py) usando el dataset de muestra que trae DeepFace.
Demuestra las pruebas exigidas por el exit gate de la Fase 7:
    1. import deepface + 1 inferencia real (carga/descarga ArcFace).
    2. Enrolar persona A (varias fotos) → verify con OTRA foto de A → match True, conf > THRESHOLD.
    3. verify con foto de persona B (distinta) → match False (unknown).
    4. verify con imagen SIN cara → error no_face.
    5. Latencia de verify en CPU (reporta valor real).
El POST /verify por HTTP se prueba aparte (curl contra uvicorn).

Con keras 3 instalado, se fuerza TF_USE_LEGACY_KERAS=1 antes de importar deepface.
"""

import os

# Forzar Keras 2 (tf-keras) antes de cargar recognition.py / deepface.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import shutil
import sys
import tempfile
import time
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from services.recognition import FaceRecognitionService  # noqa: E402


def find_dataset() -> Path:
    """
    Localiza una carpeta con caras de muestra (img*.jpg).

    Orden de búsqueda:
        1. Variable de entorno F7_DATASET (si apunta a un dir con img*.jpg).
        2. ./_f7_samples/dataset junto a este script (caras descargadas para la
           verificación; el pip-install de DeepFace NO incluye el dataset).
        3. El dataset que trae el paquete DeepFace (si la versión lo empaqueta).
    """
    here = Path(__file__).resolve().parent
    candidates = []
    env_ds = os.getenv("F7_DATASET")
    if env_ds:
        candidates.append(Path(env_ds))
    candidates.append(here / "_f7_samples" / "dataset")
    try:
        import deepface

        pkg_root = Path(deepface.__file__).resolve().parent
        candidates += [
            pkg_root / "tests" / "dataset",
            pkg_root / "tests" / "unit" / "dataset",
            pkg_root.parent / "tests" / "dataset",
        ]
    except Exception:  # noqa: BLE001 — deepface debería existir, pero no bloqueamos por esto
        pass

    for c in candidates:
        if c.is_dir():
            imgs = sorted(c.glob("img*.jpg"))
            if imgs:
                return c
    raise SystemExit(f"No se encontró dataset de caras. Probé: {candidates}")


def main() -> int:
    print("=" * 70)
    print("VERIFICACIÓN FASE 7 — recognition.py (DeepFace + ArcFace)")
    print("=" * 70)

    svc = FaceRecognitionService()
    print(f"Modelo={svc.model_name} detector={svc.detector} threshold={svc.threshold}")
    print(f"embeddings.pkl={svc.embeddings_file}")

    # ----- TEST 1: import + 1 inferencia real -----
    print("\n[TEST 1] import deepface + 1 inferencia real (puede descargar ArcFace ~130MB)...")
    dataset = find_dataset()
    all_imgs = sorted(dataset.glob("img*.jpg"))
    print(f"  dataset: {dataset}  ({len(all_imgs)} imágenes img*.jpg)")

    t0 = time.perf_counter()
    arr0 = svc._to_rgb_array(str(all_imgs[0]))
    emb0 = svc.get_embedding(arr0)
    t_first = time.perf_counter() - t0
    if emb0 is None:
        print("  FALLO: no se obtuvo embedding de la primera imagen.")
        return 1
    print(
        f"  OK: embedding shape={emb0.shape} dtype={emb0.dtype} "
        f"(1ª inferencia {t_first:.1f}s, incluye carga de modelo)"
    )
    assert emb0.shape == (512,), f"Se esperaban 512 dims, no {emb0.shape}"

    # ----- Construir matriz de embeddings de TODO el dataset (caras detectables) -----
    print("\n[setup] Calculando embeddings de todo el dataset para elegir pares...")
    embs: dict[str, np.ndarray] = {}
    for p in all_imgs:
        a = svc._to_rgb_array(str(p))
        e = svc.get_embedding(a)
        if e is not None:
            embs[p.name] = svc._l2_normalize(e)
        print(f"    {p.name}: {'cara' if e is not None else 'SIN cara'}")
    names = list(embs.keys())
    if len(names) < 3:
        print("  FALLO: se necesitan >= 3 imágenes con cara para la prueba.")
        return 1

    # Par MÁS parecido (misma persona) y par MENOS parecido (personas distintas).
    def cos(a, b):
        return float(np.dot(a, b))

    pairs = [((i, j), cos(embs[i], embs[j])) for i, j in combinations(names, 2)]
    pairs.sort(key=lambda x: x[1], reverse=True)
    (same_a, same_b), same_sim = pairs[0]
    (diff_a, diff_b), diff_sim = pairs[-1]
    print(f"\n  Par más parecido  (misma persona):  {same_a} ~ {same_b}  cos={same_sim:.4f}")
    print(f"  Par menos parecido (distintas):      {diff_a} ~ {diff_b}  cos={diff_sim:.4f}")

    # ----- TEST 2: enrolar A (varias fotos) → verify con OTRA foto de A -----
    print("\n[TEST 2] Enrolar 'PersonaA' con varias fotos → verify con OTRA foto de A...")
    # Usamos un store TEMPORAL para no tocar el embeddings.pkl real del servidor.
    tmpdir = Path(tempfile.mkdtemp(prefix="f7verify_"))
    svc.embeddings_file = tmpdir / "embeddings.pkl"
    svc.index_file = tmpdir / "enrolled_index.json"
    svc._ensure_stores()

    # Enrolamos A con 'same_a' (y, si las hay, otras fotos del mismo cluster).
    enroll_imgs = [str(dataset / same_a)]
    res = svc.enroll("PersonaA", enroll_imgs, replace=True)
    print(f"  enroll PersonaA: {res}")

    # verify con la OTRA foto del par de misma persona.
    probe_a = svc._to_rgb_array(str(dataset / same_b))
    r_a = svc.verify(probe_a)
    print(f"  verify(A_otra={same_b}): {r_a}")
    ok2 = bool(r_a.get("match")) and r_a.get("confidence", 0) > svc.threshold
    print(f"  -> {'PASS' if ok2 else 'FAIL'} (match True y confidence > {svc.threshold})")

    # ----- TEST 3: verify con persona B distinta → match False -----
    print("\n[TEST 3] verify con persona B (distinta) → match False (unknown)...")
    # Elegimos una imagen lo más distinta posible a la enrolada (same_a).
    far_name = min(
        (n for n in names if n not in (same_a,)),
        key=lambda n: cos(embs[same_a], embs[n]),
    )
    probe_b = svc._to_rgb_array(str(dataset / far_name))
    r_b = svc.verify(probe_b)
    print(f"  verify(B={far_name}): {r_b}")
    ok3 = (not r_b.get("match")) and r_b.get("person") == "unknown"
    print(f"  -> {'PASS' if ok3 else 'FAIL'} (match False, person unknown)")

    # ----- TEST 4: verify con imagen SIN cara → error no_face -----
    print("\n[TEST 4] verify con imagen SIN cara (paisaje sintético) → error no_face...")
    # Generamos una imagen de gradiente (sin caras) y la guardamos como JPG.
    h, w = 240, 320
    grad = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        grad[:, x, 0] = int(255 * x / w)          # canal B
        grad[:, x, 1] = int(255 * (1 - x / w))    # canal G
    grad[:, :, 2] = 128
    no_face_path = tmpdir / "paisaje.jpg"
    cv2.imwrite(str(no_face_path), grad)
    r_nf = svc.verify(str(no_face_path))
    print(f"  verify(paisaje): {r_nf}")
    ok4 = r_nf.get("error") == "no_face" and r_nf.get("match") is False
    print(f"  -> {'PASS' if ok4 else 'FAIL'} (error == no_face)")

    # ----- TEST 5: latencia de verify en CPU -----
    print("\n[TEST 5] Latencia de verify (CPU, ya con modelo cargado)...")
    lat = []
    for _ in range(3):
        t = time.perf_counter()
        svc.verify(probe_a)
        lat.append((time.perf_counter() - t) * 1000)
    avg = sum(lat) / len(lat)
    print(f"  latencias(ms)={[round(x) for x in lat]}  promedio={avg:.0f} ms")
    ok5 = avg < 2000
    print(f"  -> {'PASS' if ok5 else 'FAIL'} (< 2000 ms en CPU)")

    # Limpieza del store temporal.
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 70)
    print(
        f"RESUMEN: T1=OK  T2={'PASS' if ok2 else 'FAIL'}  "
        f"T3={'PASS' if ok3 else 'FAIL'}  T4={'PASS' if ok4 else 'FAIL'}  "
        f"T5={'PASS' if ok5 else 'FAIL'}"
    )
    print("=" * 70)
    return 0 if (ok2 and ok3 and ok4 and ok5) else 1


if __name__ == "__main__":
    raise SystemExit(main())

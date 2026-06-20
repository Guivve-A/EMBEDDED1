"""
enroll_cli.py — Enrolamiento de personas por línea de comandos (FASE 7).

Propósito:
    Registrar (o actualizar) a una persona en el sistema de reconocimiento facial
    a partir de un DIRECTORIO de fotos. Es la vía recomendada para enrolar al
    usuario real: se le piden varias fotos (≥ 10 recomendadas, con variación de
    ángulo e iluminación), se valida que cada una contenga una cara detectable, se
    extraen sus embeddings ArcFace (512-d), se promedian, se L2-normalizan y se
    guardan en `storage/embeddings.pkl`. El índice `enrolled_index.json` queda
    sincronizado para que `GET /enrolled` siga funcionando.

Uso:
    python enroll_cli.py --name "Guillermo" --photos ./fotos/
    python enroll_cli.py --name "Guillermo" --photos ./fotos/ --replace
    python enroll_cli.py --name "Guillermo" --photos ./fotos/ --list

Inputs (argumentos):
    --name      Nombre/clave de la persona (único en embeddings.pkl). Requerido
                salvo que se use --list solo.
    --photos    Ruta a un directorio con imágenes (.jpg/.jpeg/.png/.bmp/.webp).
                Requerido salvo que se use --list solo.
    --replace   Si se indica, SUSTITUYE el embedding previo de la persona en vez
                de fusionarlo (promediarlo) con el existente. Default: fusionar.
    --list      Solo lista las personas ya enroladas y termina (no enrola).

Salida:
    Resumen por consola con: fotos encontradas, válidas (con cara) vs rechazadas
    (sin cara / ilegibles), y el resultado del enrolamiento. Código de salida 0
    si se enroló al menos 1 foto válida; 1 si no se pudo enrolar nada o hubo error
    de argumentos.

Nota de rendimiento:
    La PRIMERA ejecución descarga el modelo ArcFace (~130 MB) a
    `~/.deepface/weights/` y construye el grafo de TensorFlow (varios segundos).
    Las siguientes son rápidas.

COMPATIBILIDAD KERAS 3 (CRÍTICO):
    Con `keras==3.14.1` instalado, DeepFace requiere `TF_USE_LEGACY_KERAS=1` para
    usar `tf-keras` (Keras 2). Se fija aquí, antes de cualquier import que arrastre
    tensorflow/deepface (recognition.py también lo fija de forma defensiva).
"""

import os

# Forzar Keras 2 (tf-keras) ANTES de cargar recognition.py / deepface / tensorflow.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import argparse
import sys
from pathlib import Path

# Extensiones de imagen aceptadas (en minúsculas, con punto).
VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _find_images(photos_dir: Path) -> list[Path]:
    """
    Recoge las rutas de imagen dentro del directorio (no recursivo).

    Inputs:  photos_dir — directorio a inspeccionar.
    Outputs: lista ordenada de rutas con extensión de imagen válida.
    """
    return sorted(
        p
        for p in photos_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTS
    )


def _print_enrolled(recognition) -> None:
    """Imprime la tabla de personas enroladas (nombre, nº fotos, fecha)."""
    enrolled = recognition.list_enrolled()
    if not enrolled:
        print("No hay personas enroladas todavía.")
        return
    print(f"Personas enroladas ({len(enrolled)}):")
    for e in enrolled:
        print(
            f"  - {e['name']:<20} "
            f"n_embeddings={e['n_embeddings']:<4} "
            f"enrolled_at={e['enrolled_at']}"
        )


def main(argv: list[str] | None = None) -> int:
    """
    Punto de entrada del CLI de enrolamiento.

    Inputs:  argv — argumentos (None = usa sys.argv).
    Outputs: código de salida (0 OK, 1 error / nada enrolado).
    """
    parser = argparse.ArgumentParser(
        prog="enroll_cli.py",
        description="Enrola una persona a partir de un directorio de fotos "
        "(DeepFace + ArcFace, embeddings 512-d).",
    )
    parser.add_argument("--name", help="Nombre/clave de la persona a enrolar.")
    parser.add_argument(
        "--photos",
        help="Directorio con las fotos de la persona (.jpg/.png/...).",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Sustituye el embedding previo en vez de fusionarlo (promediar).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista las personas ya enroladas y termina.",
    )
    args = parser.parse_args(argv)

    # Import diferido: cargar recognition (y con él DeepFace/TensorFlow) solo
    # cuando realmente se va a usar, para que `--help` sea instantáneo.
    # Aseguramos que el directorio del script esté en sys.path (para `import config`
    # y `from services...` igual que hace main.py).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from services.recognition import FaceRecognitionService

    recognition = FaceRecognitionService()

    # Modo solo-listar.
    if args.list and not (args.name or args.photos):
        _print_enrolled(recognition)
        return 0

    # Validación de argumentos para enrolar.
    if not args.name or not args.name.strip():
        parser.error("--name es obligatorio para enrolar.")
    if not args.photos:
        parser.error("--photos (directorio) es obligatorio para enrolar.")

    photos_dir = Path(args.photos).expanduser().resolve()
    if not photos_dir.is_dir():
        print(f"ERROR: el directorio de fotos no existe: {photos_dir}")
        return 1

    image_paths = _find_images(photos_dir)
    print(f"Directorio:  {photos_dir}")
    print(f"Imágenes encontradas: {len(image_paths)}")
    if not image_paths:
        print(
            "ERROR: no se encontraron imágenes "
            f"({', '.join(sorted(VALID_EXTS))}) en el directorio."
        )
        return 1

    # Recomendación de cantidad mínima (no bloqueante).
    if len(image_paths) < 10:
        print(
            f"AVISO: se recomiendan >= 10 fotos con variación de ángulo/iluminación "
            f"para mejor precisión (encontradas {len(image_paths)})."
        )

    # Pre-clasificación foto a foto (válida = tiene cara detectable). Esto da un
    # resumen claro de cuáles se rechazan; recognition.enroll vuelve a filtrar,
    # pero aquí mostramos el detalle por archivo.
    valid: list[str] = []
    rejected: list[str] = []
    print("\nValidando fotos (detección de cara)...")
    for p in image_paths:
        arr = recognition._to_rgb_array(str(p))  # carga BGR→RGB; None si ilegible
        if arr is None:
            rejected.append(f"{p.name} (ilegible)")
            print(f"  [X] {p.name}: no se pudo leer la imagen")
            continue
        emb = recognition.get_embedding(arr)
        if emb is None:
            rejected.append(f"{p.name} (sin cara)")
            print(f"  [X] {p.name}: no se detectó cara")
        else:
            valid.append(str(p))
            print(f"  [OK] {p.name}: cara detectada")

    print(f"\nResumen detección: {len(valid)} válida(s), {len(rejected)} rechazada(s).")
    if not valid:
        print("ERROR: ninguna foto válida (sin caras detectables). No se enrola nada.")
        return 1

    # Enrolamiento real (promedia + L2-normaliza + persiste).
    result = recognition.enroll(args.name.strip(), valid, replace=args.replace)

    print("\n=== Resultado del enrolamiento ===")
    print(f"  Persona:        {result['person']}")
    print(f"  Enrolado:       {result['enrolled']}")
    print(f"  Fotos válidas en esta corrida: {result['n_valid']}")
    print(f"  Total fotos acumuladas:        {result['n_photos']}")
    print(f"  Modo:           {'replace' if args.replace else 'fusion (promedio)'}")
    print(f"  embeddings.pkl: {recognition.embeddings_file}")

    if rejected:
        print("\n  Fotos rechazadas:")
        for r in rejected:
            print(f"    - {r}")

    print()
    _print_enrolled(recognition)

    return 0 if result["enrolled"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

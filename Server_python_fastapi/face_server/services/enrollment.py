"""
services/enrollment.py — Wrapper async sobre el servicio de reconocimiento.

Propósito:
    Exponer el enrolamiento (y consultas asociadas) de forma `async` para usarse
    cómodamente desde los endpoints FastAPI.

FASE 7: el enroll real hace inferencia pesada con DeepFace (extracción de
    embeddings ArcFace), que es CPU-bound y BLOQUEANTE. Para no congelar el event
    loop de FastAPI mientras se procesa, la llamada se delega a un thread con
    `anyio.to_thread.run_sync`. Así un /enroll lento no detiene al resto de
    requests (p. ej. el /verify del Arduino).
"""

import anyio

from services.recognition import FaceRecognitionService, ImageInput


class EnrollmentService:
    """Wrapper async de alto nivel para enrolar / consultar / borrar personas."""

    def __init__(self, recognition: FaceRecognitionService) -> None:
        """
        Inputs:
            recognition: instancia compartida de FaceRecognitionService
                         (inyectada para reutilizar el mismo store y modelo).
        """
        self._recognition = recognition

    async def enroll(
        self, name: str, image_paths: list[ImageInput], replace: bool = False
    ) -> dict:
        """
        Enrola una persona a partir de una o más fotos ya guardadas.

        La inferencia (bloqueante) se ejecuta en un thread para no bloquear el
        event loop.

        Inputs:
            name:        nombre de la persona.
            image_paths: rutas (str/Path) y/o np.ndarray con las fotos.
            replace:     True = reemplaza la galería de la persona con estas fotos
                         (re-aprender desde cero, atómico); False = añade muestras.
        Outputs:
            dict { enrolled, person, n_photos, n_valid } (ver recognition.enroll).
        """
        return await anyio.to_thread.run_sync(
            self._recognition.enroll, name, image_paths, replace
        )

    async def list_enrolled(self) -> list[dict]:
        """Devuelve la lista de personas enroladas (ver recognition.list_enrolled)."""
        return self._recognition.list_enrolled()

    async def delete(self, name: str) -> bool:
        """Borra una persona enrolada. Devuelve True si existía."""
        return self._recognition.delete(name)

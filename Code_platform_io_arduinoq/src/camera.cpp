// ============================================================================
//  camera.cpp  -  Implementacion de la camara OV7670
//  Ing 2 - Esqueleto (FASE 1). Inicializacion SCCB y captura de frame se
//          implementan en FASE 3 (sujeto al riesgo critico de DCMI del UNO Q).
// ============================================================================

#include "camera.h"
#include "config.h"

namespace camera {

// Bandera de inicializacion del modulo.
static bool s_ready = false;

bool init() {
  // TODO Fase 3: configurar pines OV7670_*, generar XCLK, resetear el sensor y
  //              escribir registros via SCCB (RGB565 + QVGA). Detectar PID/VER.
  s_ready = false;
  return s_ready;
}

bool captureFrame(uint8_t** buf, size_t* len) {
  // TODO Fase 3: esperar VSYNC, leer el frame (DCMI o bit-banging) a un buffer
  //              de CAM_FRAME_BYTES y devolver puntero + tamano. Timeout 500 ms.
  if (buf) *buf = nullptr;
  if (len) *len = 0;
  return false;
}

bool isReady() {
  return s_ready;
}

}  // namespace camera

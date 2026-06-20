// ============================================================================
//  camera.h  -  Captura de imagen con camara OV7670 (QVGA RGB565)
//  Ing 2 - Esqueleto creado en FASE 1 / implementacion en FASE 3
// ----------------------------------------------------------------------------
//  RIESGO CRITICO (ver PLAN_FASES.md F3): el OV7670 es de interfaz PARALELA
//  (D0-D7 + PCLK/HREF/VSYNC/XCLK + SCCB SIOD/SIOC + RESET/PWDN, ~16 GPIO).
//  El STM32U585 del UNO Q tiene DCMI (interfaz de camara nativa); hay que
//  confirmar que el core (Zephyr) del UNO Q la expone. Si no, habra que usar
//  HAL de STM32 o bit-banging. Por eso el pinmap real en config.h es tentativo.
//
//  Salida objetivo: 320x240, RGB565 (2 bytes/pixel) = 153.600 bytes por frame.
//  La conversion a JPEG (opcional) se evalua en F5; por defecto se manda raw.
// ============================================================================

#ifndef FACE_SECURITY_CAMERA_H
#define FACE_SECURITY_CAMERA_H

#include <Arduino.h>
#include <stddef.h>   // size_t

namespace camera {

// init
//  Proposito: configura los pines de la camara y la inicializa via SCCB/I2C
//             (formato RGB565, tamano QVGA, brillo/contraste por defecto).
//  Inputs:    ninguno (usa los pines OV7670_* de config.h).
//  Outputs:   true si la camara respondio y quedo configurada; false si fallo
//             (p.ej. no se detecto el sensor por SCCB).
bool init();

// captureFrame
//  Proposito: captura un frame completo QVGA RGB565 esperando VSYNC.
//  Inputs:    buf -> direccion de un puntero que recibira el buffer del frame
//                    (apunta a memoria gestionada por el modulo).
//             len -> direccion donde se escribe el tamano del frame en bytes.
//  Outputs:   true si la captura fue valida; false si hubo timeout (>500 ms)
//             u otro error. En false, *buf/*len quedan indefinidos.
//  Nota:      buffer esperado = CAM_FRAME_BYTES (153600). El UNO Q tiene SRAM
//             suficiente; en el fallback AVR este buffer NO cabe (la captura
//             real solo corre sobre el STM32U585 del UNO Q).
bool captureFrame(uint8_t** buf, size_t* len);

// isReady
//  Proposito: indica si la camara fue inicializada correctamente.
//  Inputs:    ninguno.   Outputs: true si lista, false si no.
bool isReady();

}  // namespace camera

#endif  // FACE_SECURITY_CAMERA_H

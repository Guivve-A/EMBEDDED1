// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  camera.h
// ----------------------------------------------------------------------------
// Inicializacion del OV2640 (pinout AI-Thinker, heredado del bring-up D1)
// y captura JPEG para el flujo de verificacion.
// ============================================================================
#pragma once

#include "esp_camera.h"

// Inicializa el sensor (PIXFORMAT_JPEG, SVGA con PSRAM / QVGA sin ella).
// Devuelve true si el sensor quedo operativo. Deja el flag de cameraOk().
bool initCamera();

// true si initCamera() tuvo exito (se reporta en el heartbeat como camera_ok).
bool cameraOk();

// Captura un JPEG fresco: descarta el primer frame del buffer (puede ser
// "rancio" por fb_count=2 + GRAB_LATEST) y devuelve el segundo.
// Devuelve nullptr si falla. El llamador DEBE liberar con esp_camera_fb_return().
camera_fb_t* captureJpeg();

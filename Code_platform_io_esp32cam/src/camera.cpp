// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  camera.cpp
// ----------------------------------------------------------------------------
// Reutiliza el pinout AI-Thinker y el initCamera() validados en el bring-up
// del Dia 1 (historico). Anade captureJpeg() con descarte del primer frame.
// ============================================================================
#include <Arduino.h>
#include "camera.h"
#include "config.h"

// ----- Pinout AI-Thinker ESP32-CAM (OV2640) — NO MODIFICAR ------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

static bool s_cameraOk = false;

// Traduccion del PID del sensor a nombre humano para logs.
static const char* sensorPidName(uint16_t pid) {
  switch (pid) {
    case OV9650_PID:  return "OV9650";
    case OV7725_PID:  return "OV7725";
    case OV2640_PID:  return "OV2640";
    case OV3660_PID:  return "OV3660";
    case OV5640_PID:  return "OV5640";
    case OV7670_PID:  return "OV7670";
    default:          return "DESCONOCIDO";
  }
}

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = psramFound() ? CAM_FRAMESIZE : FRAMESIZE_QVGA;
  config.jpeg_quality = CAM_JPEG_QUALITY;
  config.fb_count     = psramFound() ? 2 : 1;
  config.fb_location  = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] esp_camera_init() FALLO, codigo 0x%x\n", err);
    s_cameraOk = false;
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    Serial.println("[CAM] esp_camera_sensor_get() devolvio NULL");
    s_cameraOk = false;
    return false;
  }

  Serial.printf("[CAM] Sensor detectado: %s (PID=0x%04X)\n",
                sensorPidName(s->id.PID), s->id.PID);
  Serial.printf("[CAM] frame_size=%s  fb_count=%d  jpeg_quality=%d\n",
                psramFound() ? "SVGA(800x600)" : "QVGA(320x240)",
                config.fb_count, config.jpeg_quality);

  s_cameraOk = true;
  return true;
}

bool cameraOk() {
  return s_cameraOk;
}

camera_fb_t* captureJpeg() {
  if (!s_cameraOk) {
    Serial.println("[CAM] captureJpeg(): camara no inicializada");
    return nullptr;
  }

  // Descartar el primer frame: con fb_count=2 puede venir capturado ANTES
  // del flash/trigger (frame rancio del buffer circular).
  camera_fb_t* fb = esp_camera_fb_get();
  if (fb) {
    esp_camera_fb_return(fb);
  }

  fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] esp_camera_fb_get() FALLO (frame nulo)");
    return nullptr;
  }
  if (fb->format != PIXFORMAT_JPEG || fb->len == 0) {
    Serial.println("[CAM] Frame invalido (no JPEG o vacio)");
    esp_camera_fb_return(fb);
    return nullptr;
  }

  Serial.printf("[CAM] Captura OK: %ux%u  %u bytes\n",
                fb->width, fb->height, (unsigned)fb->len);
  return fb;
}

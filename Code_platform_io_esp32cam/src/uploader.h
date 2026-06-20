// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  uploader.h
// ----------------------------------------------------------------------------
// Subida HTTPS al servidor (Oracle Cloud, Nginx + FastAPI):
//   - verifyCapture(): flash -> captura -> POST multipart /verify -> JSON.
//   - sendHeartbeat(): POST /device/heartbeat cada HEARTBEAT_S.
// ============================================================================
#pragma once

// Resultado de la verificacion facial remota.
enum VerifyResult {
  VERIFY_MATCH,     // el servidor reconocio a una persona enrolada
  VERIFY_INTRUDER,  // el servidor NO reconocio la cara (o no hay cara)
  VERIFY_ERROR      // fallo de WiFi/HTTP/TLS/parseo (main lo trata fail-safe
                    // como intruso: mejor falsa alarma que brecha silenciosa)
};

// Flujo completo de verificacion. Enciende el flash, captura un JPEG y lo
// envia a https://SERVER_HOST/verify con X-API-Key. Timeout HTTP_TIMEOUT_MS
// y 1 reintento ante fallo de red/5xx.
VerifyResult verifyCapture();

// Heartbeat JSON {device_id, camera_ok, wifi_rssi, fw} a /device/heartbeat.
// Devuelve true si el servidor respondio 200.
bool sendHeartbeat();

// Polling del disparo (v2 sin cables): GET /capture-request -> {pending, ts}.
// Devuelve true si el servidor marca pending=true (hay que capturar+verificar).
// `outTs` recibe el ts del evento (para deduplicar). Ante cualquier fallo de
// red/HTTP/parseo devuelve false (el loop simplemente reintenta al siguiente poll).
bool pollCaptureRequest(uint32_t& outTs);

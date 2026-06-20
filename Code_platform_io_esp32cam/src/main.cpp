// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  main.cpp  (fw 2.0.0 - rol definitivo, v2 SIN CABLES)
// ----------------------------------------------------------------------------
// CAMARA CLIENTE del sistema de seguridad. SIN cables al UNO Q:
//
//   - DISPARO por POLLING: cada POLL_MS hace GET /capture-request al server.
//     Si {pending:true} -> flash -> captura OV2640 -> POST /verify (X-API-Key).
//   - RESULTADO: ya NO se devuelve por GPIO. El ESP32 solo captura y postea;
//     el UNO Q se entera del match/intruso por el propio servidor.
//   - El POST /verify apaga el pending en el server, asi el siguiente poll da
//     pending=false (ademas deduplicamos por `ts` ya atendido).
//
// Heartbeat a /device/heartbeat cada HEARTBEAT_S segundos.
//
// Host/port del server: leidos de NVS (editables desde el portal AP, sin
// re-flashear); fallback a SERVER_HOST/SERVER_PORT de config.h si NVS vacio.
//
// Configuracion WiFi: portal AP "FaceCam_Setup" (192.168.4.1) en el primer
// boot (o tras /reset); guarda 2 redes (+ host/port del server) en NVS y
// reinicia en modo STA. En modo portal NO se hace polling.
//
// NOTA: PIN_TRIGGER_IN / PIN_RESULT_MATCH / PIN_RESULT_INTRUDER quedan como
// historico (LEGACY v1) en config.h y NO se usan aqui.
// ============================================================================
#include <Arduino.h>
#include <WiFi.h>
#include "config.h"
#include "camera.h"
#include "wifi_portal.h"
#include "uploader.h"

// ----- Estado del loop -------------------------------------------------------
static uint32_t s_lastBeatMs   = 0;  // ultimo heartbeat
static uint32_t s_lastPollMs   = 0;  // ultimo GET /capture-request
static uint32_t s_lastHandledTs = 0; // ts del ultimo evento ya atendido (dedup)

// Maneja un disparo confirmado por el server: captura + verificacion.
// El resultado solo se registra por Serial (el server ya lo conoce via /verify).
// Devuelve true si el /verify se completo (match o intruso): el evento queda
// atendido. Devuelve false ante ERROR (sin WiFi/HTTP/parseo): NO se marca el ts
// como atendido para reintentar el mismo evento en el proximo poll.
static bool handleTrigger() {
  Serial.println("[POLL] capture-request pending=true -> verificando...");

  VerifyResult r = verifyCapture();
  switch (r) {
    case VERIFY_MATCH:
      Serial.println("[POLL] Resultado: MATCH (persona autorizada)");
      return true;
    case VERIFY_INTRUDER:
      Serial.println("[POLL] Resultado: INTRUSO");
      return true;
    case VERIFY_ERROR:
    default:
      // Sin GPIO de resultado: ante error solo se loguea. El /verify no llego
      // bien al server, asi que su pending podria seguir activo; reintentamos
      // en el proximo poll (no marcamos el ts como atendido).
      Serial.println("[POLL] Resultado: ERROR (se reintentara en el proximo poll)");
      return false;
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("================================================");
  Serial.println(" EMBEBIDOS_1 - ESP32-CAM  (camara cliente)");
  Serial.printf ("   fw=%s  build=%s %s\n", FW_VERSION, __DATE__, __TIME__);
  Serial.println("================================================");
  Serial.printf("[SYS] PSRAM: %s   Heap libre: %u\n",
                psramFound() ? "OK" : "AUSENTE", ESP.getFreeHeap());

  // --- Pines ---
  // v2 sin cables: solo se usa el LED flash para iluminar la captura.
  // Los pines LEGACY de trigger/result ya no se configuran.
  pinMode(PIN_FLASH_LED, OUTPUT);
  digitalWrite(PIN_FLASH_LED, LOW);

  // --- Camara ---
  if (!initCamera()) {
    Serial.println("[CAM] AVISO: camara NO operativa. El dispositivo sigue "
                   "arrancando para reportar camera_ok=false por heartbeat.");
    // No reiniciamos en bucle: el heartbeat avisara al servidor/app del fallo.
  }

  // --- WiFi: portal de configuracion o modo STA ---
  if (!portalHasCredentials()) {
    Serial.println("[WIFI] Sin credenciales en NVS -> modo portal AP");
    portalStart();
    return;  // en modo portal el loop no procesa triggers
  }

  Serial.println("[WIFI] Credenciales encontradas -> modo STA");
  if (!wifiConnectSta()) {
    Serial.println("[WIFI] Ninguna red respondio al boot; se reintentara en "
                   "el loop (y se reabrira el portal tras varios fallos).");
  }

  Serial.printf("[OK]  Operativo. Disparo=POLL %d ms  Heartbeat=%d s\n",
                POLL_MS, HEARTBEAT_S);
  Serial.printf("[OK]  Servidor: %s:%u  (TLS=%d)\n",
                portalServerHost().c_str(), portalServerPort(), USE_TLS);
  Serial.println("================================================");
}

void loop() {
  // En modo portal solo atiende el formulario (AsyncWebServer es asincrono;
  // no hay nada que hacer aqui salvo esperar el /save -> reboot).
  if (portalActive()) {
    delay(50);
    return;
  }

  const uint32_t now = millis();

  // 1) Mantenimiento WiFi (reconexion; puede degradar a portal).
  if (wifiMaintain()) {
    return;  // paso a modo portal
  }

  // 2) Polling del disparo (no bloqueante por millis): cada POLL_MS pregunta
  //    al server GET /capture-request. Si hay un evento pendiente NUEVO (ts
  //    distinto al ya atendido) -> captura + POST /verify. El /verify apaga el
  //    pending en el server; ademas deduplicamos por ts. Un fallo de red no
  //    rompe el loop: pollCaptureRequest() devuelve false y se reintenta luego.
  if (now - s_lastPollMs >= (uint32_t)POLL_MS) {
    s_lastPollMs = now;
    uint32_t ts = 0;
    if (pollCaptureRequest(ts)) {
      if (ts != 0 && ts == s_lastHandledTs) {
        // Mismo evento ya atendido con exito: ignorar (evita recapturar).
        Serial.printf("[POLL] pending=true pero ts=%lu ya atendido; ignorado\n",
                      (unsigned long)ts);
      } else if (handleTrigger()) {
        s_lastHandledTs = ts;  // marcar atendido solo si /verify se completo
      }
    }
  }

  // 3) Heartbeat periodico (no bloqueante por millis; el POST en si tiene
  //    timeout corto HEARTBEAT_TIMEOUT_MS).
  if (now - s_lastBeatMs >= (uint32_t)HEARTBEAT_S * 1000UL) {
    s_lastBeatMs = now;
    bool ok = sendHeartbeat();
    Serial.printf("[BEAT] heartbeat %s  rssi=%d  camera_ok=%s  heap=%u\n",
                  ok ? "OK" : "FALLO", WiFi.RSSI(),
                  cameraOk() ? "true" : "false", ESP.getFreeHeap());
  }

  delay(10);
}

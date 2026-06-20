// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  uploader.cpp
// ----------------------------------------------------------------------------
// TLS: WiFiClientSecure ancla la raiz ISRG Root X1 (Let's Encrypt) embebida
// en ca_cert.h. Con TLS_INSECURE=1 se usa setInsecure() (solo depuracion).
//
// Contrato verificado contra Server_python_fastapi/face_server/main.py:
//   POST /verify           multipart campo "file" -> {match, person,
//                          confidence, photo_id, latency_ms}
//   POST /device/heartbeat JSON {device_id, camera_ok, wifi_rssi, fw}
//                          -> {ok, device_id}
// Ambos protegidos por header X-API-Key.
// ============================================================================
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "uploader.h"
#include "camera.h"
#include "config.h"
#include "wifi_portal.h"   // portalServerHost()/portalServerPort() (NVS -> fallback config.h)

// El cliente y el esquema dependen de USE_TLS:
//   USE_TLS 1 -> WiFiClientSecure + https (cert ISRG Root X1 o setInsecure)
//   USE_TLS 0 -> WiFiClient plano + http (demo local contra la PC)
#if USE_TLS
  #include <WiFiClientSecure.h>
  #include "ca_cert.h"
  typedef WiFiClientSecure NetClient;
  static const bool HTTP_USE_TLS = true;
#else
  typedef WiFiClient NetClient;
  static const bool HTTP_USE_TLS = false;
#endif

static const char* MULTIPART_BOUNDARY = "----EmbebidosFaceCamBoundary7e1a";

// Configura el cliente TLS segun el flag de config.h (solo en modo nube).
static void setupClient(NetClient& client) {
#if USE_TLS
  #if TLS_INSECURE
    client.setInsecure();
  #else
    client.setCACert(ISRG_ROOT_X1_PEM);
  #endif
#else
  (void)client;  // modo local: WiFiClient plano, nada que configurar
#endif
}

// Envia el header X-API-Key solo si hay clave (en local va vacio y el server
// dev no la exige).
static inline void addApiKey(HTTPClient& http) {
  if (strlen(API_KEY) > 0) {
    http.addHeader("X-API-Key", API_KEY);
  }
}

// ----------------------------------------------------------------------------
// POST multipart del JPEG a /verify. Devuelve el codigo HTTP (o negativo si
// fallo de conexion) y deja la respuesta JSON en `response` si hubo 200.
// ----------------------------------------------------------------------------
static int postJpeg(camera_fb_t* fb, String& response) {
  // Cuerpo multipart: cabecera + JPEG + cierre, ensamblado en un solo buffer
  // contiguo (PSRAM si existe) porque HTTPClient::POST(buf,len) lo exige.
  String head;
  head.reserve(160);
  head += "--";
  head += MULTIPART_BOUNDARY;
  head += "\r\nContent-Disposition: form-data; name=\"file\"; "
          "filename=\"capture.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";

  String tail;
  tail.reserve(48);
  tail += "\r\n--";
  tail += MULTIPART_BOUNDARY;
  tail += "--\r\n";

  const size_t total = head.length() + fb->len + tail.length();
  uint8_t* body = psramFound()
                      ? (uint8_t*)ps_malloc(total)
                      : (uint8_t*)malloc(total);
  if (!body) {
    Serial.printf("[HTTP] Sin memoria para el cuerpo multipart (%u bytes)\n",
                  (unsigned)total);
    return -100;
  }
  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), fb->buf, fb->len);
  memcpy(body + head.length() + fb->len, tail.c_str(), tail.length());

  NetClient client;
  setupClient(client);

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);

  // Host/port efectivos: NVS si el portal los guardo, si no fallback config.h.
  const String host = portalServerHost();
  const uint16_t port = portalServerPort();

  int code = -101;
  if (http.begin(client, host.c_str(), port, "/verify", HTTP_USE_TLS)) {
    addApiKey(http);
    http.addHeader("Content-Type",
                   String("multipart/form-data; boundary=") + MULTIPART_BOUNDARY);
    code = http.POST(body, total);
    if (code == 200) {
      response = http.getString();
    } else if (code > 0) {
      Serial.printf("[HTTP] /verify respondio %d: %s\n",
                    code, http.getString().c_str());
    } else {
      Serial.printf("[HTTP] /verify fallo de conexion: %s\n",
                    HTTPClient::errorToString(code).c_str());
    }
    http.end();
  } else {
    Serial.println("[HTTP] http.begin() FALLO (/verify)");
  }

  free(body);
  return code;
}

VerifyResult verifyCapture() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[VERIFY] Sin WiFi: no se puede verificar");
    return VERIFY_ERROR;
  }

  // Flash ON breve para iluminar la escena antes de capturar.
  digitalWrite(PIN_FLASH_LED, HIGH);
  delay(120);                      // estabilizar exposicion con luz del flash
  camera_fb_t* fb = captureJpeg();
  digitalWrite(PIN_FLASH_LED, LOW);

  if (!fb) {
    Serial.println("[VERIFY] Captura fallida");
    return VERIFY_ERROR;
  }

  // POST con 1 reintento ante fallo de conexion o error 5xx del servidor.
  // 4xx (p. ej. 401 API key incorrecta) NO se reintenta: es error de config.
  String response;
  int code = postJpeg(fb, response);
  if (code != 200 && (code < 0 || code >= 500)) {
    Serial.println("[VERIFY] Reintentando POST /verify...");
    response = "";
    code = postJpeg(fb, response);
  }
  esp_camera_fb_return(fb);

  if (code != 200) {
    Serial.printf("[VERIFY] Fallo definitivo (HTTP %d)\n", code);
    return VERIFY_ERROR;
  }

  // Parseo del JSON {match, person, confidence, photo_id, latency_ms}.
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, response);
  if (err) {
    Serial.printf("[VERIFY] JSON invalido: %s\n", err.c_str());
    return VERIFY_ERROR;
  }

  const bool  match      = doc["match"] | false;
  const char* person     = doc["person"] | "unknown";
  const float confidence = doc["confidence"] | 0.0f;
  const char* photoId    = doc["photo_id"] | "";

  Serial.printf("[VERIFY] match=%s  person=%s  conf=%.3f  photo=%s\n",
                match ? "SI" : "NO", person, confidence, photoId);

  return match ? VERIFY_MATCH : VERIFY_INTRUDER;
}

// ----------------------------------------------------------------------------
// Heartbeat
// ----------------------------------------------------------------------------
bool sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["camera_ok"] = cameraOk();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["fw"]        = FW_VERSION;
  String payload;
  serializeJson(doc, payload);

  NetClient client;
  setupClient(client);

  HTTPClient http;
  // Timeout mas corto que el de /verify: el heartbeat no debe retener el
  // loop demasiado (un latido perdido no es critico).
  http.setTimeout(HEARTBEAT_TIMEOUT_MS);
  http.setConnectTimeout(HEARTBEAT_TIMEOUT_MS);

  const String host = portalServerHost();
  const uint16_t port = portalServerPort();

  bool ok = false;
  if (http.begin(client, host.c_str(), port, "/device/heartbeat", HTTP_USE_TLS)) {
    addApiKey(http);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(payload);
    ok = (code == 200);
    if (!ok) {
      Serial.printf("[BEAT] /device/heartbeat HTTP %d\n", code);
    }
    http.end();
  }
  return ok;
}

// ----------------------------------------------------------------------------
// Polling del disparo (v2 sin cables): GET /capture-request -> {pending, ts}.
// Reusa el mismo cliente/esquema (http/https) que /verify y /heartbeat.
// Cualquier fallo (sin WiFi, conexion, HTTP != 200, JSON invalido) -> false:
// el loop simplemente reintenta al siguiente poll, sin romperse.
// ----------------------------------------------------------------------------
bool pollCaptureRequest(uint32_t& outTs) {
  outTs = 0;
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  NetClient client;
  setupClient(client);

  HTTPClient http;
  // Timeout corto: el poll es frecuente y no debe retener el loop.
  http.setTimeout(POLL_TIMEOUT_MS);
  http.setConnectTimeout(POLL_TIMEOUT_MS);

  const String host = portalServerHost();
  const uint16_t port = portalServerPort();

  bool pending = false;
  if (http.begin(client, host.c_str(), port, "/capture-request", HTTP_USE_TLS)) {
    addApiKey(http);
    int code = http.GET();
    if (code == 200) {
      String body = http.getString();
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, body);
      if (!err) {
        pending = doc["pending"] | false;
        outTs   = doc["ts"] | 0UL;
      } else {
        Serial.printf("[POLL] JSON invalido: %s\n", err.c_str());
      }
    } else if (code > 0) {
      Serial.printf("[POLL] /capture-request HTTP %d\n", code);
    }
    // code < 0 (fallo de conexion) se silencia: es ruido en cada poll fallido.
    http.end();
  }
  return pending;
}

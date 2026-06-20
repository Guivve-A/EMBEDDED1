// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  wifi_portal.cpp
// ----------------------------------------------------------------------------
// Reutiliza el patron AP + AsyncWebServer del bring-up D1, ahora como portal
// de configuracion WiFi persistido en NVS (Preferences, namespace "facecam").
// ============================================================================
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <Preferences.h>
#include <time.h>
#include "wifi_portal.h"
#include "config.h"

static const IPAddress AP_IP  (192, 168, 4, 1);
static const IPAddress AP_GW  (192, 168, 4, 1);
static const IPAddress AP_MASK(255, 255, 255, 0);

// El servidor solo existe en modo portal (ahorra ~heap en operacion normal).
static AsyncWebServer* s_server   = nullptr;
static bool            s_portal   = false;
static uint8_t         s_failedCycles = 0;

// ----- NVS -------------------------------------------------------------------

bool portalHasCredentials() {
  Preferences prefs;
  prefs.begin("facecam", true);  // solo lectura
  String s1 = prefs.getString("ssid1", "");
  prefs.end();
  return s1.length() > 0;
}

void portalEraseCredentials() {
  Preferences prefs;
  prefs.begin("facecam", false);
  prefs.clear();
  prefs.end();
  Serial.println("[NVS] Credenciales WiFi borradas");
}

static void saveCredentials(const String& s1, const String& p1,
                            const String& s2, const String& p2,
                            const String& srvHost, uint16_t srvPort) {
  Preferences prefs;
  prefs.begin("facecam", false);
  prefs.putString("ssid1", s1);
  prefs.putString("pass1", p1);
  prefs.putString("ssid2", s2);
  prefs.putString("pass2", p2);
  // Config del servidor (opcional). Vacio -> uploader cae al fallback config.h.
  prefs.putString("srv_host", srvHost);
  prefs.putUShort("srv_port", srvPort);
  prefs.end();
  Serial.printf("[NVS] Guardadas redes: \"%s\" y \"%s\"\n",
                s1.c_str(), s2.length() ? s2.c_str() : "(ninguna)");
  Serial.printf("[NVS] Servidor: host=\"%s\"  port=%u  %s\n",
                srvHost.length() ? srvHost.c_str() : "(fallback config.h)",
                (unsigned)srvPort,
                srvHost.length() ? "" : "(usara SERVER_HOST/SERVER_PORT)");
}

// ----- Getters de la config del servidor (NVS -> fallback config.h) ----------

String portalServerHost() {
  Preferences prefs;
  prefs.begin("facecam", true);
  String h = prefs.getString("srv_host", "");
  prefs.end();
  if (h.length() == 0) {
    return String(SERVER_HOST);  // fallback config.h
  }
  return h;
}

uint16_t portalServerPort() {
  Preferences prefs;
  prefs.begin("facecam", true);
  uint16_t p = prefs.getUShort("srv_port", 0);
  prefs.end();
  if (p == 0) {
    return (uint16_t)SERVER_PORT;  // fallback config.h
  }
  return p;
}

static void loadCredentials(String& s1, String& p1, String& s2, String& p2) {
  Preferences prefs;
  prefs.begin("facecam", true);
  s1 = prefs.getString("ssid1", "");
  p1 = prefs.getString("pass1", "");
  s2 = prefs.getString("ssid2", "");
  p2 = prefs.getString("pass2", "");
  prefs.end();
}

// ----- HTML del portal (negro/oro, coherente con la identidad de la app) ----

static const char PORTAL_HTML[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceCam · Configuracion WiFi</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;background:#000;color:#F5F5F7;
    font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;
    display:flex;align-items:center;justify-content:center;padding:24px}
  .card{width:100%;max-width:380px}
  h1{color:#D4AF37;font-weight:300;font-size:1.6rem;letter-spacing:.06em;
    margin:0 0 4px}
  p.sub{color:#6E6E73;font-size:.8rem;margin:0 0 28px}
  label{display:block;color:#A1A1A6;font-size:.72rem;letter-spacing:.08em;
    text-transform:uppercase;margin:18px 0 6px}
  input{width:100%;padding:12px 14px;background:#111;border:1px solid #2a2a2e;
    border-radius:10px;color:#F5F5F7;font-size:.95rem;outline:none}
  input:focus{border-color:#D4AF37}
  .sep{border-top:1px solid #1c1c1e;margin:26px 0 8px;position:relative}
  .sep span{position:absolute;top:-9px;left:0;background:#000;padding-right:10px;
    color:#6E6E73;font-size:.7rem;letter-spacing:.1em}
  button{width:100%;margin-top:30px;padding:14px;background:#D4AF37;border:0;
    border-radius:10px;color:#000;font-size:.95rem;font-weight:600;
    letter-spacing:.04em;cursor:pointer}
  small{display:block;color:#6E6E73;margin-top:18px;font-size:.72rem;
    text-align:center}
</style></head><body><div class="card">
<h1>FaceCam</h1><p class="sub">Sistema de seguridad · Configuracion WiFi</p>
<form method="POST" action="/save">
  <div class="sep"><span>RED PRINCIPAL</span></div>
  <label for="ssid1">SSID</label>
  <input id="ssid1" name="ssid1" required maxlength="32" autocomplete="off">
  <label for="pass1">Contrasena</label>
  <input id="pass1" name="pass1" type="password" maxlength="64">
  <div class="sep"><span>RED DE RESPALDO (OPCIONAL)</span></div>
  <label for="ssid2">SSID</label>
  <input id="ssid2" name="ssid2" maxlength="32" autocomplete="off">
  <label for="pass2">Contrasena</label>
  <input id="pass2" name="pass2" type="password" maxlength="64">
  <div class="sep"><span>SERVIDOR (OPCIONAL)</span></div>
  <label for="srv_host">IP o host del servidor</label>
  <input id="srv_host" name="srv_host" maxlength="64" autocomplete="off"
         placeholder="192.168.100.23">
  <label for="srv_port">Puerto</label>
  <input id="srv_port" name="srv_port" type="number" min="1" max="65535"
         placeholder="8000">
  <button type="submit">Guardar y reiniciar</button>
</form>
<small>La camara se reiniciara y se conectara a tu red.</small>
</div></body></html>)HTML";

static const char SAVED_HTML[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceCam · Guardado</title>
<style>
  body{margin:0;min-height:100vh;background:#000;color:#F5F5F7;
    font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    text-align:center;padding:24px}
  h1{color:#D4AF37;font-weight:300;font-size:1.6rem;letter-spacing:.06em}
  p{color:#A1A1A6;font-size:.9rem;max-width:320px}
  .dot{width:8px;height:8px;background:#D4AF37;border-radius:50%;
    margin-top:24px;box-shadow:0 0 18px #D4AF37}
</style></head><body>
<h1>Configuracion guardada</h1>
<p>La camara se reinicia y se conectara a tu red WiFi. Ya puedes cerrar esta
pagina y desconectarte de FaceCam_Setup.</p>
<div class="dot"></div></body></html>)HTML";

// ----- Portal AP -------------------------------------------------------------

void portalStart() {
  s_portal = true;

  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GW, AP_MASK);
  bool ok = WiFi.softAP(AP_SSID, AP_PASS);
  Serial.printf("[PORTAL] AP %s  SSID=\"%s\"  IP=%s\n",
                ok ? "ACTIVO" : "FALLO", AP_SSID,
                WiFi.softAPIP().toString().c_str());

  if (!s_server) {
    s_server = new AsyncWebServer(80);
  }

  s_server->on("/", HTTP_GET, [](AsyncWebServerRequest* req) {
    req->send(200, "text/html; charset=utf-8", PORTAL_HTML);
  });

  s_server->on("/save", HTTP_POST, [](AsyncWebServerRequest* req) {
    String s1 = req->hasParam("ssid1", true) ? req->getParam("ssid1", true)->value() : "";
    String p1 = req->hasParam("pass1", true) ? req->getParam("pass1", true)->value() : "";
    String s2 = req->hasParam("ssid2", true) ? req->getParam("ssid2", true)->value() : "";
    String p2 = req->hasParam("pass2", true) ? req->getParam("pass2", true)->value() : "";
    String srvHost = req->hasParam("srv_host", true) ? req->getParam("srv_host", true)->value() : "";
    String srvPortStr = req->hasParam("srv_port", true) ? req->getParam("srv_port", true)->value() : "";
    s1.trim(); s2.trim(); srvHost.trim(); srvPortStr.trim();

    if (s1.length() == 0) {
      req->send(400, "text/plain", "ssid1 es obligatorio");
      return;
    }
    // Server opcional: si se deja vacio, el uploader cae al fallback config.h.
    // Puerto fuera de rango (o vacio/0) -> 0 -> el getter usara SERVER_PORT.
    long srvPortL = srvPortStr.toInt();
    uint16_t srvPort = (srvPortL >= 1 && srvPortL <= 65535) ? (uint16_t)srvPortL : 0;
    saveCredentials(s1, p1, s2, p2, srvHost, srvPort);
    req->send(200, "text/html; charset=utf-8", SAVED_HTML);

    Serial.println("[PORTAL] Credenciales guardadas. Reinicio en 1.5 s...");
    delay(1500);  // dar tiempo a entregar la respuesta HTTP
    ESP.restart();
  });

  s_server->on("/reset", HTTP_GET, [](AsyncWebServerRequest* req) {
    portalEraseCredentials();
    req->send(200, "text/plain", "Credenciales borradas. Reiniciando...");
    delay(1000);
    ESP.restart();
  });

  s_server->onNotFound([](AsyncWebServerRequest* req) {
    req->redirect("/");  // comportamiento tipo captive portal basico
  });

  s_server->begin();
  Serial.println("[PORTAL] Formulario en http://192.168.4.1");
}

bool portalActive() {
  return s_portal;
}

// ----- Modo STA --------------------------------------------------------------

// Intenta una sola red con timeout. Devuelve true si conecto.
static bool tryNetwork(const String& ssid, const String& pass) {
  if (ssid.length() == 0) return false;

  Serial.printf("[WIFI] Conectando a \"%s\" (timeout %d ms)...\n",
                ssid.c_str(), WIFI_TIMEOUT_MS);
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), pass.c_str());

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
    delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Conectado: IP=%s  RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
  }
  Serial.printf("[WIFI] \"%s\" no respondio\n", ssid.c_str());
  return false;
}

// Sincroniza la hora por NTP: imprescindible para validar el certificado TLS
// (el RTC arranca en 1970 y mbedTLS rechazaria el cert como "aun no valido").
static void syncNtp() {
#if !USE_TLS
  // Modo local (HTTP plano): no hay validacion de cert, NTP no es necesario.
  Serial.println("[NTP] Omitido (USE_TLS=0, modo local HTTP)");
#elif TLS_INSECURE
  Serial.println("[NTP] Omitido (TLS_INSECURE=1)");
#else
  configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);
  Serial.print("[NTP] Sincronizando hora");
  uint32_t t0 = millis();
  time_t now = time(nullptr);
  while (now < 1700000000 && millis() - t0 < NTP_SYNC_TIMEOUT_MS) {
    delay(250);
    Serial.print(".");
    now = time(nullptr);
  }
  Serial.println();
  if (now >= 1700000000) {
    struct tm tmInfo;
    gmtime_r(&now, &tmInfo);
    Serial.printf("[NTP] Hora UTC: %04d-%02d-%02d %02d:%02d:%02d\n",
                  tmInfo.tm_year + 1900, tmInfo.tm_mon + 1, tmInfo.tm_mday,
                  tmInfo.tm_hour, tmInfo.tm_min, tmInfo.tm_sec);
  } else {
    Serial.println("[NTP] AVISO: sin hora valida; la validacion TLS fallara. "
                   "Revisa salida a internet o usa TLS_INSECURE=1.");
  }
#endif
}

bool wifiConnectSta() {
  String s1, p1, s2, p2;
  loadCredentials(s1, p1, s2, p2);

  if (tryNetwork(s1, p1) || tryNetwork(s2, p2)) {
    s_failedCycles = 0;
    syncNtp();
    return true;
  }
  return false;
}

bool wifiMaintain() {
  if (s_portal) return true;                       // ya en portal
  if (WiFi.status() == WL_CONNECTED) {
    s_failedCycles = 0;
    return false;
  }

  Serial.println("[WIFI] Conexion perdida. Reintentando ciclo red1/red2...");
  if (wifiConnectSta()) {
    return false;
  }

  s_failedCycles++;
  Serial.printf("[WIFI] Ciclo fallido %u/%u\n", s_failedCycles, WIFI_RETRY_CYCLES);

  if (s_failedCycles >= WIFI_RETRY_CYCLES) {
    Serial.println("[WIFI] Demasiados fallos: reabriendo portal AP "
                   "(las credenciales NVS se conservan)");
    portalStart();
    return true;
  }
  return false;
}

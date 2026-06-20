// ============================================================================
//  wifi_manager.cpp  -  Implementacion de WiFi (AP + cliente) + EEPROM
//  Ing 2 - Esqueleto (FASE 1). EEPROM + portal AP se implementan en FASE 4;
//          conexion cliente + reconexion en FASE 5.
//
//  NOTA: este esqueleto NO incluye <WiFi.h>/<EEPROM.h> todavia, para que el
//  proyecto compile en el env de validacion `uno` (ATmega328P), que no tiene
//  stack WiFi. La inclusion del header WiFi real del UNO Q se hara en F4/F5,
//  posiblemente bajo guardas de plataforma.
// ============================================================================

#include "wifi_manager.h"
#include "config.h"

namespace wifi_manager {

// Bandera de conexion en modo cliente.
static bool s_connected = false;

void init() {
  // TODO Fase 4: EEPROM.begin(...) (o Preferences) + preparar stack WiFi.
}

bool hasStoredCredentials() {
  // TODO Fase 4: leer magic byte + verificar CRC8 del bloque en EEPROM.
  return false;
}

bool loadCredentials(Credentials& out) {
  // TODO Fase 4: copiar las 2 redes desde EEPROM a `out` y validar CRC.
  (void)out;
  return false;
}

bool saveCredentials(const char* ssid1, const char* pass1,
                     const char* ssid2, const char* pass2) {
  // TODO Fase 4: escribir magic + 2 redes + CRC8 en EEPROM.
  (void)ssid1; (void)pass1; (void)ssid2; (void)pass2;
  return false;
}

void eraseCredentials() {
  // TODO Fase 4: invalidar el magic byte / limpiar el bloque en EEPROM.
}

bool startAP() {
  // TODO Fase 4: WiFi.softAPConfig(192.168.4.1...) + softAP(AP_SSID, AP_PASS)
  //              + arrancar el servidor HTTP del portal en :80.
  return false;
}

void stopAP() {
  // TODO Fase 4: detener portal y apagar el AP.
}

ConnResult connect() {
  // TODO Fase 5: intentar primaria (WIFI_TIMEOUT_MS) y luego respaldo.
  s_connected = false;
  return ConnResult::FAILED;
}

void loop() {
  // TODO Fase 5: watchdog de conexion + reconexion automatica no bloqueante.
}

bool isConnected() {
  return s_connected;
}

String localIP() {
  // TODO Fase 5: return WiFi.localIP().toString();
  return String("0.0.0.0");
}

}  // namespace wifi_manager

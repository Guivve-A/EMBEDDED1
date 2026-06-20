// ============================================================================
// EMBEBIDOS_1 - ESP32-CAM  ·  wifi_portal.h
// ----------------------------------------------------------------------------
// Gestion WiFi de doble modo:
//   - PORTAL: sin credenciales en NVS -> AP "FaceCam_Setup" (192.168.4.1) con
//     formulario para guardar 2 redes (Preferences/NVS). Tras guardar: reinicio.
//   - STA: con credenciales -> intenta red1 (8 s) -> red2 (8 s); tras
//     WIFI_RETRY_CYCLES ciclos fallidos reabre el portal AP.
// ============================================================================
#pragma once

#include <Arduino.h>

// true si hay al menos una red guardada en NVS.
bool portalHasCredentials();

// Levanta AP + portal de configuracion (AsyncWebServer en :80).
// Bloquea conceptualmente el modo operativo: main no procesa triggers.
void portalStart();

// Borra las credenciales de NVS (tambien expuesto como GET /reset del portal).
void portalEraseCredentials();

// Intenta conectar en modo STA: red1 -> red2, WIFI_TIMEOUT_MS cada una.
// Devuelve true si quedo conectado. Tras conectar sincroniza NTP (TLS).
bool wifiConnectSta();

// Mantenimiento en loop(): si la conexion STA se cae, reintenta ciclos
// red1/red2; tras WIFI_RETRY_CYCLES fallidos consecutivos reabre el portal.
// Devuelve true si el dispositivo paso a modo portal (main debe dejar de
// procesar triggers hasta el reinicio).
bool wifiMaintain();

// true si esta en modo portal (AP activo, sin operacion normal).
bool portalActive();

// ----- Config del servidor persistida en NVS --------------------------------
// Host/port del servidor guardados desde el portal AP (claves "srv_host" /
// "srv_port" del namespace "facecam"). Si NVS esta vacio devuelven el fallback
// de config.h (SERVER_HOST / SERVER_PORT). Asi la IP del server se cambia desde
// el portal sin re-flashear.
String portalServerHost();
uint16_t portalServerPort();

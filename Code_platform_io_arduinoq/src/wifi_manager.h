// ============================================================================
//  wifi_manager.h  -  WiFi (AP de setup + cliente) + credenciales en EEPROM
//  Ing 2 - Esqueleto creado en FASE 1 / implementacion en FASE 4 y FASE 5
// ----------------------------------------------------------------------------
//  Responsable de:
//    - Persistir 2 pares (SSID, pass) en EEPROM con validacion (magic + CRC8).
//    - Modo AP (Fase 4): levantar "FaceSecurity_Setup" en 192.168.4.1 con un
//      portal web para que el usuario ingrese sus redes; luego reiniciar.
//    - Modo Cliente (Fase 5): conectar a la red primaria; si falla, a la de
//      respaldo; reconexion automatica no bloqueante.
//
//  Flujo de boot previsto: si hasStoredCredentials() -> modo Cliente; si no,
//  startAP() para configuracion inicial.
// ============================================================================

#ifndef FACE_SECURITY_WIFI_MANAGER_H
#define FACE_SECURITY_WIFI_MANAGER_H

#include <Arduino.h>

namespace wifi_manager {

// Resultado de un intento de conexion en modo cliente.
enum class ConnResult : uint8_t {
  CONNECTED_PRIMARY,   // conecto con la red primaria
  CONNECTED_BACKUP,    // conecto con la red de respaldo
  FAILED               // ninguna red disponible / timeout
};

// Estructura con las 2 redes guardadas. Se llena con loadCredentials().
struct Credentials {
  char ssidPrimary[33];   // SSID WiFi: hasta 32 chars + '\0'
  char passPrimary[64];   // password: hasta 63 chars + '\0'
  char ssidBackup[33];
  char passBackup[64];
};

// init
//  Proposito: inicializa el subsistema (EEPROM/Preferences y stack WiFi).
//             NO conecta ni levanta AP por si mismo.
//  Inputs:    ninguno.   Outputs: ninguno.
void init();

// --- Persistencia en EEPROM ----------------------------------------------

// hasStoredCredentials
//  Proposito: indica si hay credenciales validas en EEPROM (magic byte + CRC8 ok).
//  Inputs:    ninguno.
//  Outputs:   true si hay configuracion valida; false si EEPROM vacia/corrupta.
bool hasStoredCredentials();

// loadCredentials
//  Proposito: lee las 2 redes desde EEPROM hacia `out`.
//  Inputs:    out -> referencia a una Credentials que se rellenara.
//  Outputs:   true si la lectura fue valida (CRC ok); false en caso contrario.
bool loadCredentials(Credentials& out);

// saveCredentials
//  Proposito: graba las 2 redes en EEPROM con magic byte + CRC8.
//  Inputs:    ssid1/pass1 -> red primaria; ssid2/pass2 -> red de respaldo.
//  Outputs:   true si se escribio correctamente; false si fallo la escritura.
bool saveCredentials(const char* ssid1, const char* pass1,
                     const char* ssid2, const char* pass2);

// eraseCredentials
//  Proposito: borra/invalida las credenciales en EEPROM (reset de fabrica).
//             Tras llamar a esto y reiniciar, el sistema vuelve a modo AP.
//  Inputs:    ninguno.   Outputs: ninguno.
void eraseCredentials();

// --- Modo AP (configuracion inicial, Fase 4) -----------------------------

// startAP
//  Proposito: levanta el Access Point de setup (AP_SSID/AP_PASS, 192.168.4.1)
//             y arranca el portal web embebido.
//  Inputs:    ninguno (usa AP_SSID/AP_PASS de config.h).
//  Outputs:   true si el AP quedo activo; false si fallo.
bool startAP();

// stopAP
//  Proposito: apaga el Access Point y detiene el portal web.
//  Inputs:    ninguno.   Outputs: ninguno.
void stopAP();

// --- Modo Cliente (operacion, Fase 5) ------------------------------------

// connect
//  Proposito: intenta conectar a la red primaria (timeout WIFI_TIMEOUT_MS) y,
//             si falla, a la de respaldo.
//  Inputs:    ninguno (usa las credenciales cargadas de EEPROM).
//  Outputs:   ConnResult indicando con que red conecto o si fallo.
ConnResult connect();

// loop
//  Proposito: mantenimiento no bloqueante de la conexion (watchdog y
//             reconexion automatica). Se llama en cada iteracion del loop.
//  Inputs:    ninguno.   Outputs: ninguno.
void loop();

// isConnected
//  Proposito: indica si hay conexion WiFi activa en modo cliente.
//  Inputs:    ninguno.   Outputs: true si conectado, false si no.
bool isConnected();

// localIP
//  Proposito: devuelve la IP asignada como texto (o "0.0.0.0" si no hay).
//  Inputs:    ninguno.   Outputs: String con la IP local.
String localIP();

}  // namespace wifi_manager

#endif  // FACE_SECURITY_WIFI_MANAGER_H

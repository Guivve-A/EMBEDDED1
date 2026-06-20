// ============================================================================
//  config.h  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)  -  FASE 5 (v3)
//  Ing 2 (firmware embedded)
// ----------------------------------------------------------------------------
//  Punto unico de configuracion del SKETCH del MCU. Modelo DEFINITIVO (sin
//  cables a la ESP32): la coordinacion con el servidor de reconocimiento se
//  hace por el LADO LINUX (cloud_bridge.py). El MCU solo maneja:
//
//    - Sensor del haz: LDR DIGITAL en D2 (divisor pull-down externo). Con el
//      haz incidiendo, D2 lee HIGH (normal); al cortarse el haz cae a LOW
//      (intrusion). Logica POSITIVA, sin lectura analogica ni autocalibracion.
//    - Emisor laser KY-008 (D7), buzzer (D8), LEDs verde/rojo (D5/D6) y boton
//      de reset de configuracion WiFi (D3).
//
//  COORDINACION SIN CABLES:
//    - MCU -> Linux:  envia la linea  EVT:INTRUSION  por Serial/Monitor cuando
//                     confirma un corte del haz estando ARMED.
//    - Linux -> MCU:  envia  RES:MATCH / RES:INTRUDER  (resultado del servidor)
//                     y  ARM / DISARM  (sync con la app), por el mismo canal.
//
//  REPARTO (igual que F4): el WiFi/portal AP vive en el LADO LINUX
//  (NetworkManager + brick web_ui); el bridge al cloud (poll /state +
//  /last-result + heartbeat) tambien es python del lado Linux. Este sketch solo
//  maneja lo fisico y la maquina de estados de seguridad.
// ============================================================================
#ifndef FACE_SECURITY_CONFIG_H
#define FACE_SECURITY_CONFIG_H

// ----------------------------------------------------------------------------
//  Modo AP de setup (lo levanta el LADO LINUX, no el MCU). Documentacion.
// ----------------------------------------------------------------------------
#define AP_SSID               "FaceSecurity_Setup"  // SSID del portal de setup
#define AP_PASS               "setup1234"           // Password del AP (>= 8 chars)
#define AP_PORTAL_IP          "10.42.0.1"           // Gateway del AP (NM shared)
#define AP_PORTAL_PORT        7000                  // Puerto del brick web_ui

// ----------------------------------------------------------------------------
//  Sensor del haz: LDR DIGITAL en D2 (divisor pull-down externo)
// ----------------------------------------------------------------------------
// El haz del KY-008 incide sobre la LDR del divisor resistivo. Con el haz
// presente, D2 lee HIGH (normal); al cortarse el haz, D2 cae a LOW (intrusion).
// Lectura DIGITAL pura: no hay autocalibracion ni umbral analogico.
//
//    BEAM_OK_LEVEL  = HIGH  -> haz presente (normal)
//    intrusion      = LOW   (implicito: !BEAM_OK_LEVEL)
//
#define BEAM_OK_LEVEL         HIGH   // D2 HIGH = haz incidiendo = normal

// ----------------------------------------------------------------------------
//  Tiempos / timeouts (milisegundos)
// ----------------------------------------------------------------------------
#define DEBOUNCE_MS           200    // haz cortado >= 200 ms continuos = intrusion
#define RESULT_TIMEOUT_MS     15000  // sin RES: del servidor -> ALARM fail-safe
#define GREEN_OK_MS           3000   // LED verde fijo tras MATCH (legacy, ver GRACE_MS)
#define GRACE_MS              30000  // tras MATCH: verde fijo + ventana de gracia
                                     //   (NO re-verifica) antes de re-armar (30 s)
#define ARMED_BLINK_MS        500    // parpadeo 1 Hz del verde en ARMED (500 on/off)
#define ALARM_BLINK_MS        250    // parpadeo rapido del rojo en ALARM por timeout
#define BLINK_INTERVAL_MS     500    // blink "vivo" del LED onboard
#define HEARTBEAT_INTERVAL_MS 5000   // heartbeat de diagnostico por Serial
#define BTN_DEBOUNCE_MS       50     // antirrebote del boton de reset WiFi
#define RESET_HOLD_MS         3000   // mantener el boton para pedir reset WiFi

// ----------------------------------------------------------------------------
//  PINES - validados en HW para arduino:zephyr:unoq (forma UNO R3)
//  Tabla definitiva del usuario (sin cables a la ESP32):
//    D2 LDR(in) | D3 boton | D5 verde | D6 rojo | D7 laser | D8 buzzer | D13 onboard
// ----------------------------------------------------------------------------
#ifndef LED_BUILTIN
#define LED_BUILTIN           13
#endif
#define PIN_LED_ONBOARD       LED_BUILTIN

// Sensor laser: emisor KY-008 + LDR en divisor resistivo (lectura digital).
#define PIN_LASER_EMITTER     7      // salida digital -> enciende el laser KY-008
#define PIN_LDR               2      // entrada DIGITAL (regular, sin pull-up) <- divisor
#define LASER_EMITTER_ON_LEVEL HIGH  // KY-008: HIGH enciende el diodo

// Buzzer activo.
#define PIN_BUZZER            8      // salida digital -> buzzer
#define BUZZER_ON_LEVEL       HIGH   // activo-alto tipico

// LEDs de estado.
#define PIN_LED_GREEN         5      // LED verde (+R 220R a GND)
#define PIN_LED_RED           6      // LED rojo  (+R 220R a GND)

// Boton fisico de reset de configuracion WiFi (borra redes -> AP).
#define PIN_BUTTON_RESET      3      // INPUT_PULLUP, otro extremo a GND
#define BUTTON_PRESSED_LEVEL  LOW

#endif  // FACE_SECURITY_CONFIG_H

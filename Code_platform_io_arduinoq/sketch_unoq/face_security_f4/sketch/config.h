// ============================================================================
//  config.h  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)  -  FASE 4
//  Ing 2 (firmware embedded)
// ----------------------------------------------------------------------------
//  Punto unico de configuracion del SKETCH del MCU. Espejo del config.h del
//  proyecto PlatformIO, recortado a lo que el sketch F4 usa + el AP.
//
//  REPARTO DE RESPONSABILIDADES EN EL UNO Q (hallazgo de F4):
//    - El WiFi (AP de setup, 2 redes, conmutar a cliente) NO lo maneja este
//      sketch: lo maneja el LADO LINUX (NetworkManager) via host/fs_wifi.sh y
//      el portal web (brick web_ui, python/main.py). En el UNO Q NO hay
//      libreria WiFi.h para el sketch del MCU.
//    - Este sketch coordina lo FISICO: LEDs de estado y el boton de reset.
//
//  Los valores del AP estan aqui SOLO como documentacion/coherencia con el
//  lado Linux (host/fs_wifi.sh los usa de verdad). El sketch no abre el AP.
// ============================================================================
#ifndef FACE_SECURITY_CONFIG_H
#define FACE_SECURITY_CONFIG_H

// ----------------------------------------------------------------------------
//  Modo AP de setup (lo levanta el LADO LINUX, no el MCU).
//  En NetworkManager modo 'shared' el gateway/portal es 10.42.0.1 (NO
//  192.168.4.1 como seria en un ESP32). Portal: http://10.42.0.1:7000
// ----------------------------------------------------------------------------
#define AP_SSID               "FaceSecurity_Setup"  // SSID del portal de setup
#define AP_PASS               "setup1234"           // Password del AP (>= 8 chars)
#define AP_PORTAL_IP          "10.42.0.1"           // Gateway del AP (NM shared)
#define AP_PORTAL_PORT        7000                  // Puerto del brick web_ui

// ----------------------------------------------------------------------------
//  Tiempos (ms)
// ----------------------------------------------------------------------------
#define BLINK_INTERVAL_MS     500    // blink "vivo" del LED onboard
#define HEARTBEAT_INTERVAL_MS 5000   // heartbeat por Serial
#define RESET_HOLD_MS         3000   // mantener el boton para pedir reset
#define DEBOUNCE_MS           50     // antirrebote del boton

// ----------------------------------------------------------------------------
//  PINES — validados en HW para arduino:zephyr:unoq (F1/F2 corrieron con
//  estos alias de pin). Forma UNO R3: D0..D13 + A0..A5.
// ----------------------------------------------------------------------------
#ifndef LED_BUILTIN
#define LED_BUILTIN           13
#endif
#define PIN_LED_ONBOARD       LED_BUILTIN

#define PIN_LED_GREEN         5      // LED verde  -> estado CLIENTE/autorizado
#define PIN_LED_RED           6      // LED rojo   -> estado AP/sin red
#define LED_ON_LEVEL          HIGH   // nivel que enciende los LEDs

// Boton fisico de reset de configuracion. INPUT_PULLUP: en reposo HIGH, al
// pulsar LOW. Mantener > RESET_HOLD_MS pide el reset (borra redes -> AP).
#define PIN_BUTTON_RESET      3      // D2/D3 soportan interrupciones en UNO
#define BUTTON_PRESSED_LEVEL  LOW

#endif  // FACE_SECURITY_CONFIG_H

// ============================================================================
//  face_security_f2.ino  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)
//  Ing 2 - FASE 2: maquina de estados laser + buzzer (respuesta local < 100 ms)
// ----------------------------------------------------------------------------
//  Version-sketch (para arduino-cli / App Lab del UNO Q) del firmware F2 que
//  vive en ../../src/main.cpp del proyecto PlatformIO. EQUIVALENTE en logica;
//  el proyecto PlatformIO queda INTACTO. Los modulos (laser_sensor, alerts,
//  config, camera, wifi_manager) se copian junto a este .ino para que el
//  compilador de sketch los tome.
//
//  DIFERENCIA CLAVE vs el main.cpp PlatformIO (descubierta en el bring-up):
//    En el UNO Q 'Serial' lo provee la libreria Arduino_RouterBridge y solo
//    sale al monitor cuando hay una App Lab corriendo. Por eso aqui:
//      - se incluye <Arduino_RouterBridge.h>
//      - en setup() se hace Bridge.begin() + Monitor.begin() (patron oficial)
//    Sin esto, ARM/DISARM/heartbeat no se ven por 'arduino-app-cli monitor'.
//
//  Que hace esta fase:
//    - laser::init() (enciende haz, estado DISARMED) + alerts::init() (todo OFF).
//    - Comandos por Serial @115200, una linea terminada en '\n': ARM | DISARM.
//    - laser::update() cada iteracion; si ARMED y haz cortado >= DEBOUNCE_MS,
//      buzzer ON inmediato e imprime: INTRUSION DETECTED t=<millis> ms.
//    - Blink de vida del LED onboard + heartbeat por Serial. Todo no bloqueante.
// ============================================================================

#include <Arduino.h>
#include <ctype.h>    // toupper()
#include <string.h>   // strcmp()

// Identidad del firmware. En PlatformIO llegan por build_flags (platformio.ini);
// en el sketch/App Lab se definen aqui con los MISMOS valores.
#ifndef PROJECT_NAME
#define PROJECT_NAME "EMBEBIDOS_1_FACE_SECURITY"
#endif
#ifndef FW_VERSION
#define FW_VERSION "0.3.0-f2"
#endif

// 'Serial' del UNO Q lo provee esta libreria (alias de Monitor via router).
#include <Arduino_RouterBridge.h>

#include "config.h"
#include "laser_sensor.h"
#include "alerts.h"
// camera/wifi_manager siguen como esqueletos; se integran en F3-F5.
#include "camera.h"
#include "wifi_manager.h"

// ---- Blink de vida del LED onboard (no bloqueante) -------------------------
static unsigned long s_lastBlinkMs = 0;
static bool s_ledState = false;

// ---- Heartbeat de diagnostico (no bloqueante) ------------------------------
static unsigned long s_lastHeartbeatMs = 0;

// ---- Buffer de comandos por Serial -----------------------------------------
static char s_cmdBuf[16];
static uint8_t s_cmdLen = 0;

// printArmState - imprime el estado actual del sistema por Serial.
static void printArmState() {
  Serial.print(F("STATE = "));
  Serial.println(laser::getState() == laser::State::ARMED ? F("ARMED")
                                                          : F("DISARMED"));
}

// handleCommand - interpreta una linea de comando ya recibida (sin '\n').
static void handleCommand(char* cmd) {
  for (char* p = cmd; *p; ++p) *p = (char)toupper((unsigned char)*p);

  if (strcmp(cmd, "ARM") == 0) {
    laser::arm();
    Serial.println(F("CMD ARM -> sistema ARMADO"));
    printArmState();
  } else if (strcmp(cmd, "DISARM") == 0) {
    laser::disarm();
    alerts::buzzerOff();          // silencio inmediato del buzzer
    Serial.println(F("CMD DISARM -> sistema DESARMADO, buzzer OFF"));
    printArmState();
  } else if (cmd[0] != '\0') {
    Serial.print(F("CMD desconocido: "));
    Serial.println(cmd);
  }
}

// pollSerialCommands - lee caracteres pendientes sin bloquear y despacha en '\n'.
static void pollSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      if (s_cmdLen > 0) {
        s_cmdBuf[s_cmdLen] = '\0';
        handleCommand(s_cmdBuf);
        s_cmdLen = 0;
      }
      continue;
    }

    if (s_cmdLen < (sizeof(s_cmdBuf) - 1)) {
      s_cmdBuf[s_cmdLen++] = c;
    } else {
      s_cmdLen = 0;   // linea demasiado larga -> reinicia
    }
  }
}

// heartbeat - linea periodica de estado cuando no hay eventos.
static void heartbeat(unsigned long now) {
  if (now - s_lastHeartbeatMs < HEARTBEAT_INTERVAL_MS) return;
  s_lastHeartbeatMs = now;

  Serial.print(F("[hb] t="));
  Serial.print(now);
  Serial.print(F(" ms | "));
  Serial.print(laser::getState() == laser::State::ARMED ? F("ARMED") : F("DISARMED"));
  Serial.print(F(" | beam="));
  Serial.println(laser::isBeamBroken() ? F("BROKEN") : F("OK"));
}

void setup() {
  // LED de vida.
  pinMode(PIN_LED_ONBOARD, OUTPUT);
  digitalWrite(PIN_LED_ONBOARD, LOW);

  // --- Serial del UNO Q via RouterBridge (patron oficial) ------------------
  Serial.begin(115200);
  if (!Bridge.begin()) {
    Serial.println(F("ERR: Bridge.begin() fallo"));
  }
  Monitor.begin(115200);
  // Espera ACOTADA a que el monitor se conecte (headless-friendly), parpadeando.
  unsigned long waitStart = millis();
  while (!Monitor && (millis() - waitStart) < 10000UL) {
    unsigned long now = millis();
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now;
      s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    delay(10);
  }

  // Subsistemas de la Fase 2.
  laser::init();     // enciende el haz, estado DISARMED
  alerts::init();    // buzzer + LEDs en OFF

  Serial.println(F("Boot OK - F2 (laser + buzzer)"));
  Serial.print(F("  proyecto = ")); Serial.println(F(PROJECT_NAME));
  Serial.print(F("  firmware = ")); Serial.println(F(FW_VERSION));
  Serial.print(F("  debounce = ")); Serial.print(DEBOUNCE_MS); Serial.println(F(" ms"));
  Serial.println(F("  comandos: ARM | DISARM  (terminar con Enter)"));
  printArmState();
}

void loop() {
  const unsigned long now = millis();

  // 1) Comandos por Serial (ARM / DISARM). No bloqueante.
  pollSerialCommands();

  // 2) Sensor laser: se evalua SIEMPRE para mantener el debounce coherente.
  if (laser::update()) {
    // --- Respuesta local critica: buzzer INMEDIATO (una escritura GPIO) ---
    alerts::buzzerOn();
    Serial.print(F("INTRUSION DETECTED t="));
    Serial.print(now);
    Serial.println(F(" ms"));
  }

  // 3) Actuadores temporizados no bloqueantes.
  alerts::update();

  // 4) Blink de vida del LED onboard, sin delay().
  if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
    s_lastBlinkMs = now;
    s_ledState = !s_ledState;
    digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
  }

  // 5) Heartbeat de diagnostico periodico.
  heartbeat(now);
}

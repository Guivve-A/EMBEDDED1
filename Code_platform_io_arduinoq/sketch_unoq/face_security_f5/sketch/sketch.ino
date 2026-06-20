// ============================================================================
//  sketch.ino  -  EMBEBIDOS_1 / face_security (Arduino UNO Q)  -  FASE 5 (v3)
//  Ing 2 (firmware embedded)  -  LDR digital D2 + coordinacion SIN cables
// ----------------------------------------------------------------------------
//  VERSION DEFINITIVA del firmware del UNO Q: SIN cables a la ESP32. La
//  coordinacion con el servidor de reconocimiento la hace el LADO LINUX
//  (cloud_bridge.py), no GPIOs. Integra:
//
//    - F2 (verificada en HW): debounce 200 ms + latch del sensor laser,
//      buzzer < 100 ms, parser serial. El sensor ahora es una LDR DIGITAL en
//      D2 (HIGH = haz presente, LOW = corte; ver laser_sensor.cpp).
//    - F4 (verificada en HW): boton de reset WiFi (D3, hold 3 s ->
//      'RESET_REQUEST' para que el lado Linux borre redes y vuelva al AP).
//    - NUEVO: coordinacion por Serial/Monitor con el lado Linux (sin cables).
//
//  MAQUINA DE ESTADOS:
//
//    DISARMED ──ARM──► ARMED (verde parpadeo 1 Hz)
//    ARMED: haz cortado >=200 ms ──► buzzer ON inmediato (LOCAL) +
//           enviar 'EVT:INTRUSION' al lado Linux ──► WAIT_RESULT
//    WAIT_RESULT (lee lineas del lado Linux):
//        'RES:MATCH'    -> buzzer OFF + verde FIJO 3 s -> vuelve a ARMED
//        'RES:INTRUDER' -> ALARM: rojo FIJO + buzzer continuos hasta DISARM
//        timeout 15 s sin RES -> ALARM fail-safe: rojo PARPADEANTE +
//                       buzzer continuos hasta DISARM (distinguible del intruso)
//    DISARM (serial o RPC) desde CUALQUIER estado: silencia todo -> DISARMED.
//
//  COORDINACION SIN CABLES:
//    - MCU -> Linux:  el MCU imprime 'EVT:INTRUSION' por Serial/Monitor; el
//                     cloud_bridge.py lo lee (lo reenvia al servidor: POST
//                     /intrusion).
//    - Linux -> MCU:  el cloud_bridge.py envia 'ARM'/'DISARM' (sync app) y
//                     'RES:MATCH'/'RES:INTRUDER' (resultado del servidor) por
//                     el mismo canal (RPC RouterBridge primario; parser serial
//                     fallback).
//
//  COMANDOS (Monitor de App Lab, una linea + Enter):
//      ARM | DISARM | STATUS | RES:MATCH | RES:INTRUDER
//
//  IMPORTANTE (UNO Q): 'Serial' lo provee Arduino_RouterBridge y solo llega al
//  monitor con una App Lab corriendo. Patron obligatorio (F2/F4):
//  Bridge.begin() + Monitor.begin().
// ============================================================================

#include <Arduino_RouterBridge.h>
#include <ctype.h>
#include <string.h>

#include "config.h"
#include "laser_sensor.h"
#include "alerts.h"

#ifndef PROJECT_NAME
#define PROJECT_NAME "EMBEBIDOS_1_FACE_SECURITY"
#endif
#ifndef FW_VERSION
#define FW_VERSION "5.1.0-f5"
#endif

// RPC del RouterBridge para el bridge cloud (python -> MCU). Si una version
// futura del core/libreria rompiera Bridge.provide, poner 0: el sistema sigue
// funcionando por el parser serial (fallback del lado python).
#define USE_BRIDGE_RPC 1

// ---- Maquina de estados del sistema -----------------------------------------
enum SysState : uint8_t {
  ST_DISARMED,        // todo off; solo monitoreo
  ST_ARMED,           // verde 1 Hz; el corte del haz dispara
  ST_WAIT_RESULT,     // buzzer ON; esperando RES:MATCH/RES:INTRUDER del Linux
  ST_ALARM_INTRUDER,  // rojo fijo + buzzer hasta DISARM
  ST_ALARM_TIMEOUT,   // rojo parpadeante + buzzer hasta DISARM (fail-safe)
  ST_GRACE            // tras MATCH: verde fijo + ventana de gracia (NO verifica)
};
static SysState s_sys = ST_DISARMED;

static unsigned long s_waitStartMs = 0;    // entrada a WAIT_RESULT (timeout 15 s)
static unsigned long s_greenOkUntil = 0;   // (legacy) ventana verde fijo tras MATCH
static unsigned long s_graceUntil = 0;     // fin de la ventana de gracia 30 s tras MATCH

// ---- Infra heredada (blink onboard, heartbeat, boton reset WiFi) ------------
static unsigned long s_lastBlinkMs = 0;
static bool          s_ledState = false;
static unsigned long s_lastHbMs = 0;

static int           s_btnStable = HIGH;
static int           s_btnLastRead = HIGH;
static unsigned long s_btnChangeMs = 0;
static unsigned long s_btnPressMs = 0;
static bool          s_resetLatched = false;

// Buffer de comandos por Serial (admite "RES:INTRUDER" -> 16 chars suficiente).
static char    s_cmd[20];
static uint8_t s_cmdLen = 0;

// ---- Helpers -----------------------------------------------------------------
static const __FlashStringHelper* stateName(SysState st) {
  switch (st) {
    case ST_DISARMED:       return F("DISARMED");
    case ST_ARMED:          return F("ARMED");
    case ST_WAIT_RESULT:    return F("WAIT_RESULT");
    case ST_ALARM_INTRUDER: return F("ALARM_INTRUDER");
    case ST_ALARM_TIMEOUT:  return F("ALARM_TIMEOUT");
    case ST_GRACE:          return F("GRACE");
  }
  return F("?");
}

static void printStatus() {
  Serial.print(F("STATE = "));     Serial.print(stateName(s_sys));
  Serial.print(F(" | beam="));
  Serial.println(laser::isBeamBroken() ? F("BROKEN") : F("OK"));
}

// ---- Resultado del servidor (llega del lado Linux) ---------------------------

// onResultMatch - persona autorizada: silencio + verde fijo 3 s -> ARMED.
// Acepta desde cualquier estado "activo": esperando resultado (WAIT_RESULT) o ya
// en alarma (INTRUDER/TIMEOUT). Asi, durante el loop "intruso hasta propietario",
// cuando por fin aparece el dueno el sistema sale de la alarma y vuelve a verde.
static void onResultMatch() {
  if (s_sys != ST_WAIT_RESULT && s_sys != ST_ALARM_INTRUDER &&
      s_sys != ST_ALARM_TIMEOUT) {
    Serial.println(F("[res] RES:MATCH fuera de contexto, ignorado"));
    return;
  }
  alerts::redOff();                      // apaga el rojo (venia de WAIT/ALARM)
  alerts::happyChime();                  // sonido "alegre" (no bloqueante)
  alerts::greenOn();                     // verde FIJO durante la gracia
  s_greenOkUntil = 0;
  s_graceUntil = millis() + GRACE_MS;    // ventana de gracia: NO re-verifica
  laser::disarm();                       // ignora el haz durante la gracia
  s_sys = ST_GRACE;
  Serial.print(F("RES:MATCH -> autorizado: chime + verde fijo, gracia "));
  Serial.print(GRACE_MS / 1000); Serial.println(F(" s (sin re-verificar)"));
}

// onResultIntruder - cara NO autorizada: rojo fijo + buzzer continuo y NO terminal:
// el servidor mantiene capture_pending, asi que el ESP32 sigue capturando y
// reanalizando; cada nuevo resultado intruso re-afirma la alarma. Se sale con un
// RES:MATCH (propietario) o con DISARM. Acepta desde WAIT_RESULT o ya en alarma.
static void onResultIntruder() {
  if (s_sys != ST_WAIT_RESULT && s_sys != ST_ALARM_INTRUDER &&
      s_sys != ST_ALARM_TIMEOUT) {
    Serial.println(F("[res] RES:INTRUDER fuera de contexto, ignorado"));
    return;
  }
  alerts::redOn();
  alerts::buzzerOn();
  s_sys = ST_ALARM_INTRUDER;
  Serial.println(F("RES:INTRUDER -> ALARMA (rojo + buzzer, re-capturando hasta propietario)"));
}

// ---- Acciones (compartidas por serial y RPC) ---------------------------------

// doArm - pasa a ARMED: verde parpadeo 1 Hz, sensores en alerta.
static void doArm() {
  laser::arm();
  alerts::clear();
  alerts::greenBlink(ARMED_BLINK_MS);
  s_sys = ST_ARMED;
  s_greenOkUntil = 0;
  Serial.println(F("CMD ARM -> sistema ARMADO"));
  printStatus();
}

// doDisarm - desde CUALQUIER estado: silencia todo y vuelve a DISARMED.
static void doDisarm() {
  laser::disarm();
  alerts::clear();              // buzzer OFF + LEDs OFF + patrones cancelados
  s_sys = ST_DISARMED;
  s_greenOkUntil = 0;
  Serial.println(F("CMD DISARM -> sistema DESARMADO, alarma silenciada"));
  printStatus();
}

// RPC wrappers (Bridge.provide espera funciones void(void)).
static void rpcResMatch()    { onResultMatch(); }
static void rpcResIntruder() { onResultIntruder(); }

// handleCommand - parser: ARM | DISARM | STATUS | RES:MATCH | RES:INTRUDER.
static void handleCommand(char* cmd) {
  for (char* p = cmd; *p; ++p) *p = (char)toupper((unsigned char)*p);

  if (strcmp(cmd, "ARM") == 0)               doArm();
  else if (strcmp(cmd, "DISARM") == 0)       doDisarm();
  else if (strcmp(cmd, "STATUS") == 0)       printStatus();
  else if (strcmp(cmd, "RES:MATCH") == 0)    onResultMatch();
  else if (strcmp(cmd, "RES:INTRUDER") == 0) onResultIntruder();
  else if (cmd[0] != '\0') {
    Serial.print(F("CMD desconocido: ")); Serial.println(cmd);
  }
}

static void pollSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (s_cmdLen > 0) { s_cmd[s_cmdLen] = '\0'; handleCommand(s_cmd); s_cmdLen = 0; }
      continue;
    }
    if (s_cmdLen < sizeof(s_cmd) - 1) s_cmd[s_cmdLen++] = c; else s_cmdLen = 0;
  }
}

// ---- Boton de reset WiFi (heredado de F4, verificado en HW) -------------------
static void updateResetButton(unsigned long now) {
  int raw = digitalRead(PIN_BUTTON_RESET);

  if (raw != s_btnLastRead) { s_btnLastRead = raw; s_btnChangeMs = now; }

  if ((now - s_btnChangeMs) >= BTN_DEBOUNCE_MS && raw != s_btnStable) {
    s_btnStable = raw;
    if (s_btnStable == BUTTON_PRESSED_LEVEL) {
      s_btnPressMs = now; s_resetLatched = false;
      Serial.println(F("[btn] reset presionado; manten 3 s para borrar redes WiFi"));
    } else {
      if (!s_resetLatched) Serial.println(F("[btn] liberado antes de 3 s; cancelado"));
    }
  }

  if (s_btnStable == BUTTON_PRESSED_LEVEL && !s_resetLatched) {
    if (now - s_lastBlinkMs >= 100UL) {       // feedback: blink rapido onboard
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    if ((now - s_btnPressMs) >= RESET_HOLD_MS) {
      s_resetLatched = true;
      Serial.println(F("RESET_REQUEST"));     // el lado Linux: fs_wifi.sh reset
    }
  }
}

// ---- Heartbeat de diagnostico --------------------------------------------------
static void heartbeat(unsigned long now) {
  if (now - s_lastHbMs < HEARTBEAT_INTERVAL_MS) return;
  s_lastHbMs = now;

  Serial.print(F("[hb] t="));        Serial.print(now);
  Serial.print(F(" ms | "));         Serial.print(stateName(s_sys));
  Serial.print(F(" | beam="));
  Serial.println(laser::isBeamBroken() ? F("BROKEN") : F("OK"));
}

// ============================================================================
void setup() {
  pinMode(PIN_LED_ONBOARD, OUTPUT);
  digitalWrite(PIN_LED_ONBOARD, LOW);

  // Boton de reset WiFi.
  pinMode(PIN_BUTTON_RESET, INPUT_PULLUP);

  // --- Serial del UNO Q via RouterBridge (patron oficial F2/F4) -------------
  Serial.begin(115200);
  if (!Bridge.begin()) {
    Serial.println(F("ERR: Bridge.begin() fallo"));
  }
  Monitor.begin(115200);
  unsigned long w = millis();
  while (!Monitor && (millis() - w) < 10000UL) {
    unsigned long now = millis();
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    delay(10);
  }

#if USE_BRIDGE_RPC
  // RPC python -> MCU para el bridge cloud (sin pasar por el Monitor).
  //  arm/disarm: sync con la app (GET /state). res_*: resultado del servidor.
  Bridge.provide("arm", doArm);
  Bridge.provide("disarm", doDisarm);
  Bridge.provide("res_match", rpcResMatch);
  Bridge.provide("res_intruder", rpcResIntruder);
#endif

  // Subsistemas. laser::init() NO bloquea (LDR digital, sin autocalibracion).
  alerts::init();
  laser::init();

  Serial.println(F("Boot OK - F5 v3 (LDR digital D2 + coordinacion sin cables)"));
  Serial.print(F("  proyecto = "));  Serial.println(F(PROJECT_NAME));
  Serial.print(F("  firmware = "));  Serial.println(F(FW_VERSION));
  Serial.println(F("  pines: LDR D2 (HIGH=haz ok) | laser D7 | buzzer D8 | verde D5 | rojo D6 | boton D3"));
  Serial.println(F("  coord: MCU->Linux 'EVT:INTRUSION' | Linux->MCU 'RES:MATCH'/'RES:INTRUDER' + ARM/DISARM"));
  Serial.println(F("  comandos: ARM | DISARM | STATUS | RES:MATCH | RES:INTRUDER  (terminar con Enter)"));
  printStatus();
}

// ============================================================================
void loop() {
  const unsigned long now = millis();

  // 1) Comandos/lineas por Serial (y RPC via RouterBridge, despachado por lib).
  pollSerial();

  // 2) Sensor laser/LDR: SIEMPRE se evalua (mantiene debounce coherente).
  const bool intrusion = laser::update();

  // 3) Maquina de estados.
  switch (s_sys) {
    case ST_ARMED:
      if (intrusion) {
        // Respuesta local critica: buzzer INMEDIATO (una escritura GPIO)...
        alerts::buzzerOn();
        // ...y aviso al lado Linux por el MISMO canal RPC que ya funciona en el
        // sentido inverso (App Lab arranca sketch+python, NO los scripts host):
        //   sketch Bridge.notify("intrusion")  ->  python Bridge.provide("intrusion").
        Bridge.notify("intrusion");
        // Traza de depuracion (y fallback opcional via watcher host, no requerido).
        Serial.println(F("EVT:INTRUSION"));
        s_sys = ST_WAIT_RESULT;
        s_waitStartMs = now;
        s_greenOkUntil = 0;
        alerts::greenOff();              // el verde 1 Hz no aplica en espera
        Serial.print(F("INTRUSION DETECTED t=")); Serial.print(now);
        Serial.println(F(" ms -> EVT:INTRUSION enviado, esperando RES (15 s)"));
      } else if (s_greenOkUntil != 0 && (long)(now - s_greenOkUntil) >= 0) {
        // Fin de la ventana "verde fijo 3 s" tras un MATCH: volver al 1 Hz.
        s_greenOkUntil = 0;
        alerts::greenBlink(ARMED_BLINK_MS);
      }
      break;

    case ST_WAIT_RESULT:
      // Los resultados llegan por RES:MATCH / RES:INTRUDER (serial o RPC) y los
      // manejan onResultMatch()/onResultIntruder(). Aqui solo el timeout.
      if ((now - s_waitStartMs) >= RESULT_TIMEOUT_MS) {
        // Fail-safe: sin resultado (Linux/WiFi/servidor caidos) = alarma, con
        // rojo PARPADEANTE para distinguirlo del intruso confirmado.
        alerts::redBlink(ALARM_BLINK_MS);
        alerts::buzzerOn();
        s_sys = ST_ALARM_TIMEOUT;
        Serial.println(F("RES TIMEOUT (15 s) -> ALARMA fail-safe (rojo parpadeante)"));
      }
      break;

    case ST_ALARM_INTRUDER:
    case ST_ALARM_TIMEOUT:
      // Se mantiene hasta DISARM (serial o RPC). Nada que hacer aqui.
      break;

    case ST_GRACE:
      // Ventana tras MATCH: verde fijo, haz ignorado, NO se re-verifica. Al
      // expirar la gracia, re-armar (verde 1 Hz) para la proxima intrusion.
      if ((long)(now - s_graceUntil) >= 0) {
        laser::arm();
        alerts::greenBlink(ARMED_BLINK_MS);
        s_sys = ST_ARMED;
        Serial.println(F("Gracia terminada -> re-ARMADO"));
      }
      break;

    case ST_DISARMED:
    default:
      break;
  }

  // 4) Actuadores temporizados no bloqueantes.
  alerts::update();
  updateResetButton(now);

  // 5) Blink "vivo" del LED onboard (salvo durante el hold del boton).
  if (!(s_btnStable == BUTTON_PRESSED_LEVEL && !s_resetLatched)) {
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
  }

  // 6) Heartbeat de diagnostico periodico.
  heartbeat(now);
}

// ============================================================================
//  laser_sensor.cpp  -  Haz laser sobre LDR DIGITAL en D2 (FASE 5 v3)
// ----------------------------------------------------------------------------
//  Base = laser_sensor.cpp de F2 (VERIFICADO en HW). La maquina de debounce +
//  latch de flanco esta INTACTA; lo unico que cambio es la FUENTE de la
//  lectura "haz roto":
//
//    F2/v2:  analogRead(A0) < baseline * ...          (analogico + calibracion)
//    v3:     digitalRead(D2) == LOW                   (digital, sin calibracion)
//
//  El divisor resistivo lleva la LDR a un nivel logico limpio: con el haz
//  presente D2 lee HIGH (BEAM_OK_LEVEL); al cortarse el haz cae a LOW. No hay
//  autocalibracion: se elimino toda la logica de baseline/umbral.
//
//  GARANTIAS DE F2 QUE SE CONSERVAN:
//    - Polling con millis(), sin ISR ni delay() en update(): retorna en us.
//    - DEBOUNCE temporal: la intrusion solo se CONFIRMA con el haz cortado
//      DEBOUNCE_MS continuos (micro-cortes no disparan).
//    - update() devuelve true UNA sola vez por corte (latch de flanco) y solo
//      en ARMED.
// ============================================================================

#include "laser_sensor.h"
#include "config.h"

namespace laser {

// ---- Estado interno del modulo ---------------------------------------------
static State s_state = State::DISARMED;

// Seguimiento del debounce del haz (identico a F2).
static unsigned long s_beamBrokenSince = 0;
static bool s_beamDown = false;
static bool s_intrusionLatched = false;

// resetTracking - limpia el seguimiento de debounce (tras armar).
static void resetTracking() {
  s_beamDown = false;
  s_intrusionLatched = false;
  s_beamBrokenSince = 0;
}

// init
//  Configura D2 como entrada DIGITAL regular (el pull-down lo da el divisor
//  externo; NO usar INPUT_PULLUP) y enciende el haz. No bloquea.
void init() {
  pinMode(PIN_LASER_EMITTER, OUTPUT);
  digitalWrite(PIN_LASER_EMITTER, LASER_EMITTER_ON_LEVEL);   // enciende el haz
  pinMode(PIN_LDR, INPUT);                                   // digital, sin pull-up

  s_state = State::DISARMED;
  resetTracking();
}

// isBeamBroken
//  Lectura instantanea (cruda, sin debounce): haz roto = D2 en LOW (distinto de
//  BEAM_OK_LEVEL).
bool isBeamBroken() {
  return (digitalRead(PIN_LDR) != BEAM_OK_LEVEL);
}

// update  (logica de F2 INTACTA; solo cambio la fuente de brokenNow)
bool update() {
  const unsigned long now = millis();
  const bool brokenNow = isBeamBroken();

  if (brokenNow) {
    // Flanco de bajada del haz: arranca la ventana de debounce.
    if (!s_beamDown) {
      s_beamDown = true;
      s_beamBrokenSince = now;
      s_intrusionLatched = false;
    }

    // Confirmacion: haz cortado de forma continua >= DEBOUNCE_MS.
    // Se reporta una sola vez (latch) y solo si el sistema esta ARMED.
    if (!s_intrusionLatched && (now - s_beamBrokenSince) >= DEBOUNCE_MS) {
      s_intrusionLatched = true;          // marca este ciclo de corte como tratado
      if (s_state == State::ARMED) {
        return true;                      // <-- intrusion confirmada (flanco)
      }
    }
  } else {
    // Haz restablecido: reinicia el seguimiento para el proximo corte.
    s_beamDown = false;
    s_intrusionLatched = false;
  }

  return false;
}

// arm
//  Pasa a ARMED. Reinicia el seguimiento para que la primera intrusion valida
//  tras armar requiera su propia ventana de debounce completa.
void arm() {
  s_state = State::ARMED;
  resetTracking();
  s_beamBrokenSince = millis();
}

// disarm
//  Pasa a DISARMED. La inhibicion de la alarma la hace el main (apaga buzzer).
void disarm() {
  s_state = State::DISARMED;
}

State getState() {
  return s_state;
}

}  // namespace laser

// ============================================================================
//  laser_sensor.cpp  -  Implementacion del sensor laser IR  (FASE 2)
// ----------------------------------------------------------------------------
//  Deteccion de intrusion por corte de haz laser/IR.
//
//  PRINCIPIO DE DISENO (por que cumple < 100 ms y evita falsos positivos):
//    - Lectura por POLLING con millis() en cada iteracion del loop (sin ISR,
//      por portabilidad AVR <-> Zephyr/UNO Q). No se usa delay() en ningun
//      punto, por lo que update() retorna en microsegundos.
//    - DEBOUNCE temporal: una intrusion solo se CONFIRMA si el haz permanece
//      interrumpido DEBOUNCE_MS (>= 200 ms) de forma CONTINUA. Cualquier
//      reaparicion del haz reinicia el contador -> los micro-cortes (insectos,
//      vibracion, ruido del fototransistor) no disparan la alarma.
//    - update() devuelve true UNA sola vez, en el instante exacto en que se
//      cumple el debounce (deteccion por flanco), y solo si el sistema esta
//      ARMED. main reacciona en la MISMA iteracion encendiendo el buzzer ->
//      la latencia haz-confirmado -> buzzer es esencialmente la de una
//      escritura GPIO (microsegundos), muy por debajo de 100 ms.
//
//  La polaridad del receptor (que lectura significa "haz roto") y el nivel que
//  enciende el emisor estan en config.h (LASER_BEAM_BROKEN_LEVEL /
//  LASER_EMITTER_ON_LEVEL): aqui NO hay numeros ni niveles magicos.
// ============================================================================

#include "laser_sensor.h"
#include "config.h"

namespace laser {

// ---- Estado interno del modulo ---------------------------------------------
// Inicia DISARMED segun el contrato del proyecto.
static State s_state = State::DISARMED;

// Seguimiento del debounce del haz.
//   s_beamBrokenSince : millis() del instante en que el haz se corto (inicio
//                       de la ventana de debounce). Valido solo si s_beamDown.
//   s_beamDown        : true mientras el haz esta interrumpido (lectura cruda).
//   s_intrusionLatched: true una vez confirmada la intrusion en el ciclo de
//                       corte actual; evita que update() devuelva true repetido
//                       mientras el haz siga cortado. Se limpia al volver el haz.
static unsigned long s_beamBrokenSince = 0;
static bool s_beamDown = false;
static bool s_intrusionLatched = false;

// init
//  Configura emisor (salida, encendido) y receptor (entrada con pull-up).
//  Deja el sistema en DISARMED y reinicia el seguimiento de debounce.
void init() {
  pinMode(PIN_LASER_EMITTER, OUTPUT);
  digitalWrite(PIN_LASER_EMITTER, LASER_EMITTER_ON_LEVEL);   // enciende el haz

  pinMode(PIN_LASER_RECEIVER, INPUT_PULLUP);

  s_state = State::DISARMED;
  s_beamBrokenSince = 0;
  s_beamDown = false;
  s_intrusionLatched = false;
}

// isBeamBroken
//  Lectura instantanea (cruda, sin debounce) del receptor.
//  Devuelve true si el haz esta interrumpido AHORA, segun la polaridad de
//  config.h.
bool isBeamBroken() {
  return (digitalRead(PIN_LASER_RECEIVER) == LASER_BEAM_BROKEN_LEVEL);
}

// update
//  Se llama en cada iteracion del loop. Aplica el debounce temporal y, si el
//  sistema esta ARMED, reporta (por flanco) la intrusion confirmada.
//
//  Devuelve true EXACTAMENTE en el ciclo en que el haz cumple DEBOUNCE_MS
//  interrumpido de forma continua estando ARMED; false en cualquier otro caso.
//  El seguimiento del haz se mantiene tambien en DISARMED para que, si se arma
//  con el haz ya cortado, no se "herede" una intrusion vieja: el latch impide
//  re-disparos y el contador se mide desde el corte real.
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
//  Pasa a ARMED. Reinicia el seguimiento del haz para que la primera intrusion
//  valida tras armar requiera su propia ventana de debounce completa (no
//  hereda un corte previo ocurrido mientras estaba DISARMED).
void arm() {
  s_state = State::ARMED;
  s_beamDown = false;
  s_intrusionLatched = false;
  s_beamBrokenSince = millis();
}

// disarm
//  Pasa a DISARMED. La inhibicion de la alarma es responsabilidad de main
//  (apaga el buzzer); aqui solo se actualiza el estado.
void disarm() {
  s_state = State::DISARMED;
}

// getState
//  Devuelve el estado actual (ARMED / DISARMED).
State getState() {
  return s_state;
}

}  // namespace laser

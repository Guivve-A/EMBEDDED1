// ============================================================================
//  laser_sensor.h  -  Deteccion de intrusion por haz laser sobre LDR DIGITAL
//  Ing 2 - base F2 (debounce 200 ms + latch de flanco, VERIFICADA en HW)
// ----------------------------------------------------------------------------
//  Modelo v3 (definitivo): la LDR se lee de forma DIGITAL en D2 (divisor
//  pull-down externo). El haz del KY-008 incide sobre la LDR:
//
//      D2 == HIGH (BEAM_OK_LEVEL)  -> haz presente  -> normal
//      D2 == LOW                   -> haz cortado    -> intrusion
//
//  Se elimina toda la lectura analogica y la autocalibracion de A0. La logica
//  de confirmacion (debounce DEBOUNCE_MS + latch de flanco + estado
//  ARMED/DISARMED) es EXACTAMENTE la de F2.
//
//  Patron de uso:
//      laser::init();            // configura D2 (INPUT) + enciende haz (D7)
//      laser::arm();
//      ... en loop():  if (laser::update()) { /* intrusion confirmada */ }
// ============================================================================

#ifndef FACE_SECURITY_LASER_SENSOR_H
#define FACE_SECURITY_LASER_SENSOR_H

#include <Arduino.h>

namespace laser {

// Estados del subsistema de deteccion (identicos a F2).
enum class State : uint8_t {
  DISARMED,   // solo monitoreo, sin disparar alarma (estado inicial)
  ARMED       // una intrusion confirmada dispara la alarma
};

// init
//  Proposito: configura D2 como INPUT regular (sin pull-up; el divisor lleva el
//             pull-down externo) y enciende el emisor laser (D7 HIGH). Deja el
//             sistema en DISARMED. NO bloquea (sin autocalibracion).
//  Inputs:    ninguno (usa PIN_LASER_EMITTER / PIN_LDR de config.h).
void init();

// update
//  Proposito: se llama en cada iteracion del loop. Lee D2, aplica el debounce
//             (DEBOUNCE_MS) y, si el sistema esta ARMED y el haz quedo cortado
//             (LOW) el tiempo suficiente, reporta intrusion UNA sola vez
//             (latch de flanco, igual que F2).
//  Outputs:   true  -> intrusion confirmada en este instante (flanco).
//             false -> sin novedad.
bool update();

// isBeamBroken
//  Proposito: lectura instantanea (sin debounce) del estado del haz.
//  Outputs:   true si D2 esta en LOW (haz cortado).
bool isBeamBroken();

// arm / disarm / getState  (identicos a F2)
void arm();
void disarm();
State getState();

}  // namespace laser

#endif  // FACE_SECURITY_LASER_SENSOR_H

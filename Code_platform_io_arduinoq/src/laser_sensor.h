// ============================================================================
//  laser_sensor.h  -  Deteccion de intrusion por haz laser IR
//  Ing 2 - Esqueleto creado en FASE 1 / implementacion en FASE 2
// ----------------------------------------------------------------------------
//  Encapsula el sensor laser (emisor + receptor) y el estado armado/desarmado
//  del sistema. Es la UNICA logica que debe responder localmente (< 100 ms)
//  sin esperar al servidor: si el haz se corta estando ARMED, se debe disparar
//  el buzzer de inmediato (la actuacion fisica vive en alerts.*).
//
//  Patron de uso (Fase 2):
//      laser::init();
//      laser::arm();
//      ... en loop():  if (laser::update()) { /* intrusion confirmada */ }
// ============================================================================

#ifndef FACE_SECURITY_LASER_SENSOR_H
#define FACE_SECURITY_LASER_SENSOR_H

#include <Arduino.h>

namespace laser {

// Estados del subsistema de deteccion.
enum class State : uint8_t {
  DISARMED,   // solo monitoreo, sin disparar buzzer (estado inicial)
  ARMED       // una intrusion confirmada dispara la alarma
};

// init
//  Proposito: configura los pines del emisor y receptor laser y enciende el
//             haz. Deja el sistema en estado DISARMED.
//  Inputs:    ninguno (usa PIN_LASER_EMITTER / PIN_LASER_RECEIVER de config.h).
//  Outputs:   ninguno.
void init();

// update
//  Proposito: se llama en cada iteracion del loop. Lee el receptor, aplica
//             debounce (DEBOUNCE_MS) y, si el sistema esta ARMED y el haz
//             quedo interrumpido el tiempo suficiente, reporta intrusion.
//  Inputs:    ninguno (lee el pin internamente; usa millis()).
//  Outputs:   true  -> intrusion confirmada en este instante (flanco).
//             false -> sin novedad.
bool update();

// isBeamBroken
//  Proposito: lectura instantanea (sin debounce) del estado del haz.
//  Inputs:    ninguno.
//  Outputs:   true si el haz esta interrumpido ahora mismo, false si esta intacto.
bool isBeamBroken();

// arm
//  Proposito: pasa el sistema a estado ARMED (habilita disparo de alarma).
//  Inputs:    ninguno.
//  Outputs:   ninguno.
void arm();

// disarm
//  Proposito: pasa el sistema a estado DISARMED (silencia/inhibe la alarma).
//  Inputs:    ninguno.
//  Outputs:   ninguno.
void disarm();

// getState
//  Proposito: consultar el estado actual (ARMED / DISARMED).
//  Inputs:    ninguno.
//  Outputs:   el State actual.
State getState();

}  // namespace laser

#endif  // FACE_SECURITY_LASER_SENSOR_H

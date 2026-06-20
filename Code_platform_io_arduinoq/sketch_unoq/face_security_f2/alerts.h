// ============================================================================
//  alerts.h  -  Actuacion fisica: buzzer + LEDs de estado
//  Ing 2 - Esqueleto creado en FASE 1 / implementacion en FASE 2 y FASE 5
// ----------------------------------------------------------------------------
//  Centraliza la salida hacia el usuario:
//    - Buzzer activo (intrusion).
//    - LED verde (acceso autorizado) y LED rojo (intruso / fallo de red).
//
//  Tabla de actuacion (de work_ing2.md):
//    Boot / DISARMED .................. todo OFF
//    ARMED sin intrusion .............. LED verde parpadeo lento (1 Hz)
//    Intrusion (antes de respuesta) ... buzzer ON inmediato (< 100 ms)
//    Respuesta match=true ............. LED verde ON 3 s
//    Respuesta match=false ............ LED rojo + buzzer continuos hasta DISARM
//    WiFi caido ....................... LED rojo parpadeo rapido (5 Hz)
//
//  Las funciones parpadeo/temporizadas seran NO bloqueantes (millis()); por eso
//  se preve un update() que se llama desde el loop.
// ============================================================================

#ifndef FACE_SECURITY_ALERTS_H
#define FACE_SECURITY_ALERTS_H

#include <Arduino.h>

namespace alerts {

// init
//  Proposito: configura los pines del buzzer y de los LEDs y los deja en OFF.
//  Inputs:    ninguno (usa PIN_BUZZER / PIN_LED_GREEN / PIN_LED_RED de config.h).
//  Outputs:   ninguno.
void init();

// update
//  Proposito: avanza los patrones temporizados no bloqueantes (parpadeos,
//             apagado del LED verde tras 3 s, etc.). Se llama en cada loop.
//  Inputs:    ninguno (usa millis()).
//  Outputs:   ninguno.
void update();

// --- Buzzer ---------------------------------------------------------------

// buzzerOn
//  Proposito: enciende el buzzer de forma continua (intrusion / intruso).
//  Inputs:    ninguno.   Outputs: ninguno.
void buzzerOn();

// buzzerOff
//  Proposito: apaga el buzzer.
//  Inputs:    ninguno.   Outputs: ninguno.
void buzzerOff();

// buzzerPulse
//  Proposito: enciende el buzzer durante `ms` milisegundos y lo apaga solo,
//             sin bloquear (gestionado por update()).
//  Inputs:    ms -> duracion del pulso en milisegundos.
//  Outputs:   ninguno.
void buzzerPulse(unsigned long ms);

// --- LEDs de estado -------------------------------------------------------

// greenOn / greenOff
//  Proposito: control directo del LED verde (acceso autorizado).
void greenOn();
void greenOff();

// redOn / redOff
//  Proposito: control directo del LED rojo (intruso / fallo de red).
void redOn();
void redOff();

// showAuthorized
//  Proposito: feedback de "acceso autorizado": LED verde ON 3 s (no bloqueante).
//  Inputs:    ninguno.   Outputs: ninguno.
void showAuthorized();

// showIntruder
//  Proposito: feedback de "intruso": LED rojo + buzzer continuos hasta DISARM.
//  Inputs:    ninguno.   Outputs: ninguno.
void showIntruder();

// clear
//  Proposito: apaga todo (buzzer + ambos LEDs) y cancela patrones activos.
//  Inputs:    ninguno.   Outputs: ninguno.
void clear();

}  // namespace alerts

#endif  // FACE_SECURITY_ALERTS_H

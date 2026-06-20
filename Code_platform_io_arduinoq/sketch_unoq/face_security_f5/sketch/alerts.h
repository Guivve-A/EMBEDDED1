// ============================================================================
//  alerts.h  -  Actuacion fisica: buzzer + LEDs de estado  (FASE 5)
//  Ing 2 - base F2 (buzzer VERIFICADO en HW) + patrones de LED completos
// ----------------------------------------------------------------------------
//  Centraliza la salida hacia el usuario. Tabla de actuacion (work_ing2.md):
//
//    Boot / DISARMED .................. todo OFF
//    ARMED sin intrusion .............. LED verde parpadeo 1 Hz
//    Intrusion (esperando resultado) .. buzzer ON inmediato (< 100 ms)
//    Resultado MATCH .................. buzzer OFF + LED verde FIJO 3 s
//    Resultado INTRUDER ............... LED rojo + buzzer CONTINUOS hasta DISARM
//    Timeout sin resultado (15 s) ..... LED rojo PARPADEANTE + buzzer (fail-safe)
//
//  Todo NO bloqueante (millis()): update() se llama en cada iteracion del loop
//  y avanza parpadeos/ventanas temporizadas. El buzzer conserva la garantia
//  F2 de latencia (<100 ms): buzzerOn() es una unica escritura GPIO.
// ============================================================================

#ifndef FACE_SECURITY_ALERTS_H
#define FACE_SECURITY_ALERTS_H

#include <Arduino.h>

namespace alerts {

// init
//  Proposito: configura buzzer y LEDs como salidas y deja todo en OFF.
void init();

// update
//  Proposito: avanza los patrones temporizados (parpadeos, ventana verde 3 s,
//             auto-apagado de buzzerPulse). Llamar en CADA iteracion del loop.
void update();

// --- Buzzer (identico a F2) -------------------------------------------------
void buzzerOn();                       // continuo (latencia = 1 escritura GPIO)
void buzzerOff();                      // apaga y cancela pulsos
void buzzerPulse(unsigned long ms);    // pulso temporizado no bloqueante
void happyChime();                     // melodia "alegre" (beeps cortos) NO bloqueante
                                       //   tras MATCH; avanza en update(). Buzzer
                                       //   activo on/off: el ritmo da el caracter alegre.

// --- LED verde ---------------------------------------------------------------
void greenOn();                        // fijo ON (cancela parpadeo/ventana)
void greenOff();                       // OFF (cancela parpadeo/ventana)
void greenBlink(unsigned long halfPeriodMs);  // parpadeo (ARMED: 500 -> 1 Hz)
void greenTimed(unsigned long ms);     // fijo ON durante `ms`, luego OFF solo

// --- LED rojo ----------------------------------------------------------------
void redOn();                          // fijo ON (cancela parpadeo)
void redOff();                         // OFF (cancela parpadeo)
void redBlink(unsigned long halfPeriodMs);    // parpadeo (ALARM timeout: 250)

// clear
//  Proposito: apaga todo (buzzer + LEDs) y cancela todos los patrones.
void clear();

}  // namespace alerts

#endif  // FACE_SECURITY_ALERTS_H

// ============================================================================
//  alerts.cpp  -  Implementacion de buzzer + LEDs de estado
// ----------------------------------------------------------------------------
//  FASE 2: el foco es el BUZZER (buzzerOn / buzzerOff / buzzerPulse) con
//  respuesta inmediata y sin bloqueos. Los LEDs verde/rojo quedan con control
//  directo minimo (on/off) + init; su logica completa (parpadeos 1 Hz/5 Hz,
//  ventana de 3 s, patron intruso) se implementa en FASE 5.
//
//  GARANTIA DE LATENCIA (< 100 ms):
//    buzzerOn() es una unica escritura GPIO (digitalWrite). No hay esperas,
//    bucles ni delay(). Llamada desde el loop en cuanto laser::update() confirma
//    la intrusion, el sonido arranca en microsegundos -> el presupuesto de
//    100 ms se cumple con varios ordenes de magnitud de margen.
//
//  NO BLOQUEANTE:
//    buzzerPulse(ms) NO usa delay(): enciende el buzzer y registra el instante
//    de apagado; update() (llamado cada iteracion del loop) lo apaga cuando el
//    tiempo vence. Un buzzerOn() o buzzerOff() explicito cancela el pulso.
//
//  Pines y niveles activos viven en config.h (PIN_BUZZER / BUZZER_ON_LEVEL,
//  PIN_LED_GREEN/RED). Sin valores magicos aqui.
// ============================================================================

#include "alerts.h"
#include "config.h"

namespace alerts {

// Nivel "apagado" del buzzer = complemento del nivel activo de config.h.
static const uint8_t BUZZER_OFF_LEVEL = (BUZZER_ON_LEVEL == HIGH) ? LOW : HIGH;

// ---- Estado interno --------------------------------------------------------
//   s_buzzerActive  : true si el buzzer esta sonando ahora mismo.
//   s_pulseEndMs     : millis() en que un pulso temporizado debe apagarse.
//   s_pulseRunning   : true mientras hay un buzzerPulse() en curso.
static bool s_buzzerActive = false;
static unsigned long s_pulseEndMs = 0;
static bool s_pulseRunning = false;

// ---- Helper interno: escribe el pin del buzzer y refleja el estado ---------
static void writeBuzzer(bool on) {
  digitalWrite(PIN_BUZZER, on ? BUZZER_ON_LEVEL : BUZZER_OFF_LEVEL);
  s_buzzerActive = on;
}

// init
//  Configura buzzer y LEDs como salidas y los deja todos en OFF.
void init() {
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);

  writeBuzzer(false);
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, LOW);

  s_pulseRunning = false;
  s_pulseEndMs = 0;
}

// update
//  Avanza los patrones temporizados no bloqueantes. En FASE 2 solo gestiona el
//  auto-apagado de buzzerPulse(); en FASE 5 se anaden parpadeos y la ventana
//  de 3 s del LED verde. Debe llamarse en cada iteracion del loop.
void update() {
  if (s_pulseRunning && (long)(millis() - s_pulseEndMs) >= 0) {
    writeBuzzer(false);
    s_pulseRunning = false;
  }
}

// --- Buzzer ---------------------------------------------------------------

// buzzerOn
//  Enciende el buzzer de forma continua (intrusion). Cancela cualquier pulso
//  temporizado en curso. Latencia: una escritura GPIO.
void buzzerOn() {
  s_pulseRunning = false;     // un encendido continuo manda sobre un pulso
  writeBuzzer(true);
}

// buzzerOff
//  Apaga el buzzer de inmediato y cancela cualquier pulso en curso.
void buzzerOff() {
  s_pulseRunning = false;
  writeBuzzer(false);
}

// buzzerPulse
//  Enciende el buzzer durante `ms` milisegundos y lo apaga solo (via update()),
//  sin bloquear. Si ms == 0, no hace nada.
//  Inputs:  ms -> duracion del pulso en milisegundos.
void buzzerPulse(unsigned long ms) {
  if (ms == 0) return;
  writeBuzzer(true);
  s_pulseEndMs = millis() + ms;
  s_pulseRunning = true;
}

// --- LEDs de estado (control directo; logica completa en FASE 5) ----------
void greenOn()  { digitalWrite(PIN_LED_GREEN, HIGH); }
void greenOff() { digitalWrite(PIN_LED_GREEN, LOW);  }
void redOn()    { digitalWrite(PIN_LED_RED,   HIGH); }
void redOff()   { digitalWrite(PIN_LED_RED,   LOW);  }

// showAuthorized
//  FASE 5: LED verde ON 3 s no bloqueante + buzzer OFF. En F2 stub minimo:
//  apaga el buzzer y enciende el verde (sin la ventana temporizada todavia).
void showAuthorized() {
  buzzerOff();
  greenOn();
}

// showIntruder
//  FASE 5: LED rojo + buzzer continuos hasta DISARM. En F2 stub minimo:
//  enciende rojo + buzzer continuo (la cancelacion la hace clear()/buzzerOff()).
void showIntruder() {
  redOn();
  buzzerOn();
}

// clear
//  Apaga buzzer + ambos LEDs y cancela cualquier patron/pulso activo.
void clear() {
  buzzerOff();
  greenOff();
  redOff();
  s_pulseRunning = false;
}

}  // namespace alerts

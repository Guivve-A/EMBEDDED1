// ============================================================================
//  alerts.cpp  -  Buzzer + LEDs de estado  (FASE 5)
// ----------------------------------------------------------------------------
//  Base F2 (buzzer verificado en HW) + los patrones de LED que F2 dejaba como
//  stubs "para Fase 5": parpadeo del verde en ARMED, ventana de 3 s del verde
//  tras MATCH y parpadeo del rojo en la alarma por timeout.
//
//  DISENO: cada LED tiene un "modo" (OFF / ON / BLINK / TIMED) y update()
//  avanza los modos temporizados con millis(). Ninguna funcion bloquea.
//  Llamar a cualquier setter cancela el patron anterior de ese LED, de modo
//  que la maquina de estados del .ino solo declara el patron deseado y no se
//  preocupa de limpiar el previo.
//
//  GARANTIA DE LATENCIA (< 100 ms, heredada de F2):
//    buzzerOn() es una unica escritura GPIO (digitalWrite). Sin esperas.
// ============================================================================

#include "alerts.h"
#include "config.h"

namespace alerts {

// Nivel "apagado" del buzzer = complemento del nivel activo de config.h.
static const uint8_t BUZZER_OFF_LEVEL = (BUZZER_ON_LEVEL == HIGH) ? LOW : HIGH;

// ---- Buzzer (identico a F2) -------------------------------------------------
static bool s_buzzerActive = false;
static unsigned long s_pulseEndMs = 0;
static bool s_pulseRunning = false;

// Chime "alegre" tras MATCH: secuencia de tramos (on,off,on,off,...) en ms,
// empezando ENCENDIDO. Buzzer activo (on/off) -> el ritmo (corto-corto-largo)
// da la sensacion alegre. NO bloqueante: lo avanza update().
static const unsigned long CHIME_STEPS_MS[] = {90, 70, 90, 70, 220};
static const uint8_t CHIME_N = sizeof(CHIME_STEPS_MS) / sizeof(CHIME_STEPS_MS[0]);
static bool          s_chimeRunning = false;
static uint8_t       s_chimeIdx = 0;
static unsigned long s_chimeStepEndMs = 0;

static void writeBuzzer(bool on) {
  digitalWrite(PIN_BUZZER, on ? BUZZER_ON_LEVEL : BUZZER_OFF_LEVEL);
  s_buzzerActive = on;
}

// ---- LEDs: modos por LED ------------------------------------------------------
enum class LedMode : uint8_t { OFF, ON, BLINK, TIMED };

struct LedChannel {
  uint8_t       pin;
  LedMode       mode;
  unsigned long halfPeriodMs;   // BLINK: semiperiodo
  unsigned long lastToggleMs;   // BLINK: ultimo cambio
  unsigned long offAtMs;        // TIMED: instante de apagado
  bool          level;          // nivel logico actual
};

static LedChannel s_green = {PIN_LED_GREEN, LedMode::OFF, 0, 0, 0, false};
static LedChannel s_red   = {PIN_LED_RED,   LedMode::OFF, 0, 0, 0, false};

static void writeLed(LedChannel& led, bool on) {
  digitalWrite(led.pin, on ? HIGH : LOW);
  led.level = on;
}

static void setMode(LedChannel& led, LedMode mode, bool level,
                    unsigned long halfPeriodMs = 0, unsigned long offAtMs = 0) {
  led.mode = mode;
  led.halfPeriodMs = halfPeriodMs;
  led.offAtMs = offAtMs;
  led.lastToggleMs = millis();
  writeLed(led, level);
}

static void updateLed(LedChannel& led, unsigned long now) {
  switch (led.mode) {
    case LedMode::BLINK:
      if (now - led.lastToggleMs >= led.halfPeriodMs) {
        led.lastToggleMs = now;
        writeLed(led, !led.level);
      }
      break;
    case LedMode::TIMED:
      if ((long)(now - led.offAtMs) >= 0) {
        setMode(led, LedMode::OFF, false);
      }
      break;
    default:
      break;   // OFF / ON: nada que avanzar
  }
}

// ---- API ----------------------------------------------------------------------

// init - todo como salida y en OFF.
void init() {
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);

  writeBuzzer(false);
  setMode(s_green, LedMode::OFF, false);
  setMode(s_red,   LedMode::OFF, false);

  s_pulseRunning = false;
  s_pulseEndMs = 0;
}

// update - avanza pulso del buzzer + patrones de ambos LEDs. No bloqueante.
void update() {
  const unsigned long now = millis();

  if (s_pulseRunning && (long)(now - s_pulseEndMs) >= 0) {
    writeBuzzer(false);
    s_pulseRunning = false;
  }

  // Avance del chime alegre (secuencia on/off no bloqueante).
  if (s_chimeRunning && (long)(now - s_chimeStepEndMs) >= 0) {
    s_chimeIdx++;
    if (s_chimeIdx >= CHIME_N) {
      writeBuzzer(false);
      s_chimeRunning = false;
    } else {
      writeBuzzer((s_chimeIdx % 2) == 0);   // pares = ON, impares = OFF
      s_chimeStepEndMs = now + CHIME_STEPS_MS[s_chimeIdx];
    }
  }

  updateLed(s_green, now);
  updateLed(s_red, now);
}

// --- Buzzer ---------------------------------------------------------------
void buzzerOn() {
  s_pulseRunning = false;     // un encendido continuo manda sobre un pulso
  s_chimeRunning = false;     // ...y sobre el chime
  writeBuzzer(true);
}

void buzzerOff() {
  s_pulseRunning = false;
  s_chimeRunning = false;
  writeBuzzer(false);
}

void buzzerPulse(unsigned long ms) {
  if (ms == 0) return;
  s_chimeRunning = false;
  writeBuzzer(true);
  s_pulseEndMs = millis() + ms;
  s_pulseRunning = true;
}

// happyChime - arranca la secuencia alegre desde el primer tramo (ENCENDIDO).
void happyChime() {
  s_pulseRunning = false;
  s_chimeIdx = 0;
  s_chimeRunning = true;
  writeBuzzer(true);
  s_chimeStepEndMs = millis() + CHIME_STEPS_MS[0];
}

// --- LED verde --------------------------------------------------------------
void greenOn()  { setMode(s_green, LedMode::ON,  true);  }
void greenOff() { setMode(s_green, LedMode::OFF, false); }

void greenBlink(unsigned long halfPeriodMs) {
  setMode(s_green, LedMode::BLINK, true, halfPeriodMs);
}

void greenTimed(unsigned long ms) {
  setMode(s_green, LedMode::TIMED, true, 0, millis() + ms);
}

// --- LED rojo ----------------------------------------------------------------
void redOn()  { setMode(s_red, LedMode::ON,  true);  }
void redOff() { setMode(s_red, LedMode::OFF, false); }

void redBlink(unsigned long halfPeriodMs) {
  setMode(s_red, LedMode::BLINK, true, halfPeriodMs);
}

// clear - apaga buzzer + ambos LEDs y cancela patrones/pulsos.
void clear() {
  buzzerOff();
  setMode(s_green, LedMode::OFF, false);
  setMode(s_red,   LedMode::OFF, false);
}

}  // namespace alerts

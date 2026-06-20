// ============================================================================
//  main.cpp  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)
//  Ing 2 - FASE 2: maquina de estados laser + buzzer (respuesta local < 100 ms)
// ----------------------------------------------------------------------------
//  Que hace esta fase:
//    - Inicializa el sensor laser (laser::init, enciende el haz) y los
//      actuadores (alerts::init, buzzer + LEDs en OFF). Estado inicial DISARMED.
//    - Acepta comandos por Serial @115200, una linea terminada en '\n':
//          ARM     -> arma el sistema
//          DISARM  -> desarma y silencia el buzzer al instante
//      (se aceptan en mayus/minus y se ignoran espacios y CR sobrantes).
//    - En cada iteracion llama laser::update(). Si el sistema esta ARMED y se
//      confirma una intrusion (haz cortado >= DEBOUNCE_MS continuos), enciende
//      el buzzer DE INMEDIATO e imprime:
//          INTRUSION DETECTED t=<millis> ms
//    - Mantiene un blink de "vida" en el LED onboard y un heartbeat por Serial.
//
//  POR QUE LA RESPUESTA ES < 100 ms:
//    El loop no usa ningun delay() bloqueante: todo es millis(). laser::update()
//    confirma la intrusion y, en la MISMA iteracion, se llama alerts::buzzerOn()
//    que es una sola escritura GPIO. La cadena "haz confirmado -> buzzer sonando"
//    tarda microsegundos; el presupuesto de 100 ms se cumple con enorme margen.
//    (El debounce de 200 ms es la espera DELIBERADA para confirmar la intrusion
//     y evitar falsos positivos; el "< 100 ms" se mide desde esa confirmacion.)
//
//  Camara/WiFi/HTTP (F3-F5) se integraran aqui mas adelante, sobre este mismo
//  patron no bloqueante.
// ============================================================================

#include <Arduino.h>
#include <ctype.h>    // toupper()
#include <string.h>   // strcmp()
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
// Acumula caracteres hasta recibir '\n'. Tamano holgado para "DISARM" + ruido.
static char s_cmdBuf[16];
static uint8_t s_cmdLen = 0;

// ---------------------------------------------------------------------------
//  printArmState - imprime el estado actual del sistema por Serial.
//  Inputs:  ninguno.  Outputs: ninguno (efecto: linea por Serial).
// ---------------------------------------------------------------------------
static void printArmState() {
  Serial.print(F("STATE = "));
  Serial.println(laser::getState() == laser::State::ARMED ? F("ARMED")
                                                          : F("DISARMED"));
}

// ---------------------------------------------------------------------------
//  handleCommand - interpreta una linea de comando ya recibida (sin '\n').
//  Reconoce "ARM" y "DISARM" (insensible a mayus/minus). Cualquier otra cosa
//  se reporta como desconocida. ARM/DISARM confirman por Serial; DISARM ademas
//  silencia el buzzer en el acto.
//  Inputs:  cmd -> cadena C terminada en '\0' con el comando recibido.
//  Outputs: ninguno (efectos: cambia estado, actua buzzer, imprime).
// ---------------------------------------------------------------------------
static void handleCommand(char* cmd) {
  // Normaliza a mayusculas in-place (comando corto, costo despreciable).
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

// ---------------------------------------------------------------------------
//  pollSerialCommands - lee caracteres pendientes del Serial sin bloquear y,
//  al encontrar fin de linea ('\n'), despacha el comando acumulado.
//  Tolera '\r' (CRLF) y descarta lineas demasiado largas (overflow del buffer).
//  Inputs:  ninguno.  Outputs: ninguno.
// ---------------------------------------------------------------------------
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

    // Acumula; si se llena el buffer, se descarta la linea (evita overflow).
    if (s_cmdLen < (sizeof(s_cmdBuf) - 1)) {
      s_cmdBuf[s_cmdLen++] = c;
    } else {
      s_cmdLen = 0;   // linea demasiado larga -> reinicia y espera el proximo '\n'
    }
  }
}

// ---------------------------------------------------------------------------
//  heartbeat - imprime periodicamente una linea de estado cuando no hay eventos
//  (util para verificar que el firmware sigue vivo y ver haz/buzzer en vivo).
//  Inputs:  now -> millis() actual.  Outputs: ninguno.
// ---------------------------------------------------------------------------
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

  // Serial @115200 (exigido por el proyecto).
  Serial.begin(115200);
  while (!Serial && millis() < 2000) {
    /* espera no bloqueante acotada a 2 s */
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
  //    update() solo devuelve true si estamos ARMED y la intrusion se confirmo.
  if (laser::update()) {
    // --- Respuesta local critica: buzzer INMEDIATO (una escritura GPIO) ---
    alerts::buzzerOn();

    // Log con el formato exigido por el exit gate.
    // NOTA: el brief pide Serial.printf("INTRUSION DETECTED t=%lu ms\n", ...).
    //   El core AVR del env de validacion (env:uno) NO expone Serial.printf,
    //   asi que se compone la MISMA linea con print/println (portable AVR <->
    //   Zephyr del UNO Q). El texto emitido es identico.
    Serial.print(F("INTRUSION DETECTED t="));
    Serial.print(now);
    Serial.println(F(" ms"));
  }

  // 3) Actuadores temporizados no bloqueantes (auto-apagado de pulsos, etc.).
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

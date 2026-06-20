// ============================================================================
//  face_security_f1.ino  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)
//  Ing 2 - FASE 1: bring-up fisico (blink no bloqueante + Serial @115200)
// ----------------------------------------------------------------------------
//  POR QUE EXISTE ESTE ARCHIVO:
//    arduino-cli (toolchain que corre DENTRO del propio UNO Q, core
//    arduino:zephyr:unoq) NO usa la estructura PlatformIO del proyecto. Espera
//    un "sketch": una carpeta cuyo nombre coincide con el .ino. Este .ino es la
//    version-sketch, EQUIVALENTE en comportamiento, del firmware F1 que vive en
//    ../../src/main.cpp del proyecto PlatformIO. El proyecto PlatformIO queda
//    INTACTO; este sketch es solo el vehiculo para compilar/flashear en el UNO Q.
//
//  QUE HACE LA FASE 1 (exit gate):
//    - Serial.begin(115200) e imprime "Boot OK - F1" una vez en setup().
//    - Parpadea el LED onboard cada BLINK_INTERVAL_MS (500 ms) SIN delay()
//      (temporizado con millis()), evidenciando que el firmware esta vivo.
//    - Emite un heartbeat periodico por Serial para poder verificar el "vivo"
//      tambien por consola (no solo por el LED).
//
//  Mantiene el patron NO BLOQUEANTE que el resto del firmware (F2-F5) reutiliza:
//    todo el tiempo se gestiona con millis(); el loop nunca se bloquea.
//
//  Los valores (intervalos y pin) replican config.h del proyecto PlatformIO.
//  Se definen aqui de forma local y autocontenida para que el sketch compile
//  sin arrastrar el resto de modulos (laser/alerts/camera/wifi), que no
//  intervienen en el exit gate de F1.
//
//  CLAVE DEL UNO Q (descubierto en bring-up): en esta placa 'Serial' NO es un
//  UART/USB-CDC normal. Lo PROVEE la libreria Arduino_RouterBridge: 'Serial'
//  esta aliaseado a 'Monitor', un Stream que habla por RPC con 'arduino-router'
//  y se lee con 'arduino-app-cli monitor' en el lado Linux. Por eso es
//  OBLIGATORIO incluir <Arduino_RouterBridge.h>: sin esa inclusion, 'Serial' es
//  un stub silencioso y NADA llega al monitor (el LED igual parpadea, pero no
//  hay texto). Con la inclusion, Serial.begin()/println() funcionan normal.
// ============================================================================

// 'Serial' del UNO Q lo provee esta libreria (alias de Monitor via router).
#include <Arduino_RouterBridge.h>

// --- Parametros (espejo de include/config.h del proyecto PlatformIO) --------

// LED onboard para el blink de bring-up. El core del UNO Q define LED_BUILTIN;
// si no lo definiera, se cae a 13 (estandar tipo UNO).
#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif
#define PIN_LED_ONBOARD       LED_BUILTIN

// Periodo del blink de vida (config.h: BLINK_INTERVAL_MS = 500).
#define BLINK_INTERVAL_MS     500UL

// Cada cuanto se imprime el heartbeat por Serial (config.h: 5000 ms).
#define HEARTBEAT_INTERVAL_MS 5000UL

// Identidad del firmware (informativo en el heartbeat / boot).
#define PROJECT_NAME          "EMBEBIDOS_1 / face_security"
#define FW_VERSION            "F1-bringup"

// --- Estado no bloqueante ----------------------------------------------------
static unsigned long s_lastBlinkMs     = 0;
static bool          s_ledState        = false;
static unsigned long s_lastHeartbeatMs = 0;
static unsigned long s_bootMs          = 0;

void setup() {
  // LED de vida.
  pinMode(PIN_LED_ONBOARD, OUTPUT);
  digitalWrite(PIN_LED_ONBOARD, LOW);

  // --- Inicializacion del canal Serial del UNO Q (patron oficial) ----------
  // En esta placa el Serial/Monitor sale por RPC al arduino-router. La
  // secuencia correcta (ver examples/monitor/monitor.ino del core) es:
  //   1) Serial.begin()  2) Bridge.begin()  3) Monitor.begin()  4) esperar Monitor.
  // Sin Bridge.begin()/Monitor.begin() los bytes NO llegan al router y
  // 'arduino-app-cli monitor' no muestra nada.
  Serial.begin(115200);

  if (!Bridge.begin()) {
    // Sin Bridge no hay salida posible; igual seguimos para que el LED parpadee.
    Serial.println("ERR: Bridge.begin() fallo");
  }

  Monitor.begin(115200);

  // Espera a que un monitor se conecte para no perder el banner, pero ACOTADA
  // (hasta 10 s) para poder correr headless: si nadie conecta, igual arranca y
  // el LED parpadea. El parpadeo del LED enciende ANTES de esta espera abajo.
  unsigned long waitStart = millis();
  while (!Monitor && (millis() - waitStart) < 10000UL) {
    // Mantiene el LED parpadeando mientras espera (no se queda "muerto").
    unsigned long now = millis();
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now;
      s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    delay(10);
  }

  s_bootMs = millis();

  // Linea exigida por el exit gate de la Fase 1.
  Serial.println("Boot OK - F1");
  Serial.print("  proyecto = "); Serial.println(PROJECT_NAME);
  Serial.print("  firmware = "); Serial.println(FW_VERSION);
  Serial.print("  blink    = "); Serial.print(BLINK_INTERVAL_MS); Serial.println(" ms");
}

void loop() {
  const unsigned long now = millis();

  // Blink de vida del LED onboard, sin delay().
  if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
    s_lastBlinkMs = now;
    s_ledState = !s_ledState;
    digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
  }

  // Heartbeat de diagnostico por Serial (para verificar "vivo" por consola).
  if (now - s_lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    s_lastHeartbeatMs = now;
    Serial.print("[hb] F1 alive | uptime=");
    Serial.print((now - s_bootMs) / 1000UL);
    Serial.print(" s | led=");
    Serial.println(s_ledState ? "ON" : "OFF");
  }
}

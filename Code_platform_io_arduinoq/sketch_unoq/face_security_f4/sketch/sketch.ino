// ============================================================================
//  sketch.ino  -  EMBEBIDOS_1 / face_security (Arduino UNO Q)  -  FASE 4
//  Ing 2 (firmware embedded)  -  WiFi AP + portal + 2 redes persistentes
// ----------------------------------------------------------------------------
//  QUE HACE F4 Y DONDE CORRE CADA PARTE (lee esto antes de cablear):
//
//    El UNO Q es HIBRIDO (MCU STM32U585 + lado Linux Qualcomm con el WiFi).
//    A diferencia de un ESP32, el WiFi NO se controla desde este sketch: NO
//    existe libreria WiFi.h para el MCU. Por eso F4 se reparte asi:
//
//      LADO LINUX (App Lab):
//        - python/main.py  -> portal web (brick web_ui) en :7000
//        - host/fs_wifi.sh -> motor WiFi real con nmcli (AP, 2 redes, cliente)
//        - host/fs_wifi_watch.sh -> aplica lo que el portal guarda
//        - "EEPROM de 2 redes" = 2 perfiles persistentes de NetworkManager
//        - "AP 192.168.4.1"    = NM modo shared -> gateway 10.42.0.1:7000
//
//      ESTE SKETCH (MCU):
//        - Coordina lo FISICO: LED de estado (verde=cliente, rojo=AP) y el
//          BOTON DE RESET (D3). Mantener el boton > 3 s imprime una linea
//          'RESET_REQUEST' por Serial para que el lado Linux ejecute
//          'fs_wifi.sh reset' (borra redes y vuelve a AP).
//        - Acepta por Serial: 'MODE AP' | 'MODE CLIENT' para reflejar el
//          estado actual en los LEDs (el lado Linux puede enviarlos).
//
//  IMPORTANTE (UNO Q): 'Serial' lo provee Arduino_RouterBridge y solo llega al
//  monitor con una App Lab corriendo (arduino-app-cli monitor). Por eso se
//  incluye <Arduino_RouterBridge.h> + Bridge.begin()/Monitor.begin().
//
//  ----------------------------------------------------------------------------
//  PINOUT DEL SKETCH (forma UNO R3, alias validados en HW en F1/F2):
//    D13 (LED_BUILTIN) -> LED onboard "vivo" (blink 500 ms)
//    D5                -> LED VERDE  (ON = modo CLIENTE / red OK)        [+R 220R a GND]
//    D6                -> LED ROJO   (ON = modo AP / sin red)            [+R 220R a GND]
//    D3                -> BOTON RESET (INPUT_PULLUP, otro extremo a GND) [mantener 3 s]
//  (laser D7, receptor D2, buzzer D8 -> F2; OV7670 -> F3; ver README/config.h)
//  ============================================================================

#include <Arduino_RouterBridge.h>
#include <ctype.h>
#include <string.h>

#include "config.h"

#ifndef FW_VERSION
#define FW_VERSION "0.4.0-f4"
#endif

// --- Estado no bloqueante ---------------------------------------------------
static unsigned long s_lastBlinkMs = 0;
static bool          s_ledState    = false;
static unsigned long s_lastHbMs    = 0;
static unsigned long s_bootMs      = 0;

// Modo logico actual reflejado en los LEDs (lo informa el lado Linux).
enum NetMode { MODE_UNKNOWN, MODE_AP, MODE_CLIENT };
static NetMode s_mode = MODE_AP;   // al boot, lo normal es AP (sin red guardada)

// Boton de reset.
static int           s_btnStable    = HIGH;   // ultimo nivel estable
static int           s_btnLastRead  = HIGH;
static unsigned long s_btnChangeMs  = 0;       // ultimo cambio (antirrebote)
static unsigned long s_btnPressMs   = 0;       // inicio de la pulsacion estable
static bool          s_resetLatched = false;   // ya se pidio el reset en esta pulsacion

// Buffer de comandos por Serial.
static char    s_cmd[24];
static uint8_t s_cmdLen = 0;

// applyModeLeds - refleja el modo en los LEDs (verde=cliente, rojo=AP).
static void applyModeLeds() {
  bool client = (s_mode == MODE_CLIENT);
  digitalWrite(PIN_LED_GREEN, (client ? LED_ON_LEVEL : !LED_ON_LEVEL));
  digitalWrite(PIN_LED_RED,   (client ? !LED_ON_LEVEL : LED_ON_LEVEL));
}

static void printStatus() {
  Serial.print(F("STATE = "));
  Serial.println(s_mode == MODE_CLIENT ? F("CLIENT") : F("AP"));
}

// handleCommand - 'MODE AP' | 'MODE CLIENT' | 'STATUS'.
static void handleCommand(char* cmd) {
  for (char* p = cmd; *p; ++p) *p = (char)toupper((unsigned char)*p);

  if (strcmp(cmd, "MODE AP") == 0) {
    s_mode = MODE_AP; applyModeLeds();
    Serial.println(F("OK MODE AP")); printStatus();
  } else if (strcmp(cmd, "MODE CLIENT") == 0) {
    s_mode = MODE_CLIENT; applyModeLeds();
    Serial.println(F("OK MODE CLIENT")); printStatus();
  } else if (strcmp(cmd, "STATUS") == 0) {
    printStatus();
  } else if (cmd[0] != '\0') {
    Serial.print(F("CMD desconocido: ")); Serial.println(cmd);
  }
}

static void pollSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (s_cmdLen > 0) { s_cmd[s_cmdLen] = '\0'; handleCommand(s_cmd); s_cmdLen = 0; }
      continue;
    }
    if (s_cmdLen < sizeof(s_cmd) - 1) s_cmd[s_cmdLen++] = c; else s_cmdLen = 0;
  }
}

// updateResetButton - antirrebote + deteccion de mantenido > RESET_HOLD_MS.
// Al cumplirse, imprime 'RESET_REQUEST' UNA vez (el lado Linux ejecuta el
// reset real). Da feedback con blink rapido del LED onboard mientras se manti.
static void updateResetButton(unsigned long now) {
  int raw = digitalRead(PIN_BUTTON_RESET);

  if (raw != s_btnLastRead) { s_btnLastRead = raw; s_btnChangeMs = now; }

  if ((now - s_btnChangeMs) >= DEBOUNCE_MS && raw != s_btnStable) {
    s_btnStable = raw;
    if (s_btnStable == BUTTON_PRESSED_LEVEL) {
      s_btnPressMs = now; s_resetLatched = false;
      Serial.println(F("[btn] reset presionado; manten 3 s para borrar redes"));
    } else {
      if (!s_resetLatched) Serial.println(F("[btn] liberado antes de 3 s; cancelado"));
    }
  }

  if (s_btnStable == BUTTON_PRESSED_LEVEL && !s_resetLatched) {
    // feedback: blink rapido del LED onboard durante el hold
    if (now - s_lastBlinkMs >= 100UL) {
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    if ((now - s_btnPressMs) >= RESET_HOLD_MS) {
      s_resetLatched = true;
      Serial.println(F("RESET_REQUEST"));   // <-- el lado Linux: fs_wifi.sh reset
      s_mode = MODE_AP; applyModeLeds();
    }
  }
}

void setup() {
  pinMode(PIN_LED_ONBOARD, OUTPUT); digitalWrite(PIN_LED_ONBOARD, LOW);
  pinMode(PIN_LED_GREEN,   OUTPUT);
  pinMode(PIN_LED_RED,     OUTPUT);
  pinMode(PIN_BUTTON_RESET, INPUT_PULLUP);

  Serial.begin(115200);
  if (!Bridge.begin()) Serial.println(F("ERR: Bridge.begin() fallo"));
  Monitor.begin(115200);
  unsigned long w = millis();
  while (!Monitor && (millis() - w) < 10000UL) {
    unsigned long now = millis();
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
    delay(10);
  }

  s_bootMs = millis();
  applyModeLeds();

  Serial.println(F("Boot OK - F4 (WiFi setup coordinator)"));
  Serial.print(F("  firmware = ")); Serial.println(F(FW_VERSION));
  Serial.println(F("  WiFi/AP/portal -> LADO LINUX (NetworkManager + brick web_ui)"));
  Serial.print(F("  AP SSID  = ")); Serial.println(F(AP_SSID));
  Serial.print(F("  portal   = http://")); Serial.print(F(AP_PORTAL_IP));
  Serial.print(F(":")); Serial.println(AP_PORTAL_PORT);
  Serial.println(F("  PINOUT: LED verde D5 | LED rojo D6 | boton reset D3 (hold 3 s)"));
  Serial.println(F("  comandos: MODE AP | MODE CLIENT | STATUS"));
  printStatus();
}

void loop() {
  const unsigned long now = millis();

  pollSerial();
  updateResetButton(now);

  // Blink "vivo" del LED onboard (salvo durante el hold del boton, que ya
  // parpadea rapido por su cuenta).
  if (!(s_btnStable == BUTTON_PRESSED_LEVEL && !s_resetLatched)) {
    if (now - s_lastBlinkMs >= BLINK_INTERVAL_MS) {
      s_lastBlinkMs = now; s_ledState = !s_ledState;
      digitalWrite(PIN_LED_ONBOARD, s_ledState ? HIGH : LOW);
    }
  }

  if (now - s_lastHbMs >= HEARTBEAT_INTERVAL_MS) {
    s_lastHbMs = now;
    Serial.print(F("[hb] F4 alive | uptime="));
    Serial.print((now - s_bootMs) / 1000UL);
    Serial.print(F(" s | mode="));
    Serial.println(s_mode == MODE_CLIENT ? F("CLIENT") : F("AP"));
  }
}

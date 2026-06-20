// ============================================================================
//  config.h  -  EMBEBIDOS_1 / face_security  (Arduino UNO Q)
//  Ing 2 - FASE 1
// ----------------------------------------------------------------------------
//  Punto unico de configuracion del firmware. TODO el "hardcoding"
//  (credenciales, IPs, puertos, tiempos y pines) vive aqui. Ningun otro
//  archivo debe contener valores magicos: si algo es ajustable, va en este
//  header.
//
//  NOTA sobre los pines: los numeros son PLACEHOLDERS razonables pensados
//  para la disposicion tipo UNO. Se confirmaran/ajustaran al cablear el
//  hardware real (Fases 2-4). Los pines de la camara OV7670 son tentativos
//  porque el mapeo definitivo depende de como el core (Zephyr) del UNO Q
//  exponga el bus de la camara (ver camera.h, riesgo critico de F3).
// ============================================================================

#ifndef FACE_SECURITY_CONFIG_H
#define FACE_SECURITY_CONFIG_H

// ----------------------------------------------------------------------------
//  WiFi - credenciales de operacion (modo Cliente)
//  Se sobreescriben en runtime con lo que el usuario guarde en EEPROM via el
//  portal web (Fase 4). Estos valores son solo el "defecto de fabrica".
// ----------------------------------------------------------------------------
#define WIFI_SSID_PRIMARY     "MiRedWiFi"          // SSID principal (placeholder)
#define WIFI_PASS_PRIMARY     "claveprincipal"     // Password principal
#define WIFI_SSID_BACKUP      "MiRedWiFi_Backup"   // SSID de respaldo
#define WIFI_PASS_BACKUP      "clavebackup"        // Password de respaldo

// ----------------------------------------------------------------------------
//  Servidor (PC con FastAPI - Ing 3). Destino del POST /verify.
// ----------------------------------------------------------------------------
#define SERVER_IP             "192.168.1.50"       // IP de la PC en la red local
#define SERVER_PORT           8000                 // Puerto del servidor FastAPI

// ----------------------------------------------------------------------------
//  Modo AP (configuracion inicial - Fase 4). El UNO Q levanta este AP en el
//  primer boot (o tras reset de fabrica) para que el usuario ingrese sus
//  redes WiFi desde el celular en 192.168.4.1.
// ----------------------------------------------------------------------------
#define AP_SSID               "FaceSecurity_Setup" // SSID del portal de setup
#define AP_PASS               "setup1234"          // Password del AP (>= 8 chars)

// ----------------------------------------------------------------------------
//  Tiempos / timeouts (milisegundos)
// ----------------------------------------------------------------------------
#define DEBOUNCE_MS           200    // Haz interrumpido >= 200 ms continuos = intrusion
#define HTTP_TIMEOUT_MS       5000   // Timeout de la peticion HTTP /verify
#define WIFI_TIMEOUT_MS       8000   // Timeout para conectar a una red WiFi

// Tiempo del blink de bring-up (Fase 1). El LED onboard alterna cada este
// intervalo para evidenciar que el firmware esta vivo.
#define BLINK_INTERVAL_MS     500

// Heartbeat de diagnostico (Fase 2): cada cuanto el main imprime una linea de
// estado por Serial (estado ARM/DISARM, haz, buzzer) cuando no hay eventos.
#define HEARTBEAT_INTERVAL_MS 5000

// Duracion por defecto de un pulso de buzzer (alerts::buzzerPulse sin argumento
// explicito y cualquier "beep" corto de feedback). No bloqueante.
#define BUZZER_PULSE_MS       150

// Tiempo que debe mantenerse pulsado el boton de reset para borrar EEPROM
// y volver a modo AP (Fase 4).
#define RESET_HOLD_MS         3000

// ----------------------------------------------------------------------------
//  PINES - Actuadores y entradas digitales
//  (numeros estilo UNO; se confirman al cablear)
// ----------------------------------------------------------------------------

// LED onboard para el blink de bring-up (Fase 1). LED_BUILTIN lo define el
// core; si el core del UNO Q no lo define, se cae a 13 (estandar UNO).
#ifndef LED_BUILTIN
#define LED_BUILTIN           13
#endif
#define PIN_LED_ONBOARD       LED_BUILTIN

// Sensor laser IR (Fase 2)
#define PIN_LASER_EMITTER     7      // Salida digital -> enciende el laser
#define PIN_LASER_RECEIVER    2      // Entrada (INPUT_PULLUP) -> receptor del haz
                                     // D2 elegido por soportar interrupciones en UNO

// Polaridad del receptor laser (Fase 2). Con un fototransistor/modulo receptor
// IR tipico + INPUT_PULLUP: haz PRESENTE satura el receptor y lleva el pin a
// nivel BAJO; haz INTERRUMPIDO suelta el pin y el pull-up lo lleva a ALTO.
// Por tanto "haz roto" = lectura == HIGH. Si el cableado real invierte esto,
// se cambia AQUI (no en el .cpp).
#define LASER_BEAM_BROKEN_LEVEL HIGH

// Nivel logico que activa el laser emisor (la mayoria de modulos laser/IR son
// activos en ALTO: HIGH enciende el diodo). Ajustar si el modulo es activo-bajo.
#define LASER_EMITTER_ON_LEVEL  HIGH

// Buzzer activo (Fase 2)
#define PIN_BUZZER            8      // Salida digital -> buzzer
#define BUZZER_ON_LEVEL       HIGH   // Nivel que hace sonar el buzzer activo
                                     // (activo-alto tipico; invertir si es activo-bajo)

// LEDs de estado (Fase 5)
#define PIN_LED_GREEN         5      // LED verde  -> acceso autorizado
#define PIN_LED_RED           6      // LED rojo   -> intruso / error de red

// Boton fisico de reset de configuracion (Fase 4)
#define PIN_BUTTON_RESET      3      // Entrada (INPUT_PULLUP); mantener > RESET_HOLD_MS

// ----------------------------------------------------------------------------
//  PINES - Camara OV7670 (Fase 3)  [PLACEHOLDERS]
//  El OV7670 es paralelo: 8 lineas de datos (D0-D7) + control (PCLK, HREF,
//  VSYNC, XCLK) + SCCB/I2C (SIOD/SDA, SIOC/SCL) + RESET + PWDN.
//  El mapeo REAL depende de DCMI/bus de camara del STM32U585 expuesto por el
//  core del UNO Q. Estos valores son provisionales y se ajustan en F3.
// ----------------------------------------------------------------------------
#define OV7670_D0             22     // Bus de datos paralelo (LSB)
#define OV7670_D1             23
#define OV7670_D2             24
#define OV7670_D3             25
#define OV7670_D4             26
#define OV7670_D5             27
#define OV7670_D6             28
#define OV7670_D7             29     // Bus de datos paralelo (MSB)
#define OV7670_PCLK           30     // Pixel clock (salida de la camara)
#define OV7670_HREF           31     // Horizontal reference
#define OV7670_VSYNC          32     // Vertical sync (inicio de frame)
#define OV7670_XCLK           33     // Master clock hacia la camara (8-24 MHz)
#define OV7670_SIOD           34     // SCCB data  (~ I2C SDA)
#define OV7670_SIOC           35     // SCCB clock (~ I2C SCL)
#define OV7670_RESET          36     // Reset de la camara (activo en bajo)
#define OV7670_PWDN           37     // Power-down de la camara

// Geometria de captura objetivo (Fase 3): QVGA 320x240, RGB565 (2 bytes/pixel)
#define CAM_FRAME_WIDTH       320
#define CAM_FRAME_HEIGHT      240
#define CAM_BYTES_PER_PIXEL   2
#define CAM_FRAME_BYTES       (CAM_FRAME_WIDTH * CAM_FRAME_HEIGHT * CAM_BYTES_PER_PIXEL) // 153600

#endif  // FACE_SECURITY_CONFIG_H

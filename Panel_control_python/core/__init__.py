"""
core/ — Lógica de orquestación del Panel de Control (EMBEBIDOS_1).

Cada módulo aquí encapsula UNA responsabilidad y NO importa CustomTkinter:
la GUI (app.py) los llama en hilos y recibe progreso por callbacks/cola.
Así los módulos son testeables sin abrir la ventana (verificación headless).

Módulos:
    paths           — rutas absolutas del proyecto (única fuente de verdad).
    netinfo         — IP local de la PC + heurística DHCP/estática.
    server_ctrl     — start/stop de uvicorn (Popen) + health-check GET /.
    devices         — detección de ESP32-CAM (COM) y UNO Q (adb).
    esp32_config    — flasheo del ESP32-CAM (pio run -t upload) con stream.
    unoq_config     — config WiFi+cloud.json del UNO Q por adb.
    telegram_wizard — asistente getMe → getUpdates → sendMessage → .env.
    guicfg          — persistencia de la config de la propia GUI.
"""

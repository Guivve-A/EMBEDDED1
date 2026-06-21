"""
app.py — Panel de Control (CustomTkinter) del sistema EMBEBIDOS_1.

GUI de escritorio "plug & play" que orquesta TODO el sistema:
    1. Servidor   — montar/desmontar uvicorn + health-check.
    2. Red        — IP local de la PC + copiar + guía de IP estática.
    3. Telegram   — wizard getMe -> chat_id -> prueba -> guardar .env.
    4. App        — instrucciones + QR con http://IP:8000.
    5. ESP32-CAM  — semáforo COM + flasheo (pio) con log en vivo.
    6. UNO Q      — semáforo ADB + config WiFi (2 redes) + cloud.json por adb.
    7. Log        — área desplegable "Mostrar registros" con timestamp.

Principios:
    - THREADING obligatorio: toda acción de I/O/red/subprocess corre en un hilo;
      el progreso se manda a la GUI por una cola (queue.Queue) que se vacía con
      after() en el hilo de Tk. La ventana NUNCA se congela.
    - Un hilo de detección sondea ESP32 (COM) y UNO Q (adb) cada ~3 s y actualiza
      semáforos + habilita/inhabilita los botones 5 y 6.
    - Look oscuro/moderno: paleta negro + oro (identidad visual del proyecto).

Lanzar:
    <venv_python> Panel_control_python\\app.py
"""

from __future__ import annotations

import queue
import threading
import webbrowser
from datetime import datetime
from typing import Callable

import customtkinter as ctk

from core import (
    devices,
    esp32_config,
    guicfg,
    netinfo,
    server_ctrl,
    system_ctrl,
    telegram_wizard,
    unoq_config,
)
from core import paths

# --------------------------------------------------------------------------- #
# Paleta (negro absoluto + oro), identidad visual del proyecto.
# --------------------------------------------------------------------------- #
COL_BG = "#0A0A0A"        # fondo de la ventana
COL_CARD = "#141414"      # tarjetas / paneles
COL_CARD_2 = "#1C1C1C"    # subzonas dentro de tarjeta
COL_GOLD = "#D4AF37"      # acento (oro)
COL_GOLD_DK = "#A6841C"   # oro oscuro (hover)
COL_TEXT = "#EAEAEA"      # texto principal
COL_MUTED = "#8A8A8A"     # texto secundario
COL_GREEN = "#2ECC71"     # semáforo OK
COL_RED = "#E74C3C"       # semáforo error/offline
COL_AMBER = "#F1C40F"     # semáforo en progreso
COL_GREY = "#555555"      # semáforo neutro/desconocido

PORT = 8000  # puerto estándar del servidor


# =========================================================================== #
# Widget reutilizable: un "panel" (tarjeta) con título, semáforo y cuerpo.
# =========================================================================== #
class Panel(ctk.CTkFrame):
    """
    Tarjeta con cabecera (semáforo + título + estado) y un cuerpo libre.

    El semáforo es un punto de color; set_status() cambia color + texto.
    El cuerpo (self.body) es un frame donde cada sección coloca sus controles.
    """

    def __init__(self, master, title: str, **kwargs):
        super().__init__(master, fg_color=COL_CARD, corner_radius=14, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        header.grid_columnconfigure(1, weight=1)

        # Semáforo (canvas con un círculo).
        self.dot = ctk.CTkCanvas(
            header, width=16, height=16, bg=COL_CARD, highlightthickness=0
        )
        self._dot_id = self.dot.create_oval(2, 2, 14, 14, fill=COL_GREY, outline="")
        self.dot.grid(row=0, column=0, padx=(0, 10))

        self.title_lbl = ctk.CTkLabel(
            header, text=title, font=("Inter", 16, "bold"), text_color=COL_GOLD
        )
        self.title_lbl.grid(row=0, column=1, sticky="w")

        self.status_lbl = ctk.CTkLabel(
            header, text="—", font=("Inter", 12), text_color=COL_MUTED
        )
        self.status_lbl.grid(row=0, column=2, sticky="e")

        # Cuerpo de la tarjeta.
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.body.grid_columnconfigure(0, weight=1)

    def set_status(self, color: str, text: str) -> None:
        """Cambia el color del semáforo y el texto de estado de la cabecera."""
        self.dot.itemconfig(self._dot_id, fill=color)
        self.status_lbl.configure(text=text)


# =========================================================================== #
# Aplicación principal
# =========================================================================== #
class PanelControlApp(ctk.CTk):
    """Ventana raíz del Panel de Control."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("EMBEBIDOS_1 — Panel de Control")
        self.geometry("1180x820")
        self.minsize(1000, 700)
        self.configure(fg_color=COL_BG)

        # Estado runtime.
        self.cfg = guicfg.load()
        self.server = server_ctrl.ServerController(host="127.0.0.1", port=PORT)
        self.flasher = esp32_config.Esp32Flasher()
        self.esp32_status = devices.Esp32Status()
        self.unoq_status = devices.UnoqStatus()
        self._busy_server = False
        self._busy_esp32 = False
        self._busy_unoq = False

        # Cola de mensajes hilo -> GUI (log + callbacks de UI).
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        self.local_ip = netinfo.local_ip()

        self._build_layout()
        self._start_queue_pump()
        self._start_detection_loop()
        self._start_wifi_loop()
        self._refresh_server_status_async()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --------------------------------------------------------------------- #
    # Construcción del layout
    # --------------------------------------------------------------------- #
    def _build_layout(self) -> None:
        """Arma el header, el grid de paneles (scrollable) y el área de log."""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="EMBEBIDOS_1 · Panel de Control",
            font=("Inter", 24, "bold"),
            text_color=COL_GOLD,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Sistema de seguridad: servidor IA · ESP32-CAM · Arduino UNO Q · App",
            font=("Inter", 13),
            text_color=COL_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        # --- Zona scrollable con los paneles en 2 columnas ---
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=6)
        scroll.grid_columnconfigure(0, weight=1, uniform="col")
        scroll.grid_columnconfigure(1, weight=1, uniform="col")

        self.p_server = Panel(scroll, "1 · Servidor")
        self.p_net = Panel(scroll, "2 · Red")
        self.p_tg = Panel(scroll, "3 · Telegram")
        self.p_app = Panel(scroll, "4 · App Android")
        self.p_esp = Panel(scroll, "5 · ESP32-CAM")
        self.p_unoq = Panel(scroll, "6 · Arduino UNO Q")

        self.p_server.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.p_net.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.p_tg.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.p_app.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)
        self.p_esp.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.p_unoq.grid(row=2, column=1, sticky="nsew", padx=8, pady=8)

        self._build_server_panel()
        self._build_net_panel()
        self._build_telegram_panel()
        self._build_app_panel()
        self._build_esp32_panel()
        self._build_unoq_panel()

        # --- Área de log (7) ---
        self._build_log_area()

    def _gold_button(self, master, text, command, **kw):
        """Botón con el acento oro del proyecto."""
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            fg_color=COL_GOLD,
            hover_color=COL_GOLD_DK,
            text_color="#0A0A0A",
            font=("Inter", 13, "bold"),
            corner_radius=10,
            height=38,
            **kw,
        )

    def _ghost_button(self, master, text, command, **kw):
        """Botón secundario (borde oro, fondo oscuro)."""
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            fg_color=COL_CARD_2,
            hover_color="#262626",
            text_color=COL_TEXT,
            border_color=COL_GOLD,
            border_width=1,
            font=("Inter", 13),
            corner_radius=10,
            height=38,
            **kw,
        )

    # ---- Panel 1: Servidor ------------------------------------------------ #
    def _build_server_panel(self) -> None:
        b = self.p_server.body
        self.p_server.set_status(COL_GREY, "comprobando…")
        ctk.CTkLabel(
            b,
            text="Levanta el servidor FastAPI (reconocimiento facial + alertas).",
            font=("Inter", 12),
            text_color=COL_MUTED,
            wraplength=460,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        btns = ctk.CTkFrame(b, fg_color="transparent")
        btns.grid(row=1, column=0, columnspan=2, sticky="ew")
        btns.grid_columnconfigure((0, 1), weight=1)
        self.btn_server_up = self._gold_button(btns, "Montar servidor", self._on_server_up)
        self.btn_server_down = self._ghost_button(btns, "Desmontar servidor", self._on_server_down)
        self.btn_server_up.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.btn_server_down.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.pb_server = ctk.CTkProgressBar(b, progress_color=COL_GOLD)
        self.pb_server.set(0)
        self.pb_server.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.lbl_server_url = ctk.CTkLabel(
            b, text=f"http://{self.local_ip}:{PORT}", font=("Inter", 12), text_color=COL_TEXT
        )
        self.lbl_server_url.grid(row=3, column=0, columnspan=2, sticky="w")

        # --- Control de vigilancia (Armar / Desarmar) ---
        ctk.CTkLabel(
            b, text="Vigilancia del sistema:", font=("Inter", 11), text_color=COL_MUTED
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 2))
        arm_row = ctk.CTkFrame(b, fg_color="transparent")
        arm_row.grid(row=5, column=0, columnspan=2, sticky="ew")
        arm_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_arm = self._gold_button(arm_row, "Armar vigilancia", self._on_arm)
        self.btn_disarm = self._ghost_button(arm_row, "Desarmar (reposo)", self._on_disarm)
        self.btn_arm.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.btn_disarm.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # ---- Panel 2: Red (consciente de WiFi) -------------------------------- #
    def _build_net_panel(self) -> None:
        b = self.p_net.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(1, weight=1)
        self.p_net.set_status(COL_GREY, "detectando WiFi…")

        # Snapshot de WiFi en vivo (lo rellena el hilo de monitoreo).
        self._wifi: dict = {}

        # --- SSID + banda actuales ---
        ctk.CTkLabel(b, text="Red WiFi actual de esta PC:",
                     font=("Inter", 12), text_color=COL_MUTED).grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.lbl_ssid = ctk.CTkLabel(b, text="…",
                                     font=("Inter", 18, "bold"), text_color=COL_GOLD)
        self.lbl_ssid.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.lbl_band = ctk.CTkLabel(b, text="banda: —",
                                     font=("Inter", 12), text_color=COL_MUTED)
        self.lbl_band.grid(row=2, column=0, columnspan=2, sticky="w")

        # --- IP local ---
        ctk.CTkLabel(b, text="IP de esta PC en la red local:",
                     font=("Inter", 12), text_color=COL_MUTED).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.lbl_ip = ctk.CTkLabel(b, text=self.local_ip,
                                   font=("Inter", 22, "bold"), text_color=COL_GOLD)
        self.lbl_ip.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # --- Aviso de banda (5 GHz / desconocida) ---
        self.lbl_band_warn = ctk.CTkLabel(
            b, text="", font=("Inter", 11, "bold"), text_color=COL_AMBER,
            wraplength=460, justify="left")
        self.lbl_band_warn.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # --- Banner de incoherencia (cambio de red) ---
        self.lbl_coherence = ctk.CTkLabel(
            b, text="", font=("Inter", 11, "bold"), text_color=COL_RED,
            wraplength=460, justify="left")
        self.lbl_coherence.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # --- Botonera 1 ---
        row_btns = ctk.CTkFrame(b, fg_color="transparent")
        row_btns.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        row_btns.grid_columnconfigure((0, 1), weight=1)
        self._ghost_button(row_btns, "Copiar IP", self._on_copy_ip).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        self._ghost_button(row_btns, "Refrescar red", self._on_refresh_net).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))

        # --- Botonera 2 ---
        row_btns2 = ctk.CTkFrame(b, fg_color="transparent")
        row_btns2.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        row_btns2.grid_columnconfigure((0, 1), weight=1)
        self._ghost_button(
            row_btns2, "Marcar esta red como la de los dispositivos",
            self._on_mark_work_net).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._ghost_button(
            row_btns2, "¿Cómo poner todo en la misma red?",
            self._on_show_net_guide).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # --- Botonera 3: probar alcance ---
        row_btns3 = ctk.CTkFrame(b, fg_color="transparent")
        row_btns3.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        row_btns3.grid_columnconfigure(0, weight=0)
        row_btns3.grid_columnconfigure(1, weight=1)
        self._ghost_button(row_btns3, "Probar alcance", self._on_ping_device).grid(
            row=0, column=0, sticky="w")
        self.lbl_ping = ctk.CTkLabel(b, text="", font=("Inter", 11),
                                     text_color=COL_MUTED, wraplength=460,
                                     justify="left")
        self.lbl_ping.grid(row=10, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Pinta el primer estado de forma síncrona (no bloquea: netsh es rápido,
        # pero el refresco continuo lo hace el hilo dedicado).
        try:
            self._apply_wifi(netinfo.current_wifi())
        except Exception:  # noqa: BLE001 — nunca romper el arranque de la GUI
            pass

    # ---- Panel 3: Telegram (wizard) -------------------------------------- #
    def _build_telegram_panel(self) -> None:
        b = self.p_tg.body
        self.p_tg.set_status(COL_GREY, "sin validar")
        self._tg_token_ok = False
        self._tg_chat_ok = False
        self._tg_test_ok = False

        ctk.CTkLabel(b, text="TOKEN del bot (de @BotFather):",
                     font=("Inter", 12), text_color=COL_MUTED).grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.ent_tg_token = ctk.CTkEntry(
            b, placeholder_text="123456:ABC-DEF...", show="•",
            fg_color=COL_CARD_2, border_color=COL_GREY, text_color=COL_TEXT)
        if self.cfg.get("telegram_token"):
            self.ent_tg_token.insert(0, self.cfg["telegram_token"])
        self.ent_tg_token.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 8))

        self.btn_tg_validate = self._gold_button(b, "1 · Validar bot", self._on_tg_validate)
        self.btn_tg_validate.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.lbl_tg_bot = ctk.CTkLabel(b, text="", font=("Inter", 12), text_color=COL_GREEN)
        self.lbl_tg_bot.grid(row=2, column=1, columnspan=2, sticky="w", padx=(6, 0))

        ctk.CTkLabel(
            b, text="Abre Telegram, busca tu bot y envíale cualquier mensaje. Luego:",
            font=("Inter", 11), text_color=COL_MUTED, wraplength=460, justify="left"
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 4))

        self.btn_tg_chat = self._ghost_button(b, "2 · Detectar mi chat", self._on_tg_chat)
        self.btn_tg_chat.grid(row=4, column=0, sticky="ew", padx=(0, 4))
        self.lbl_tg_chat = ctk.CTkLabel(b, text="", font=("Inter", 12), text_color=COL_GREEN)
        self.lbl_tg_chat.grid(row=4, column=1, columnspan=2, sticky="w", padx=(6, 0))

        row5 = ctk.CTkFrame(b, fg_color="transparent")
        row5.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        row5.grid_columnconfigure((0, 1), weight=1)
        self.btn_tg_test = self._ghost_button(row5, "3 · Enviar prueba", self._on_tg_test)
        self.btn_tg_save = self._gold_button(row5, "4 · Guardar en .env", self._on_tg_save)
        self.btn_tg_test.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.btn_tg_save.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # ---- Panel 4: App Android (con QR) ----------------------------------- #
    def _build_app_panel(self) -> None:
        b = self.p_app.body
        self.p_app.set_status(COL_GOLD, "instrucciones")
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(1, weight=0)

        steps = (
            "1. Instala el APK en el teléfono:\n"
            "   app/build/outputs/apk/debug/app-debug.apk\n"
            "2. Conecta el teléfono a la MISMA red WiFi que esta PC.\n"
            f"3. En la app: Ajustes → IP del servidor → {self.local_ip}:{PORT}\n"
            "4. Escanea el QR para abrir la URL del servidor."
        )
        ctk.CTkLabel(b, text=steps, font=("Inter", 12), text_color=COL_TEXT,
                     wraplength=300, justify="left").grid(
            row=0, column=0, sticky="nw")

        self.qr_canvas = ctk.CTkCanvas(b, width=140, height=140, bg=COL_CARD,
                                       highlightthickness=0)
        self.qr_canvas.grid(row=0, column=1, sticky="ne", padx=(8, 0))
        self._render_qr()

        self._ghost_button(b, "Copiar ruta del APK", self._on_copy_apk).grid(
            row=1, column=0, sticky="w", pady=(10, 0))

    def _render_qr(self) -> None:
        """Dibuja un QR con http://IP:PORT en el canvas (si qrcode está disponible)."""
        url = f"http://{self.local_ip}:{PORT}"
        try:
            import qrcode

            qr = qrcode.QRCode(border=1, box_size=4)
            qr.add_data(url)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            n = len(matrix)
            size = 140
            cell = size / n
            self.qr_canvas.delete("all")
            self.qr_canvas.create_rectangle(0, 0, size, size, fill="#FFFFFF", outline="")
            for r, rowv in enumerate(matrix):
                for c, val in enumerate(rowv):
                    if val:
                        x0, y0 = c * cell, r * cell
                        self.qr_canvas.create_rectangle(
                            x0, y0, x0 + cell, y0 + cell, fill="#000000", outline="")
        except Exception:
            # Sin qrcode o error: muestra la URL como texto (degradación elegante).
            self.qr_canvas.delete("all")
            self.qr_canvas.create_text(
                70, 70, width=130, text=url, fill=COL_GOLD, font=("Inter", 9))

    def _status_row(self, master, row, prefix):
        """Crea una fila 'mini-semáforo + etiqueta' y devuelve (canvas, dot_id, lbl)."""
        rowf = ctk.CTkFrame(master, fg_color="transparent")
        rowf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        dot = ctk.CTkCanvas(rowf, width=14, height=14, bg=COL_CARD,
                            highlightthickness=0)
        dot_id = dot.create_oval(2, 2, 12, 12, fill=COL_GREY, outline="")
        dot.grid(row=0, column=0, padx=(0, 8))
        lbl = ctk.CTkLabel(rowf, text=f"{prefix}: —", font=("Inter", 11),
                           text_color=COL_MUTED, anchor="w")
        lbl.grid(row=0, column=1, sticky="w")
        return dot, dot_id, lbl

    def _set_mini_dot(self, dot, dot_id, lbl, color, text):
        """Pinta un mini-semáforo (color + texto)."""
        dot.itemconfig(dot_id, fill=color)
        lbl.configure(text=text)

    # ---- Panel 5: ESP32-CAM ---------------------------------------------- #
    def _build_esp32_panel(self) -> None:
        b = self.p_esp.body
        self.p_esp.set_status(COL_GREY, "detectando…")
        ctk.CTkLabel(
            b, text="Detecta el ESP32-CAM por USB y flashea su firmware.",
            font=("Inter", 12), text_color=COL_MUTED, wraplength=460, justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # Semáforos: USB (detección por COM) + Red (heartbeat al servidor).
        self.esp_usb_dot, self.esp_usb_id, self.esp_usb_lbl = self._status_row(
            b, 1, "USB")
        self.esp_net_dot, self.esp_net_id, self.esp_net_lbl = self._status_row(
            b, 2, "Red")

        self.btn_esp_flash = self._gold_button(
            b, "Configurar / Flashear ESP32", self._on_esp_flash)
        self.btn_esp_flash.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_esp_flash.configure(state="disabled")

        self.btn_esp_reset = self._ghost_button(
            b, "Resetear WiFi (forzar portal)", self._on_esp_reset_wifi)
        self.btn_esp_reset.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_esp_reset.configure(state="disabled")

        self.btn_esp_intrusion = self._gold_button(
            b, "Validar Intruso", self._on_esp_trigger_intrusion)
        self.btn_esp_intrusion.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.pb_esp = ctk.CTkProgressBar(b, progress_color=COL_GOLD, mode="determinate")
        self.pb_esp.set(0)
        self.pb_esp.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    # ---- Panel 6: Arduino UNO Q ------------------------------------------ #
    def _build_unoq_panel(self) -> None:
        b = self.p_unoq.body
        self.p_unoq.set_status(COL_GREY, "detectando…")
        ctk.CTkLabel(
            b, text="Configura WiFi (2 redes) + IP del servidor en el UNO Q (por ADB).",
            font=("Inter", 12), text_color=COL_MUTED, wraplength=460, justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # Semáforos: USB/ADB (detección) + Red (heartbeat al servidor).
        self.unoq_usb_dot, self.unoq_usb_id, self.unoq_usb_lbl = self._status_row(
            b, 1, "USB")
        self.unoq_net_dot, self.unoq_net_id, self.unoq_net_lbl = self._status_row(
            b, 2, "Red")

        # Pre-rellena SSID 1 con la red WiFi actual de la PC (si la hay); si el
        # usuario ya guardó uno antes, ese tiene prioridad.
        try:
            cur_ssid = netinfo.current_wifi().get("ssid", "") or ""
        except Exception:  # noqa: BLE001 — nunca romper el arranque de la GUI
            cur_ssid = ""
        ssid1_default = self.cfg.get("unoq_ssid1", "") or cur_ssid

        self.ent_ssid1 = self._labeled_entry(b, 3, "Red WiFi 1 (SSID):", ssid1_default)
        self.ent_pass1 = self._labeled_entry(b, 4, "Contraseña 1:", "", show="•")
        self.ent_ssid2 = self._labeled_entry(b, 5, "Red WiFi 2 (opcional):",
                                             self.cfg.get("unoq_ssid2", ""))
        self.ent_pass2 = self._labeled_entry(b, 6, "Contraseña 2 (opcional):", "", show="•")

        self.btn_unoq_cfg = self._gold_button(b, "Configurar Arduino Q", self._on_unoq_config)
        self.btn_unoq_cfg.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.btn_unoq_cfg.configure(state="disabled")

        self.pb_unoq = ctk.CTkProgressBar(b, progress_color=COL_GOLD)
        self.pb_unoq.set(0)
        self.pb_unoq.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _labeled_entry(self, master, row, label, value, show=None):
        """Helper: etiqueta + entry en una fila del grid del cuerpo."""
        ctk.CTkLabel(master, text=label, font=("Inter", 11), text_color=COL_MUTED).grid(
            row=row, column=0, sticky="w", pady=(2, 0))
        ent = ctk.CTkEntry(master, fg_color=COL_CARD_2, border_color=COL_GREY,
                           text_color=COL_TEXT, show=show or "")
        if value:
            ent.insert(0, value)
        ent.grid(row=row, column=1, sticky="ew", pady=(2, 0), padx=(8, 0))
        master.grid_columnconfigure(1, weight=1)
        return ent

    # ---- Panel 7: Log ----------------------------------------------------- #
    def _build_log_area(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(2, 0))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text="Registros", font=("Inter", 14, "bold"),
                     text_color=COL_GOLD).grid(row=0, column=0, sticky="w")
        self._log_visible = True
        self.btn_log_toggle = self._ghost_button(bar, "Ocultar registros", self._on_toggle_log)
        self.btn_log_toggle.configure(width=160)
        self.btn_log_toggle.grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(
            self, fg_color="#0D0D0D", text_color="#CFCFCF", font=("Consolas", 11),
            height=180, border_color=COL_GREY, border_width=1)
        self.log_box.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 16))
        self.log_box.configure(state="disabled")
        self.log("Panel de Control iniciado.")
        self.log(f"IP local detectada: {self.local_ip}")

    # --------------------------------------------------------------------- #
    # Infraestructura de threading: cola hilo -> GUI
    # --------------------------------------------------------------------- #
    def _post(self, fn: Callable[[], None]) -> None:
        """Encola una función para ejecutarla en el hilo de Tk (thread-safe)."""
        self._ui_queue.put(fn)

    def _start_queue_pump(self) -> None:
        """Vacía la cola periódicamente en el hilo de Tk (cada 60 ms)."""
        def pump():
            try:
                while True:
                    fn = self._ui_queue.get_nowait()
                    try:
                        fn()
                    except Exception as exc:  # noqa: BLE001
                        self._append_log(f"[UI] error procesando evento: {exc}")
            except queue.Empty:
                pass
            self.after(60, pump)
        self.after(60, pump)

    def log(self, msg: str) -> None:
        """Log thread-safe: encola la escritura en el textbox."""
        self._post(lambda: self._append_log(msg))

    def _append_log(self, msg: str) -> None:
        """Escribe una línea con timestamp en el textbox (hilo de Tk)."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # --------------------------------------------------------------------- #
    # Hilo de detección de dispositivos (cada ~3 s)
    # --------------------------------------------------------------------- #
    def _start_detection_loop(self) -> None:
        """Lanza el hilo demonio que sondea ESP32 (COM) y UNO Q (adb)."""
        self._detect_stop = threading.Event()
        t = threading.Thread(target=self._detection_worker, daemon=True)
        t.start()

    def _detection_worker(self) -> None:
        """Sondea dispositivos (USB) + estado de Red y publica a la GUI por la cola."""
        while not self._detect_stop.is_set():
            esp = devices.detect_esp32()
            unoq = devices.detect_unoq()
            self._post(lambda e=esp, u=unoq: self._apply_device_status(e, u))
            # Semáforo de Red: estado de heartbeat de cada dispositivo vía servidor.
            net = devices.network_status(timeout=2.0)
            self._post(lambda n=net: self._apply_network_status(n))
            self._detect_stop.wait(3.0)

    def _apply_device_status(self, esp: devices.Esp32Status, unoq: devices.UnoqStatus) -> None:
        """Actualiza semáforos USB 5/6 y habilita/inhabilita sus botones (hilo Tk)."""
        self.esp32_status = esp
        self.unoq_status = unoq

        # ESP32-CAM — semáforo USB (detección por COM)
        if esp.online:
            self.p_esp.set_status(COL_GREEN, f"Conectado ({esp.port})")
            self._set_mini_dot(self.esp_usb_dot, self.esp_usb_id, self.esp_usb_lbl,
                               COL_GREEN, f"USB: Conectado ({esp.port})")
            if not self._busy_esp32:
                self.btn_esp_flash.configure(state="normal")
                self.btn_esp_reset.configure(state="normal")
        else:
            self.p_esp.set_status(COL_RED, "Desconectado")
            self._set_mini_dot(self.esp_usb_dot, self.esp_usb_id, self.esp_usb_lbl,
                               COL_RED, "USB: Desconectado")
            if not self._busy_esp32:
                self.btn_esp_flash.configure(state="disabled")
                self.btn_esp_reset.configure(state="disabled")

        # UNO Q — semáforo USB/ADB (detección)
        if unoq.online:
            self.p_unoq.set_status(COL_GREEN, "Conectado (ADB)")
            self._set_mini_dot(self.unoq_usb_dot, self.unoq_usb_id, self.unoq_usb_lbl,
                               COL_GREEN, "USB: Conectado (ADB)")
            if not self._busy_unoq:
                self.btn_unoq_cfg.configure(state="normal")
        else:
            self.p_unoq.set_status(COL_RED, "Desconectado")
            self._set_mini_dot(self.unoq_usb_dot, self.unoq_usb_id, self.unoq_usb_lbl,
                               COL_RED, "USB: Desconectado")
            if not self._busy_unoq:
                self.btn_unoq_cfg.configure(state="disabled")

    def _apply_network_status(self, net: dict) -> None:
        """Pinta los semáforos de Red de ESP32/UNO Q desde devices.network_status()."""
        if net.get("_server_down"):
            for dot, did, lbl in (
                (self.esp_net_dot, self.esp_net_id, self.esp_net_lbl),
                (self.unoq_net_dot, self.unoq_net_id, self.unoq_net_lbl),
            ):
                self._set_mini_dot(dot, did, lbl, COL_GREY, "Red: servidor apagado")
            return

        mapping = (
            ("esp32cam", self.esp_net_dot, self.esp_net_id, self.esp_net_lbl),
            ("unoq", self.unoq_net_dot, self.unoq_net_id, self.unoq_net_lbl),
        )
        for key, dot, did, lbl in mapping:
            info = net.get(key, {}) or {}
            if info.get("online"):
                rssi = info.get("wifi_rssi")
                txt = f"Red: online (RSSI {rssi})" if rssi is not None else "Red: online"
                self._set_mini_dot(dot, did, lbl, COL_GREEN, txt)
            else:
                self._set_mini_dot(dot, did, lbl, COL_RED, "Red: sin conexión")

    # --------------------------------------------------------------------- #
    # Panel 1: Servidor — acciones
    # --------------------------------------------------------------------- #
    def _refresh_server_status_async(self) -> None:
        """Comprueba en un hilo si el server ya está sano (al abrir la GUI)."""
        def work():
            healthy = server_ctrl.is_healthy("127.0.0.1", PORT, timeout=1.5)
            self._post(lambda: self._set_server_ui(healthy))
        threading.Thread(target=work, daemon=True).start()

    def _set_server_ui(self, active: bool) -> None:
        """Pinta el semáforo del servidor según esté activo o no."""
        if active:
            self.p_server.set_status(COL_GREEN, "Activo")
            self.pb_server.set(1.0)
            self.lbl_server_url.configure(
                text=f"Activo en http://{self.local_ip}:{PORT}", text_color=COL_GREEN)
        else:
            self.p_server.set_status(COL_RED, "Detenido")
            self.pb_server.set(0.0)
            self.lbl_server_url.configure(
                text=f"Detenido — http://{self.local_ip}:{PORT}", text_color=COL_MUTED)

    def _on_server_up(self) -> None:
        if self._busy_server:
            return
        self._busy_server = True
        self.btn_server_up.configure(state="disabled")
        self.btn_server_down.configure(state="disabled")
        self.p_server.set_status(COL_AMBER, "iniciando…")
        self.pb_server.configure(mode="indeterminate")
        self.pb_server.start()
        self.log("Montando servidor…")

        def work():
            ok = self.server.start(on_log=self.log, health_timeout=60.0, bind_host="0.0.0.0")
            def finish():
                self.pb_server.stop()
                self.pb_server.configure(mode="determinate")
                self._set_server_ui(ok)
                self._busy_server = False
                self.btn_server_up.configure(state="normal")
                self.btn_server_down.configure(state="normal")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_server_down(self) -> None:
        if self._busy_server:
            return
        self._busy_server = True
        self.btn_server_up.configure(state="disabled")
        self.btn_server_down.configure(state="disabled")
        self.p_server.set_status(COL_AMBER, "deteniendo…")
        self.log("Desmontando servidor…")

        def work():
            self.server.stop(on_log=self.log)
            def finish():
                self._set_server_ui(False)
                self._busy_server = False
                self.btn_server_up.configure(state="normal")
                self.btn_server_down.configure(state="normal")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_arm(self) -> None:
        self._system_set(True)

    def _on_disarm(self) -> None:
        self._system_set(False)

    def _system_set(self, armed: bool) -> None:
        """Arma/Desarma la vigilancia vía el servidor (en un hilo, sin congelar)."""
        self.btn_arm.configure(state="disabled")
        self.btn_disarm.configure(state="disabled")
        self.log("Armando vigilancia…" if armed else "Desarmando (sistema en reposo)…")

        def work():
            ok, info = (system_ctrl.arm(port=PORT) if armed
                        else system_ctrl.disarm(port=PORT))
            def finish():
                self.btn_arm.configure(state="normal")
                self.btn_disarm.configure(state="normal")
                self.log(("✓ " if ok else "✗ ") + info)
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------------------- #
    # Panel 2: Red — monitoreo WiFi + acciones
    # --------------------------------------------------------------------- #
    def _start_wifi_loop(self) -> None:
        """Hilo demonio que sondea la WiFi (~4 s) y publica cambios a la GUI."""
        self._wifi_stop = threading.Event()
        self._wifi_last_key: tuple | None = None
        t = threading.Thread(target=self._wifi_worker, daemon=True)
        t.start()

    def _wifi_worker(self) -> None:
        """Sondea netsh y, solo si cambió SSID/IP/banda, actualiza la UI."""
        while not self._wifi_stop.is_set():
            try:
                info = netinfo.current_wifi()
            except Exception as exc:  # noqa: BLE001 — nunca romper el hilo
                info = {"connected": False, "error": str(exc),
                        "ip": self.local_ip, "ssid": "", "band": "desconocida"}
            key = (info.get("ssid", ""), info.get("ip", ""), info.get("band", ""),
                   info.get("connected", False))
            if key != self._wifi_last_key:
                self._wifi_last_key = key
                self._post(lambda i=info: self._apply_wifi(i, announce=True))
            self._wifi_stop.wait(4.0)

    def _apply_wifi(self, info: dict, announce: bool = False) -> None:
        """
        Pinta SIEMPRE la red actual con sus parámetros (SSID, banda, señal, IP).

        Nunca muestra estados negativos ('sin WiFi'/'desconocida'): netinfo cachea
        la última red válida, así que aquí asumimos red activa y mostramos lo que
        haya, con respaldo al último SSID conocido si una lectura viene incompleta.
        """
        self._wifi = info
        ssid = info.get("ssid", "") or ""
        band = info.get("band", "") or ""
        ip = info.get("ip", "") or self.local_ip

        # Recordar el último SSID real para no mostrar jamás un valor vacío.
        if ssid:
            self._last_ssid = ssid
        ssid_show = ssid or getattr(self, "_last_ssid", "") or "Red local"

        # Mantener self.local_ip y los paneles dependientes sincronizados.
        prev_ip = self.local_ip
        self.local_ip = ip

        self.lbl_ssid.configure(text=ssid_show)
        sig = info.get("signal", "")
        radio = info.get("radio", "")
        extra = " · ".join(x for x in (band, (f"señal {sig}" if sig else ""),
                                       radio) if x)
        self.lbl_band.configure(text=f"banda: {extra}" if extra else "banda: WiFi")
        self.lbl_ip.configure(text=ip)

        # Si la IP cambió, refrescar URL del servidor, QR y panel App.
        if ip != prev_ip:
            try:
                self.lbl_server_url.configure(text=f"http://{ip}:{PORT}")
                self._render_qr()
            except Exception:  # noqa: BLE001
                pass

        # --- Semáforo de banda: SIEMPRE en positivo (hay red) ---
        if band == "2.4 GHz":
            self.p_net.set_status(COL_GREEN, "2.4 GHz OK")
            self.lbl_band_warn.configure(text="", text_color=COL_AMBER)
        elif band == "5 GHz":
            self.p_net.set_status(COL_AMBER, "5 GHz")
            self.lbl_band_warn.configure(
                text="ℹ El ESP32-CAM solo usa 2.4 GHz. Si los dispositivos no "
                     "conectan, pasa esta PC a la red de 2.4 GHz.",
                text_color=COL_AMBER)
        else:
            # El driver no reportó banda pero hay red: estado positivo, sin avisos.
            self.p_net.set_status(COL_GREEN, "conectado")
            self.lbl_band_warn.configure(text="", text_color=COL_AMBER)

        # --- Detección de incoherencia con la "red de trabajo" ---
        self._update_coherence_banner(ssid_show, ip)

        if announce:
            self.log(f"Red: {ssid_show} · {band or 'WiFi'} · IP {ip}")

    def _update_coherence_banner(self, ssid: str, ip: str) -> None:
        """Compara la red actual con la 'red de trabajo' guardada y avisa."""
        cfg = guicfg.load()
        work_ssid = cfg.get("work_ssid", "")
        work_ip = cfg.get("work_server_ip", "")
        if not work_ssid and not work_ip:
            self.lbl_coherence.configure(text="")  # nunca se marcó una red
            return
        differs = (work_ssid and ssid and ssid != work_ssid) or \
                  (work_ip and ip and ip != work_ip)
        if differs:
            self.lbl_coherence.configure(
                text=(f"⚠ Cambiaste de red (antes: {work_ssid or '?'} / IP "
                      f"{work_ip or '?'}; ahora: {ssid or '?'} / IP {ip or '?'}). "
                      "Reconfigura el ESP32 y el UNO Q para esta red."),
                text_color=COL_RED)
        else:
            self.lbl_coherence.configure(
                text=f"✓ Red coherente con la de los dispositivos ({work_ssid}).",
                text_color=COL_GREEN)

    def _register_work_net(self) -> None:
        """Guarda la red actual como 'red de trabajo' (ssid + IP servidor)."""
        ssid = (self._wifi.get("ssid", "") if self._wifi else "") \
            or getattr(self, "_last_ssid", "")
        guicfg.update(work_ssid=ssid, work_server_ip=self.local_ip)

    def _on_mark_work_net(self) -> None:
        self._register_work_net()
        ssid = (self._wifi.get("ssid", "") if self._wifi else "") \
            or getattr(self, "_last_ssid", "") or "Red local"
        self.log(f"Red de trabajo marcada: {ssid} / IP {self.local_ip}")
        self._update_coherence_banner(ssid, self.local_ip)

    def _on_copy_ip(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.local_ip)
        self.log(f"IP copiada al portapapeles: {self.local_ip}")

    def _on_refresh_net(self) -> None:
        """Refresco manual inmediato de la info de red (en un hilo)."""
        self.log("Refrescando red…")

        def work():
            info = netinfo.current_wifi()
            self._post(lambda: self._apply_wifi(info, announce=True))
        threading.Thread(target=work, daemon=True).start()

    def _on_show_net_guide(self) -> None:
        """Muestra una ventana modal con la guía de coherencia de red."""
        win = ctk.CTkToplevel(self)
        win.title("¿Cómo poner todo en la misma red?")
        win.geometry("620x520")
        win.configure(fg_color=COL_BG)
        win.transient(self)
        try:
            win.grab_set()
        except Exception:  # noqa: BLE001
            pass
        frame = ctk.CTkScrollableFrame(win, fg_color=COL_CARD)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        guide = (
            "OBJETIVO: PC, ESP32-CAM y Arduino UNO Q deben estar en la MISMA red "
            "WiFi de 2.4 GHz para que se vean entre sí.\n\n"
            "El ESP32-CAM SOLO funciona en 2.4 GHz. Si tu PC está en una red de "
            "5 GHz (p. ej. una 'XXX-5G') o en una red distinta, los dispositivos "
            "no podrán llegar al servidor (verás 'host unreachable').\n\n"
            "PASO A · Misma red 2.4 GHz\n"
            "  • Conecta la PC, el ESP32 y el UNO Q a la MISMA red de 2.4 GHz.\n"
            "  • Muchos routers separan la 2.4 GHz y la 5 GHz con sufijos como "
            "'-5G' o '-Plus'. Elige la de 2.4 GHz en la PC.\n\n"
            "PASO B · Al cambiar de red, reconfigura la IP del servidor\n"
            "  Cuando la PC cambia de red, su IP cambia y la que los dispositivos "
            "tienen grabada deja de servir. Tienes dos opciones:\n\n"
            "  OPCIÓN A — sin reflashear (rápida):\n"
            "    • ESP32-CAM: conéctate a su portal AP 'FaceCam_Setup' y actualiza "
            "WiFi + IP del servidor (la IP del servidor vive en NVS del ESP32).\n"
            "    • UNO Q: abre su portal / o reconfigúralo y pon la nueva WiFi e IP.\n\n"
            "  OPCIÓN B — desde esta GUI:\n"
            "    • Usa el panel 5 (ESP32-CAM) y el panel 6 (UNO Q) para reflashear/"
            "reconfigurar; la GUI inyecta automáticamente la IP actual de la PC "
            f"({self.local_ip}).\n\n"
            "CONSEJO: fija una IP ESTÁTICA para la PC en tu router (sugerencia en "
            f"tu red: {netinfo.suggest_static(self.local_ip)}) y vuelve a marcar "
            "'esta red como la de los dispositivos' tras configurarlos."
        )
        ctk.CTkLabel(frame, text=guide, font=("Inter", 12), text_color=COL_TEXT,
                     wraplength=540, justify="left").pack(anchor="w", padx=8, pady=8)
        self._gold_button(win, "Entendido", win.destroy).pack(pady=(0, 14))

    def _on_ping_device(self) -> None:
        """Hace ping a una IP de dispositivo conocida (guicfg.device_ip)."""
        cfg = guicfg.load()
        target = cfg.get("device_ip", "").strip()
        if not target:
            self.lbl_ping.configure(
                text="No hay IP de dispositivo conocida. Configura el ESP32/UNO Q "
                     "o anota su IP para probar el alcance.",
                text_color=COL_MUTED)
            self.log("Probar alcance: no hay IP de dispositivo guardada.")
            return
        self.lbl_ping.configure(text=f"Probando alcance a {target}…",
                                text_color=COL_MUTED)
        self.log(f"Ping a dispositivo {target}…")

        def work():
            ok, detail = self._ping(target)
            def finish():
                self.lbl_ping.configure(
                    text=("✓ " if ok else "✗ ") + detail,
                    text_color=COL_GREEN if ok else COL_RED)
                self.log(("✓ " if ok else "✗ ") + detail)
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _ping(host: str) -> tuple[bool, str]:
        """Ping ICMP (Windows: ping -n 1 -w 1500). Devuelve (ok, detalle)."""
        import subprocess
        no_window = (subprocess.CREATE_NO_WINDOW
                     if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        try:
            out = subprocess.run(
                ["ping", "-n", "1", "-w", "1500", host],
                capture_output=True, text=True, timeout=6,
                creationflags=no_window)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"{host} inalcanzable ({exc})."
        ok = out.returncode == 0 and "TTL=" in (out.stdout or "").upper()
        if ok:
            return True, f"{host} responde (alcanzable)."
        return False, f"{host} inalcanzable (sin respuesta a ping)."

    # --------------------------------------------------------------------- #
    # Panel 3: Telegram — acciones
    # --------------------------------------------------------------------- #
    def _on_tg_validate(self) -> None:
        token = self.ent_tg_token.get().strip()
        self.btn_tg_validate.configure(state="disabled")
        self.log("Validando bot de Telegram (getMe)…")

        def work():
            ok, info = telegram_wizard.get_me(token)
            def finish():
                self.btn_tg_validate.configure(state="normal")
                if ok:
                    self._tg_token_ok = True
                    self.lbl_tg_bot.configure(text=f"✓ {info}", text_color=COL_GREEN)
                    self.p_tg.set_status(COL_AMBER, "bot OK")
                    guicfg.update(telegram_token=token)
                    self.log(f"Bot válido: {info}")
                else:
                    self._tg_token_ok = False
                    self.lbl_tg_bot.configure(text=f"✗ {info}", text_color=COL_RED)
                    self.log(f"Bot inválido: {info}")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_tg_chat(self) -> None:
        token = self.ent_tg_token.get().strip()
        self.btn_tg_chat.configure(state="disabled")
        self.log("Detectando chat_id (getUpdates)…")

        def work():
            ok, info = telegram_wizard.detect_chat_id(token)
            def finish():
                self.btn_tg_chat.configure(state="normal")
                if ok:
                    self._tg_chat_ok = True
                    self._tg_chat_id = telegram_wizard.parse_chat_id(info)
                    self.lbl_tg_chat.configure(text=f"✓ {info}", text_color=COL_GREEN)
                    self.log(f"chat_id detectado: {info}")
                else:
                    self._tg_chat_ok = False
                    self.lbl_tg_chat.configure(text=f"✗ {info}", text_color=COL_RED)
                    self.log(f"No se pudo detectar chat: {info}")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_tg_test(self) -> None:
        token = self.ent_tg_token.get().strip()
        chat_id = getattr(self, "_tg_chat_id", "")
        if not chat_id:
            self.log("Primero detecta tu chat (paso 2).")
            return
        self.btn_tg_test.configure(state="disabled")
        self.log("Enviando mensaje de prueba a Telegram (REAL)…")

        def work():
            ok, info = telegram_wizard.send_test(token, chat_id)
            def finish():
                self.btn_tg_test.configure(state="normal")
                if ok:
                    self._tg_test_ok = True
                    self.p_tg.set_status(COL_GREEN, "prueba OK")
                self.log(("✓ " if ok else "✗ ") + info)
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_tg_save(self) -> None:
        token = self.ent_tg_token.get().strip()
        chat_id = getattr(self, "_tg_chat_id", "")
        if not chat_id:
            self.log("Primero detecta tu chat (paso 2) antes de guardar.")
            return
        self.btn_tg_save.configure(state="disabled")
        self.log("Guardando Telegram en el .env del servidor…")

        def work():
            ok, info = telegram_wizard.save_to_env(token, chat_id)
            def finish():
                self.btn_tg_save.configure(state="normal")
                if ok:
                    self.p_tg.set_status(COL_GREEN, "guardado")
                self.log(("✓ " if ok else "✗ ") + info)
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------------------- #
    # Panel 4: App — acciones
    # --------------------------------------------------------------------- #
    def _on_copy_apk(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(str(paths.ANDROID_APK))
        exists = paths.ANDROID_APK.is_file()
        self.log(f"Ruta del APK copiada ({'existe' if exists else 'AÚN no compilado'}): "
                 f"{paths.ANDROID_APK}")

    # --------------------------------------------------------------------- #
    # Panel 5: ESP32-CAM — acciones
    # --------------------------------------------------------------------- #
    def _on_esp_reset_wifi(self) -> None:
        """Borra flash+NVS del ESP32 (forzar portal) y luego reflashea."""
        if self._busy_esp32:
            return
        if not self.esp32_status.online:
            self.log("ESP32-CAM no detectado: conecta la placa por USB.")
            return

        # Confirmación modal antes de una acción destructiva.
        win = ctk.CTkToplevel(self)
        win.title("Resetear WiFi del ESP32")
        win.geometry("460x230")
        win.configure(fg_color=COL_BG)
        win.transient(self)
        try:
            win.grab_set()
        except Exception:  # noqa: BLE001
            pass
        ctk.CTkLabel(
            win,
            text="Esto BORRA el firmware + el WiFi guardado del ESP32-CAM "
                 "(flash + NVS) y luego reflashea el firmware. El ESP32 volverá "
                 "al portal 'FaceCam_Setup' para reconfigurar WiFi. ¿Continuar?",
            font=("Inter", 12), text_color=COL_TEXT, wraplength=420, justify="left",
        ).pack(padx=20, pady=(22, 16))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=(0, 16))

        def _do():
            win.destroy()
            self._start_esp_reset()

        self._gold_button(row, "Sí, resetear", _do).grid(row=0, column=0, padx=8)
        self._ghost_button(row, "Cancelar", win.destroy).grid(row=0, column=1, padx=8)

    def _start_esp_reset(self) -> None:
        """Lanza erase + flash en un hilo, con progreso al log."""
        self._busy_esp32 = True
        self.btn_esp_flash.configure(state="disabled")
        self.btn_esp_reset.configure(state="disabled", text="Reseteando…")
        self.p_esp.set_status(COL_AMBER, "reseteando…")
        self.pb_esp.configure(mode="indeterminate")
        self.pb_esp.start()
        self.log("Reset WiFi ESP32: borrando flash + NVS…")

        def work():
            rc_erase = esp32_config.erase(on_log=self.log, timeout=300.0)
            rc_flash = -1
            if rc_erase == 0:
                self.log("Erase OK. Reflasheando firmware…")
                rc_flash = self.flasher.flash(on_log=self.log, timeout=600.0)
            else:
                self.log("No se reflashea porque el erase falló.")

            def finish():
                self.pb_esp.stop()
                self.pb_esp.configure(mode="determinate")
                ok = rc_erase == 0 and rc_flash == 0
                self.pb_esp.set(1.0 if ok else 0.0)
                self._busy_esp32 = False
                self.btn_esp_reset.configure(text="Resetear WiFi (forzar portal)")
                if ok:
                    self.p_esp.set_status(COL_GREEN, "reseteado")
                    self._register_work_net()
                    self.log("ESP32 reseteado. Conéctate a la red WiFi "
                             "'FaceCam_Setup' y abre http://192.168.4.1 para "
                             "configurar WiFi + IP del servidor.")
                else:
                    self.p_esp.set_status(COL_RED, "error")
                online = self.esp32_status.online
                self.btn_esp_flash.configure(state="normal" if online else "disabled")
                self.btn_esp_reset.configure(state="normal" if online else "disabled")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_esp_trigger_intrusion(self) -> None:
        """Dispara POST /intrusion para que el ESP32-CAM tome foto y valide."""
        self.btn_esp_intrusion.configure(state="disabled", text="Disparando…")
        self.log("Validar Intruso: disparando captura + reconocimiento…")

        def work():
            ok, info = system_ctrl.trigger_intrusion(port=PORT)
            def finish():
                self.btn_esp_intrusion.configure(state="normal", text="Validar Intruso")
                self.log(("-> " if ok else "X ") + info)
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    def _on_esp_flash(self) -> None:
        if self._busy_esp32:
            return
        if not self.esp32_status.online:
            self.log("ESP32-CAM no detectado: conecta la placa por USB.")
            return
        self._busy_esp32 = True
        self.btn_esp_flash.configure(state="disabled", text="Flasheando…")
        self.btn_esp_reset.configure(state="disabled")
        self.p_esp.set_status(COL_AMBER, "flasheando…")
        self.pb_esp.configure(mode="indeterminate")
        self.pb_esp.start()
        self.log(f"Flasheando ESP32-CAM en {self.esp32_status.port}…")

        def work():
            rc = self.flasher.flash(on_log=self.log, timeout=600.0)
            def finish():
                self.pb_esp.stop()
                self.pb_esp.configure(mode="determinate")
                self.pb_esp.set(1.0 if rc == 0 else 0.0)
                self._busy_esp32 = False
                self.btn_esp_flash.configure(text="Configurar / Flashear ESP32")
                if rc == 0:
                    self.p_esp.set_status(COL_GREEN, "flasheado")
                    # Tras flashear, el ESP32 quedó atado a esta red/IP: regístrala.
                    self._register_work_net()
                else:
                    self.p_esp.set_status(COL_RED, "error")
                # re-evaluar habilitación con el último estado de detección
                online = self.esp32_status.online
                self.btn_esp_flash.configure(state="normal" if online else "disabled")
                self.btn_esp_reset.configure(state="normal" if online else "disabled")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------------------- #
    # Panel 6: UNO Q — acciones
    # --------------------------------------------------------------------- #
    def _on_unoq_config(self) -> None:
        if self._busy_unoq:
            return
        if not self.unoq_status.online:
            self.log("UNO Q no detectado por ADB.")
            return
        ssid1 = self.ent_ssid1.get().strip()
        if not ssid1:
            self.log("La red WiFi 1 (SSID) es obligatoria.")
            return
        pass1 = self.ent_pass1.get()
        ssid2 = self.ent_ssid2.get().strip()
        pass2 = self.ent_pass2.get()

        # Persistir SSIDs (no las contraseñas) por comodidad.
        guicfg.update(unoq_ssid1=ssid1, unoq_ssid2=ssid2,
                      unoq_server_host=self.local_ip)
        # Registrar la red de trabajo: con esta WiFi/IP quedan los dispositivos.
        self._register_work_net()

        self._busy_unoq = True
        self.btn_unoq_cfg.configure(state="disabled", text="Configurando…")
        self.p_unoq.set_status(COL_AMBER, "configurando…")
        self.pb_unoq.configure(mode="indeterminate")
        self.pb_unoq.start()

        device_id = self.unoq_status.device_id
        server_ip = self.local_ip

        def work():
            ok = unoq_config.configure_unoq(
                device_id=device_id, ssid1=ssid1, pass1=pass1,
                ssid2=ssid2, pass2=pass2, server_ip=server_ip,
                server_port=PORT, api_key="", on_log=self.log)
            def finish():
                self.pb_unoq.stop()
                self.pb_unoq.configure(mode="determinate")
                self.pb_unoq.set(1.0 if ok else 0.0)
                self._busy_unoq = False
                self.btn_unoq_cfg.configure(text="Configurar Arduino Q")
                self.p_unoq.set_status(COL_GREEN if ok else COL_RED,
                                       "configurado" if ok else "error")
                self.btn_unoq_cfg.configure(
                    state="normal" if self.unoq_status.online else "disabled")
            self._post(finish)
        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------------------- #
    # Log toggle
    # --------------------------------------------------------------------- #
    def _on_toggle_log(self) -> None:
        if self._log_visible:
            self.log_box.grid_remove()
            self.btn_log_toggle.configure(text="Mostrar registros")
        else:
            self.log_box.grid()
            self.btn_log_toggle.configure(text="Ocultar registros")
        self._log_visible = not self._log_visible

    # --------------------------------------------------------------------- #
    # Cierre limpio
    # --------------------------------------------------------------------- #
    def _on_close(self) -> None:
        """Detiene el hilo de detección y el servidor (si lo lanzó esta GUI)."""
        try:
            self._detect_stop.set()
        except Exception:
            pass
        try:
            self._wifi_stop.set()
        except Exception:
            pass
        try:
            if self.server.is_process_alive():
                self.log("Cerrando: deteniendo el servidor lanzado por la GUI…")
                self.server.stop(on_log=lambda m: None)
        except Exception:
            pass
        self.destroy()


def main() -> None:
    """Punto de entrada de la aplicación."""
    app = PanelControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()

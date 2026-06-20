#!/bin/bash
# test_f2_arm.sh - prueba los comandos ARM/DISARM de F2 por el monitor.
# Abre arduino-app-cli monitor bajo PTY, escribe 'ARM\n', espera, luego
# 'DISARM\n', y captura todo. Como no hay receptor laser cableado, el pin
# flota a HIGH => beam=BROKEN; al ARMAR, tras DEBOUNCE_MS debe dispararse
# 'INTRUSION DETECTED' (prueba la cadena completa estado->buzzer), y DISARM
# debe silenciar e imprimir el cambio de estado.
python3 - <<'PY'
import os, pty, select, subprocess, time
master, slave = pty.openpty()
p = subprocess.Popen(["arduino-app-cli","monitor"], stdin=slave, stdout=slave, stderr=slave, close_fds=True)
os.close(slave)
buf=bytearray()

def pump(seconds):
    end=time.time()+seconds
    while time.time()<end:
        r,_,_=select.select([master],[],[],0.2)
        if master in r:
            try: d=os.read(master,4096)
            except OSError: return
            if d: buf.extend(d)

# Deja estabilizar y capturar estado inicial.
pump(3)
# Envia ARM
os.write(master, b"ARM\n")
pump(4)            # tiempo para ARM + debounce(200ms) + posible INTRUSION
# Envia DISARM
os.write(master, b"DISARM\n")
pump(3)

try: p.terminate()
except Exception: pass
print("===== F2 ARM/DISARM TEST =====")
import sys; sys.stdout.write(buf.decode("utf-8","replace"))
print("\n===== END =====")
PY

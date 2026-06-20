#!/usr/bin/env python3
# monitor_pty_noreset.py - igual que monitor_pty.py pero SIN resetear el MCU
# (el reset via openocd interfiere con el serial-discovery del App Lab cuando
#  hay una app corriendo). Solo escucha el stream vivo (heartbeat cada 5 s).
import os, pty, select, subprocess, sys, time
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 14
master, slave = pty.openpty()
proc = subprocess.Popen(["arduino-app-cli", "monitor"],
                        stdin=slave, stdout=slave, stderr=slave, close_fds=True)
os.close(slave)
buf = bytearray()
deadline = time.time() + SECS
try:
    while time.time() < deadline:
        r, _, _ = select.select([master], [], [], 0.4)
        if master in r:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if data:
                buf.extend(data)
finally:
    try: proc.terminate()
    except Exception: pass
    try: os.close(master)
    except OSError: pass
print("===== arduino-app-cli monitor NO-RESET (%d bytes) =====" % len(buf))
sys.stdout.write(buf.decode("utf-8", errors="replace"))
print("\n===== END =====")

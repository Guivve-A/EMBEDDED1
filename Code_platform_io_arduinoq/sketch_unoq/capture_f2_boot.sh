#!/bin/bash
# capture_f2_boot.sh - captura banner 'Boot OK - F2' + heartbeats de facef2.
set -u
APPDIR=/home/arduino/ArduinoApps/facef2

python3 - <<'PY' &
import os, pty, select, subprocess, sys, time
SECS=22
master, slave = pty.openpty()
p = subprocess.Popen(["arduino-app-cli","monitor"], stdin=slave, stdout=slave, stderr=slave, close_fds=True)
os.close(slave)
buf=bytearray(); dl=time.time()+SECS
while time.time()<dl:
    r,_,_=select.select([master],[],[],0.4)
    if master in r:
        try: d=os.read(master,4096)
        except OSError: break
        if d: buf.extend(d)
try: p.terminate()
except Exception: pass
open("/tmp/f2_boot.log","wb").write(buf)
PY
MON_BG=$!

sleep 2
arduino-app-cli app restart "${APPDIR}" >/dev/null 2>&1
wait "${MON_BG}" 2>/dev/null

echo "===== F2 BOOT CAPTURE ====="
cat /tmp/f2_boot.log
echo ""
echo "===== END ====="
rm -f /tmp/f2_boot.log

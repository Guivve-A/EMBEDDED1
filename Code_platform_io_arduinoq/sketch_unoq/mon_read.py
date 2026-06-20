#!/usr/bin/env python3
# mon_read.py - Lee el Serial del MCU del UNO Q a traves del arduino-router,
# llamando al metodo RPC 'mon/read' por el socket unix /var/run/arduino-router.sock.
# El protocolo es msgpack-RPC (request: [0, msgid, method, params]).
# Esquiva el bug de display de 'arduino-router-cli' (no sabe imprimir []uint8).
#
# Uso: mon_read.py [segundos]   (por defecto 12). Resetea el MCU a t+2s para
#      capturar el banner de boot, y drena 'mon/read' periodicamente.
import socket, struct, sys, time, subprocess

SOCK = "/var/run/arduino-router.sock"
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 12

try:
    import msgpack  # type: ignore
    HAVE_MP = True
except Exception:
    HAVE_MP = False

# ---- Codificacion msgpack minima (solo lo que necesitamos) ----
def mp_pack(obj):
    if HAVE_MP:
        return msgpack.packb(obj, use_bin_type=True)
    # Fallback manual para: array, int pequeno, str corta.
    if isinstance(obj, list):
        assert len(obj) < 16
        out = bytes([0x90 | len(obj)])
        for e in obj:
            out += mp_pack(e)
        return out
    if isinstance(obj, bool):
        return b"\xc3" if obj else b"\xc2"
    if isinstance(obj, int):
        if 0 <= obj < 128:
            return bytes([obj])
        if 128 <= obj < 256:
            return b"\xcc" + bytes([obj])
        return b"\xcd" + struct.pack(">H", obj)
    if isinstance(obj, str):
        b = obj.encode("utf-8")
        assert len(b) < 32
        return bytes([0xa0 | len(b)]) + b
    raise TypeError("mp_pack: %r" % (obj,))

class Unpacker:
    """Desempaquetador msgpack minimo, suficiente para las respuestas del router."""
    def __init__(self, data):
        self.d = data; self.i = 0
    def _u8(self):
        v = self.d[self.i]; self.i += 1; return v
    def read(self):
        b = self._u8()
        if b < 0x80: return b                      # positive fixint
        if b >= 0xe0: return b - 0x100             # negative fixint
        if 0x80 <= b <= 0x8f:                      # fixmap
            n = b & 0x0f; return {self.read(): self.read() for _ in range(n)}
        if 0x90 <= b <= 0x9f:                      # fixarray
            n = b & 0x0f; return [self.read() for _ in range(n)]
        if 0xa0 <= b <= 0xbf:                      # fixstr
            n = b & 0x1f; s = self.d[self.i:self.i+n]; self.i += n; return s.decode("utf-8","replace")
        if b == 0xc0: return None
        if b == 0xc2: return False
        if b == 0xc3: return True
        if b == 0xcc: v=self.d[self.i]; self.i+=1; return v
        if b == 0xcd: v=struct.unpack(">H", self.d[self.i:self.i+2])[0]; self.i+=2; return v
        if b == 0xce: v=struct.unpack(">I", self.d[self.i:self.i+4])[0]; self.i+=4; return v
        if b == 0xcf: v=struct.unpack(">Q", self.d[self.i:self.i+8])[0]; self.i+=8; return v
        if b == 0xc4: n=self.d[self.i]; self.i+=1; s=self.d[self.i:self.i+n]; self.i+=n; return list(s)  # bin8
        if b == 0xc5: n=struct.unpack(">H", self.d[self.i:self.i+2])[0]; self.i+=2; s=self.d[self.i:self.i+n]; self.i+=n; return list(s)
        if b == 0xd9: n=self.d[self.i]; self.i+=1; s=self.d[self.i:self.i+n]; self.i+=n; return s.decode("utf-8","replace")  # str8
        if b == 0xda: n=struct.unpack(">H", self.d[self.i:self.i+2])[0]; self.i+=2; s=self.d[self.i:self.i+n]; self.i+=n; return s.decode("utf-8","replace")
        if b == 0xdc: n=struct.unpack(">H", self.d[self.i:self.i+2])[0]; self.i+=2; return [self.read() for _ in range(n)]  # array16
        if b == 0xde: n=struct.unpack(">H", self.d[self.i:self.i+2])[0]; self.i+=2; return {self.read(): self.read() for _ in range(n)}  # map16
        raise ValueError("byte msgpack no soportado: 0x%02x @%d" % (b, self.i-1))

_msgid = [0]
def rpc(sock, method, params):
    _msgid[0] += 1
    mid = _msgid[0]
    req = mp_pack([0, mid, method, params])
    sock.sendall(req)
    # Lee una respuesta (puede venir fragmentada).
    sock.settimeout(1.5)
    buf = b""
    while True:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        try:
            up = Unpacker(buf)
            msg = up.read()
            return msg
        except Exception:
            continue  # respuesta incompleta, sigue leyendo
    return None

def main():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    print("CONNECTED %s, capturando %ds (reset a t+2s) via mon/read..." % (SOCK, SECS))

    out = bytearray()
    deadline = time.time() + SECS
    reset_done = False
    while time.time() < deadline:
        if not reset_done and time.time() > (deadline - SECS + 2):
            subprocess.run(["arduino-reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            reset_done = True
        msg = rpc(s, "mon/read", [128])
        # Respuesta esperada: [1, msgid, error, result]; result = lista de bytes.
        data = None
        if isinstance(msg, list) and len(msg) >= 4:
            data = msg[3]
        elif isinstance(msg, list):
            data = msg[-1]
        if isinstance(data, list) and data:
            out.extend(b & 0xff for b in data)
        elif isinstance(data, (bytes, bytearray)) and data:
            out.extend(data)
        time.sleep(0.2)

    s.close()
    print("===== MCU SERIAL via mon/read (%d bytes) =====" % len(out))
    sys.stdout.write(out.decode("utf-8", errors="replace"))
    print("\n===== END =====")

if __name__ == "__main__":
    main()

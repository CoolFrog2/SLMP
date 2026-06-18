"""
Egyszerű mock SLMP PLC szerver teszteléshez (3E binary, TCP).

Csak a Batch Read (0401) és Batch Write (1401) parancsokat kezeli, Word és
Bit egységben. Egy közös memóriatérképet tart fenn eszköztípusonként.
Valódi PLC helyett használható a frontend/backend kipróbálásához.

Futtatás:  python3 mock_plc.py [port]   (alapértelmezett port: 5007)
"""

import socket
import struct
import sys
import threading
from collections import defaultdict

from slmp import DEVICES

# eszközkód -> { cím: 16 bites érték }   (bit-eszköznél is wordként tároljuk,
# de bit műveletnél címenként 1 bitet kezelünk)
WORD_MEM = defaultdict(lambda: defaultdict(int))   # word-eszközök
BIT_MEM = defaultdict(lambda: defaultdict(int))    # bit-eszközök (0/1)

CODE_TO_INFO = {info["code"]: (name, info) for name, info in DEVICES.items()}


def handle(conn, addr):
    print(f"[mock] kapcsolat: {addr}")
    try:
        while True:
            head = recv_exact(conn, 9)
            if head is None:
                break
            req_len = struct.unpack("<H", head[7:9])[0]
            payload = recv_exact(conn, req_len)
            if payload is None:
                break
            # payload: monitoring_timer(2) command(2) subcommand(2) data...
            command = struct.unpack("<H", payload[2:4])[0]
            subcommand = struct.unpack("<H", payload[4:6])[0]
            data = payload[6:]
            resp = process(command, subcommand, data)
            conn.sendall(resp)
    except (ConnectionError, OSError) as e:
        print(f"[mock] kapcsolat zárul ({addr}): {e}")
    finally:
        conn.close()


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def make_response(end_code, data=b""):
    body = struct.pack("<H", end_code) + data
    header = (b"\xD0\x00"
              + b"\x00\xFF"          # net, pc
              + struct.pack("<H", 0x03FF)
              + b"\x00"
              + struct.pack("<H", len(body)))
    return header + body


def process(command, subcommand, data):
    head_dev = struct.unpack("<I", data[0:3] + b"\x00")[0]
    dev_code = data[3]
    count = struct.unpack("<H", data[4:6])[0]
    name, info = CODE_TO_INFO.get(dev_code, (None, None))
    if info is None:
        return make_response(0xC059)   # ismeretlen eszköz

    is_bit = (subcommand == 0x0001)

    if command == 0x0401:   # Batch Read
        if is_bit:
            mem = BIT_MEM[dev_code]
            bits = [1 if mem[head_dev + i] else 0 for i in range(count)]
            out = bytearray()
            for i in range(0, count, 2):
                hi = 0x10 if bits[i] else 0x00
                lo = 0x01 if (i + 1 < count and bits[i + 1]) else 0x00
                out.append(hi | lo)
            return make_response(0x0000, bytes(out))
        else:
            mem = WORD_MEM[dev_code]
            out = b"".join(struct.pack("<H", mem[head_dev + i] & 0xFFFF)
                           for i in range(count))
            return make_response(0x0000, out)

    if command == 0x1401:   # Batch Write
        if is_bit:
            mem = BIT_MEM[dev_code]
            bitdata = data[6:]
            for i in range(count):
                byte = bitdata[i // 2]
                nibble = (byte >> 4) if (i % 2 == 0) else (byte & 0x0F)
                mem[head_dev + i] = 1 if nibble else 0
            return make_response(0x0000)
        else:
            mem = WORD_MEM[dev_code]
            worddata = data[6:]
            for i in range(count):
                mem[head_dev + i] = struct.unpack("<H", worddata[i * 2:i * 2 + 2])[0]
            return make_response(0x0000)

    return make_response(0xC059)   # nem támogatott parancs


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5007
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"[mock] SLMP mock PLC fut a 0.0.0.0:{port} címen (Ctrl+C a leállításhoz)")
    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[mock] leállás")
    finally:
        srv.close()


if __name__ == "__main__":
    main()

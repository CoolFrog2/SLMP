"""
SLMP (SeamLess Message Protocol) kliens Mitsubishi MELSEC Q-sorozatú PLC-hez.

Megvalósítás: 3E keret, BINARY kód, TCP/IP felett.
Támogatott műveletek:
  - Batch Read  (0401)  Word / Bit egységben
  - Batch Write (1401)  Word / Bit egységben

A keretformátum a MELSEC kommunikációs protokoll referencia szerint.
"""

import socket
import struct


# ---------------------------------------------------------------------------
# Eszközkódok (binary kód, 1 byte) és tulajdonságaik
#   code      : SLMP binary eszközkód
#   hex_addr  : True, ha az eszköz címe hexadecimális (X, Y, B, W, ...)
#   bit       : True, ha bit-eszköz (bit egységben is olvasható/írható)
# ---------------------------------------------------------------------------
DEVICES = {
    "SM": {"code": 0x91, "hex_addr": False, "bit": True},
    "SD": {"code": 0xA9, "hex_addr": False, "bit": False},
    "X":  {"code": 0x9C, "hex_addr": True,  "bit": True},
    "Y":  {"code": 0x9D, "hex_addr": True,  "bit": True},
    "M":  {"code": 0x90, "hex_addr": False, "bit": True},
    "L":  {"code": 0x92, "hex_addr": False, "bit": True},
    "F":  {"code": 0x93, "hex_addr": False, "bit": True},
    "V":  {"code": 0x94, "hex_addr": False, "bit": True},
    "B":  {"code": 0xA0, "hex_addr": True,  "bit": True},
    "D":  {"code": 0xA8, "hex_addr": False, "bit": False},
    "W":  {"code": 0xB4, "hex_addr": True,  "bit": False},
    "TS": {"code": 0xC1, "hex_addr": False, "bit": True},
    "TC": {"code": 0xC0, "hex_addr": False, "bit": True},
    "TN": {"code": 0xC2, "hex_addr": False, "bit": False},
    "SS": {"code": 0xC7, "hex_addr": False, "bit": True},
    "SC": {"code": 0xC6, "hex_addr": False, "bit": True},
    "SN": {"code": 0xC8, "hex_addr": False, "bit": False},
    "CS": {"code": 0xC4, "hex_addr": False, "bit": True},
    "CC": {"code": 0xC3, "hex_addr": False, "bit": True},
    "CN": {"code": 0xC5, "hex_addr": False, "bit": False},
    "SB": {"code": 0xA1, "hex_addr": True,  "bit": True},
    "SW": {"code": 0xB5, "hex_addr": True,  "bit": False},
    "DX": {"code": 0xA2, "hex_addr": True,  "bit": True},
    "DY": {"code": 0xA3, "hex_addr": True,  "bit": True},
    "R":  {"code": 0xAF, "hex_addr": False, "bit": False},
    "ZR": {"code": 0xB0, "hex_addr": True,  "bit": False},
    "Z":  {"code": 0xCC, "hex_addr": False, "bit": False},
}

# A leghosszabb prefixet kell előbb illeszteni (pl. "SD" a "S" előtt, "ZR" a "Z" előtt)
_DEVICE_PREFIXES = sorted(DEVICES.keys(), key=len, reverse=True)

# Néhány ismert befejezési (hiba) kód emberi olvasásra
END_CODES = {
    0x0000: "Sikeres",
    0x4031: "Eszközcím a tartományon kívül / nem létező eszköz",
    0xC050: "ASCII kód hiba",
    0xC051: "Túl sok olvasási pont (max túllépve)",
    0xC052: "Túl sok írási pont (max túllépve)",
    0xC056: "Cím + pontszám túllépi a megengedett tartományt",
    0xC059: "Parancs/alparancs hiba",
    0xC05B: "A megadott eszközhöz nem fér hozzá a CPU",
    0xC05C: "Kérés tartalmi hiba",
    0xC05F: "A kérés nem hajtható végre ezen a PLC-n",
    0xC060: "Bit adat hiba (0/1-től eltérő)",
    0xC061: "Adathossz nem egyezik a pontszámmal",
}


class SlmpError(Exception):
    """SLMP-szintű hiba: a PLC nem nulla befejezési kódot adott vissza."""

    def __init__(self, end_code, detail=None):
        self.end_code = end_code
        self.detail = detail
        msg = END_CODES.get(end_code, "Ismeretlen hiba")
        text = f"SLMP hiba (end code 0x{end_code:04X}): {msg}"
        if detail:
            text += f" — {detail}"
        super().__init__(text)


def parse_device(device_str):
    """
    'D100', 'M0', 'X1F', 'Y20' -> (prefix, address_int, info_dict)

    A hexadecimálisan címzett eszközöknél (X, Y, B, W, ...) a számot 16-os
    alapon, egyébként 10-es alapon értelmezzük.
    """
    s = device_str.strip().upper().replace(" ", "")
    if not s:
        raise ValueError("Üres eszköz megnevezés")

    prefix = None
    for p in _DEVICE_PREFIXES:
        if s.startswith(p):
            prefix = p
            break
    if prefix is None:
        raise ValueError(f"Ismeretlen eszköztípus: '{device_str}'")

    num_part = s[len(prefix):]
    if num_part == "":
        raise ValueError(f"Hiányzó cím: '{device_str}'")

    info = DEVICES[prefix]
    base = 16 if info["hex_addr"] else 10
    try:
        address = int(num_part, base)
    except ValueError:
        kind = "hexadecimális" if base == 16 else "decimális"
        raise ValueError(f"Érvénytelen {kind} cím: '{num_part}' ({device_str})")

    return prefix, address, info


# ---------------------------------------------------------------------------
# 3E binary keret összeállítás
# ---------------------------------------------------------------------------
class SlmpClient:
    SUBHEADER_REQ = b"\x50\x00"
    SUBHEADER_RES = b"\xD0\x00"

    def __init__(self, host, port, *, timeout=3.0,
                 network=0x00, pc=0xFF, dest_io=0x03FF, dest_station=0x00,
                 monitoring_timer=0x0010):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.network = network
        self.pc = pc
        self.dest_io = dest_io
        self.dest_station = dest_station
        # 250 ms egységben; 0x0010 = 16 -> 4 s. 0x0000 = végtelen várakozás.
        self.monitoring_timer = monitoring_timer
        self._sock = None

    # -- kapcsolatkezelés ---------------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port),
                                               timeout=self.timeout)
        self._sock.settimeout(self.timeout)

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # -- alacsony szintű keret ---------------------------------------------
    def _build_frame(self, command, subcommand, request_data):
        """Teljes 3E binary kérés keret összeállítása."""
        # monitoring timer + command + subcommand + request data
        payload = (struct.pack("<H", self.monitoring_timer)
                   + struct.pack("<H", command)
                   + struct.pack("<H", subcommand)
                   + request_data)
        header = (self.SUBHEADER_REQ
                  + struct.pack("<B", self.network)
                  + struct.pack("<B", self.pc)
                  + struct.pack("<H", self.dest_io)
                  + struct.pack("<B", self.dest_station)
                  + struct.pack("<H", len(payload)))   # request data length
        return header + payload

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("A PLC lezárta a kapcsolatot (idő előtti vég).")
            buf += chunk
        return buf

    def _transact(self, command, subcommand, request_data):
        """Kérés küldése és a válasz adatrészének visszaadása (end code után)."""
        if self._sock is None:
            self.connect()
        frame = self._build_frame(command, subcommand, request_data)
        self._sock.sendall(frame)

        # Fix rész: subheader(2)+net(1)+pc(1)+io(2)+station(1)=7, majd len(2)
        head = self._recv_exact(9)
        if head[0:2] != self.SUBHEADER_RES:
            raise ConnectionError(
                f"Váratlan válasz subheader: {head[0:2].hex()}")
        resp_len = struct.unpack("<H", head[7:9])[0]
        body = self._recv_exact(resp_len)  # end code(2) + adat

        end_code = struct.unpack("<H", body[0:2])[0]
        data = body[2:]
        if end_code != 0x0000:
            detail = data.hex() if data else None
            raise SlmpError(end_code, detail)
        return data

    # -- magas szintű műveletek --------------------------------------------
    def read_words(self, device_str, count):
        prefix, address, info = parse_device(device_str)
        req = (struct.pack("<I", address)[0:3]      # head device 3 byte LE
               + struct.pack("<B", info["code"])    # device code
               + struct.pack("<H", count))          # number of points
        data = self._transact(0x0401, 0x0000, req)
        words = list(struct.unpack(f"<{count}H", data[:count * 2]))
        return words

    def write_words(self, device_str, values):
        prefix, address, info = parse_device(device_str)
        count = len(values)
        body = b"".join(struct.pack("<H", v & 0xFFFF) for v in values)
        req = (struct.pack("<I", address)[0:3]
               + struct.pack("<B", info["code"])
               + struct.pack("<H", count)
               + body)
        self._transact(0x1401, 0x0000, req)
        return count

    def read_bits(self, device_str, count):
        prefix, address, info = parse_device(device_str)
        if not info["bit"]:
            raise ValueError(f"A(z) {prefix} szó-eszköz, nem olvasható bit egységben.")
        req = (struct.pack("<I", address)[0:3]
               + struct.pack("<B", info["code"])
               + struct.pack("<H", count))
        data = self._transact(0x0401, 0x0001, req)
        return self._decode_bits(data, count)

    def write_bits(self, device_str, values):
        prefix, address, info = parse_device(device_str)
        if not info["bit"]:
            raise ValueError(f"A(z) {prefix} szó-eszköz, nem írható bit egységben.")
        count = len(values)
        req = (struct.pack("<I", address)[0:3]
               + struct.pack("<B", info["code"])
               + struct.pack("<H", count)
               + self._encode_bits(values))
        self._transact(0x1401, 0x0001, req)
        return count

    # -- bit kódolás (2 pont / byte, felső nibble az első) -----------------
    @staticmethod
    def _encode_bits(values):
        data = bytearray()
        for i in range(0, len(values), 2):
            hi = 0x10 if values[i] else 0x00
            lo = 0x01 if (i + 1 < len(values) and values[i + 1]) else 0x00
            data.append(hi | lo)
        return bytes(data)

    @staticmethod
    def _decode_bits(data, count):
        out = []
        for i in range(count):
            byte = data[i // 2]
            nibble = (byte >> 4) if (i % 2 == 0) else (byte & 0x0F)
            out.append(1 if nibble else 0)
        return out

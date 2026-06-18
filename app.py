"""
Flask backend SLMP PLC kommunikációhoz.

A kapcsolat állapotmentes: az IP/port minden kéréssel érkezik a frontendről,
a backend megnyitja a TCP kapcsolatot, elvégzi a műveletet, majd bontja.
"""

import os
import random
import threading
import time

from flask import Flask, render_template, request, jsonify

from slmp import SlmpClient, SlmpError, DEVICES, parse_device

app = Flask(__name__)

# Opcionális token-alapú hitelesítés. Ha az SLMP_TOKEN környezeti változó be
# van állítva, minden /api/ kérés Authorization: Bearer <token> vagy
# X-API-Token: <token> fejlécet igényel. Ha nincs beállítva, a hitelesítés ki
# van kapcsolva (gyors helyi használat). ICS/PLC írásnál erősen ajánlott!
API_TOKEN = os.environ.get("SLMP_TOKEN")


@app.before_request
def _require_token():
    if not API_TOKEN:
        return  # auth kikapcsolva
    if not request.path.startswith("/api/"):
        return
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else \
        request.headers.get("X-API-Token", "")
    if token != API_TOKEN:
        return jsonify({"ok": False, "error": "Hitelesítés szükséges (érvénytelen vagy hiányzó token)."}), 401


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------
def _client_from_request(data):
    host = (data.get("ip") or "").strip()
    port = data.get("port")
    if not host:
        raise ValueError("Hiányzó IP cím.")
    if not port:
        raise ValueError("Hiányzó port.")
    timeout = float(data.get("timeout", 3.0))
    return SlmpClient(host, int(port), timeout=timeout)


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _parse_word_value(token):
    """'0x1A2B', '255', '-1' -> 0..65535 közötti int."""
    t = str(token).strip()
    if t == "":
        raise ValueError("Üres érték.")
    if t.lower().startswith("0x"):
        val = int(t, 16)
    else:
        val = int(t, 10)
    if val < 0:
        val &= 0xFFFF  # kettes komplemens 16 bitre
    if not (0 <= val <= 0xFFFF):
        raise ValueError(f"Érték a 0..65535 (vagy 0xFFFF) tartományon kívül: {token}")
    return val


# ---------------------------------------------------------------------------
# Útvonalak
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/devices")
def api_devices():
    """Az elérhető eszköztípusok listája a frontend legördülőjéhez."""
    out = []
    for name, info in DEVICES.items():
        out.append({
            "name": name,
            "bit": info["bit"],
            "hex_addr": info["hex_addr"],
        })
    return jsonify({"ok": True, "devices": out})


@app.route("/api/test", methods=["POST"])
def api_test():
    """Kapcsolat teszt: TCP csatlakozás megpróbálása a megadott IP:port-ra."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        client = _client_from_request(data)
    except (ValueError, TypeError) as e:
        return _error(str(e))
    try:
        client.connect()
        client.close()
        return jsonify({"ok": True, "message": f"Kapcsolat él: {client.host}:{client.port}"})
    except OSError as e:
        return _error(f"Nem sikerült csatlakozni: {e}", status=502)


@app.route("/api/read", methods=["POST"])
def api_read():
    data = request.get_json(force=True, silent=True) or {}
    try:
        client = _client_from_request(data)
        device = (data.get("device") or "").strip()
        count = int(data.get("count", 1))
        mode = (data.get("mode") or "word").lower()
        if count < 1 or count > 960:
            raise ValueError("A darabszám 1 és 960 között lehet.")
        parse_device(device)  # korai validáció
    except (ValueError, TypeError) as e:
        return _error(str(e))

    try:
        with client:
            if mode == "bit":
                bits = client.read_bits(device, count)
                values = [{"address": device_at(device, i), "value": b} for i, b in enumerate(bits)]
            else:
                words = client.read_words(device, count)
                values = [{
                    "address": device_at(device, i),
                    "value": w,
                    "hex": f"0x{w:04X}",
                    "signed": w - 0x10000 if w >= 0x8000 else w,
                } for i, w in enumerate(words)]
        return jsonify({"ok": True, "mode": mode, "device": device, "count": count, "values": values})
    except ValueError as e:
        return _error(str(e))
    except SlmpError as e:
        return _error(str(e), status=502)
    except OSError as e:
        return _error(f"Kommunikációs hiba: {e}", status=502)


@app.route("/api/write", methods=["POST"])
def api_write():
    data = request.get_json(force=True, silent=True) or {}
    try:
        client = _client_from_request(data)
        device = (data.get("device") or "").strip()
        mode = (data.get("mode") or "word").lower()
        raw_values = data.get("values")
        if raw_values is None:
            raise ValueError("Hiányoznak az írandó értékek.")
        if isinstance(raw_values, str):
            tokens = [t for t in raw_values.replace(";", ",").split(",") if t.strip() != ""]
        else:
            tokens = list(raw_values)
        if not tokens:
            raise ValueError("Nincs megadva írandó érték.")

        if mode == "bit":
            values = []
            for t in tokens:
                ts = str(t).strip().lower()
                if ts in ("1", "on", "true"):
                    values.append(1)
                elif ts in ("0", "off", "false"):
                    values.append(0)
                else:
                    raise ValueError(f"Bit érték csak 0/1 lehet: '{t}'")
        else:
            values = [_parse_word_value(t) for t in tokens]

        parse_device(device)  # korai validáció
    except (ValueError, TypeError) as e:
        return _error(str(e))

    try:
        with client:
            if mode == "bit":
                n = client.write_bits(device, values)
            else:
                n = client.write_words(device, values)
        return jsonify({"ok": True, "mode": mode, "device": device,
                        "written": n,
                        "message": f"{n} {'bit' if mode == 'bit' else 'word'} kiírva ide: {device}"})
    except ValueError as e:
        return _error(str(e))
    except SlmpError as e:
        return _error(str(e), status=502)
    except OSError as e:
        return _error(f"Kommunikációs hiba: {e}", status=502)


def device_at(device_str, offset):
    """A 'D100' + offset 5 -> 'D105' címke előállítása (hex eszközöknél hexa)."""
    try:
        prefix, address, info = parse_device(device_str)
        addr = address + offset
        if info["hex_addr"]:
            return f"{prefix}{addr:X}"
        return f"{prefix}{addr}"
    except ValueError:
        return f"{device_str}+{offset}"


# ---------------------------------------------------------------------------
# Random író háttérfeladat
#   Egy megadott (word) regiszterbe — jellemzően D — adott időközönként
#   véletlen értéket ír, amíg le nem állítják. Egyszerre egy fut.
# ---------------------------------------------------------------------------
class RandomWriter:
    AUTO_STOP_AFTER = 10  # ennyi egymást követő hiba után automatikus leállás

    def __init__(self):
        self._thread = None
        self._stop = None
        self._lock = threading.Lock()
        self.status = self._idle_status()

    @staticmethod
    def _idle_status():
        return {
            "running": False, "device": None, "interval_ms": None,
            "min": None, "max": None, "last_value": None, "last_hex": None,
            "last_write_at": None, "writes": 0, "errors": 0, "last_error": None,
        }

    def start(self, host, port, timeout, device, interval_ms, vmin, vmax):
        with self._lock:
            # futó példány leállítása (saját stop-eventjével)
            if self._stop is not None:
                self._stop.set()
            stop_event = threading.Event()
            self._stop = stop_event
            cfg = {
                "host": host, "port": port, "timeout": timeout, "device": device,
                "interval": interval_ms / 1000.0, "vmin": vmin, "vmax": vmax,
            }
            self.status = self._idle_status()
            self.status.update({
                "running": True, "device": device, "interval_ms": interval_ms,
                "min": vmin, "max": vmax,
            })
            self._thread = threading.Thread(
                target=self._run, args=(stop_event, cfg), daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if self._stop is not None:
                self._stop.set()
            self._thread = None
            self.status["running"] = False

    def _run(self, stop_event, cfg):
        consecutive = 0
        while not stop_event.is_set():
            value = random.randint(cfg["vmin"], cfg["vmax"])
            try:
                with SlmpClient(cfg["host"], cfg["port"], timeout=cfg["timeout"]) as client:
                    client.write_words(cfg["device"], [value])
                with self._lock:
                    if stop_event.is_set():
                        break
                    self.status["last_value"] = value
                    self.status["last_hex"] = f"0x{value:04X}"
                    self.status["last_write_at"] = time.time()
                    self.status["writes"] += 1
                consecutive = 0
            except Exception as e:  # SLMP/hálózati hiba: jelöljük, de tovább próbáljuk
                consecutive += 1
                with self._lock:
                    self.status["errors"] += 1
                    self.status["last_error"] = str(e)
                    if consecutive >= self.AUTO_STOP_AFTER:
                        self.status["running"] = False
                        self.status["last_error"] = \
                            f"Automatikus leállás {consecutive} hiba után: {e}"
                if consecutive >= self.AUTO_STOP_AFTER:
                    break
            stop_event.wait(cfg["interval"])

    def get_status(self):
        with self._lock:
            return dict(self.status)


random_writer = RandomWriter()


@app.route("/api/random/start", methods=["POST"])
def api_random_start():
    data = request.get_json(force=True, silent=True) or {}
    try:
        host = (data.get("ip") or "").strip()
        port = data.get("port")
        if not host:
            raise ValueError("Hiányzó IP cím.")
        if not port:
            raise ValueError("Hiányzó port.")
        timeout = float(data.get("timeout", 3.0))
        device = (data.get("device") or "").strip()
        parse_device(device)  # korai validáció (a word-írás bármely word-eszközre megy)
        interval_ms = int(data.get("interval", 1000))
        if interval_ms < 200 or interval_ms > 60000:
            raise ValueError("Az intervallum 200 és 60000 ms között lehet.")
        vmin = _parse_word_value(data.get("min", 0))
        vmax = _parse_word_value(data.get("max", 65535))
        if vmin > vmax:
            raise ValueError("A minimum nem lehet nagyobb a maximumnál.")
    except (ValueError, TypeError) as e:
        return _error(str(e))

    random_writer.start(host, int(port), timeout, device, interval_ms, vmin, vmax)
    return jsonify({
        "ok": True,
        "message": f"Random írás indítva: {device} minden {interval_ms} ms-ben ({vmin}–{vmax})",
        "status": random_writer.get_status(),
    })


@app.route("/api/random/stop", methods=["POST"])
def api_random_stop():
    random_writer.stop()
    return jsonify({"ok": True, "message": "Random írás leállítva.",
                    "status": random_writer.get_status()})


@app.route("/api/random/status", methods=["GET", "POST"])
def api_random_status():
    return jsonify({"ok": True, "status": random_writer.get_status()})


if __name__ == "__main__":
    # Izolált rendszerhez kényelmes alapértékek:
    #  - host alapból 0.0.0.0 -> a weblap a hálózat bármely gépéről elérhető.
    #  - debug env-kapcsolós, alapból ki (csak SLMP_DEBUG=1 mellett aktív).
    # Mind a host/port/debug, mind az opcionális SLMP_TOKEN env-ből állítható.
    host = os.environ.get("SLMP_HOST", "0.0.0.0")
    port = int(os.environ.get("SLMP_PORT", "5000"))
    debug = os.environ.get("SLMP_DEBUG") == "1"
    app.run(host=host, port=port, debug=debug)

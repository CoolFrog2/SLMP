"""
Flask backend SLMP PLC kommunikációhoz.

A kapcsolat állapotmentes: az IP/port minden kéréssel érkezik a frontendről,
a backend megnyitja a TCP kapcsolatot, elvégzi a műveletet, majd bontja.
"""

from flask import Flask, render_template, request, jsonify

from slmp import SlmpClient, SlmpError, DEVICES, parse_device

app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

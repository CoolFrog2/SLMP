"""End-to-end teszt a mock PLC ellen: SlmpClient írás/olvasás kör."""
import socket
import threading
import time

import mock_plc
from slmp import SlmpClient, parse_device


def start_mock(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)

    def loop():
        while True:
            try:
                conn, addr = srv.accept()
            except OSError:
                break
            threading.Thread(target=mock_plc.handle, args=(conn, addr), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return srv


def main():
    port = 5099
    srv = start_mock(port)
    time.sleep(0.2)
    ok = True

    # --- parse_device tesztek ---
    assert parse_device("D100")[1] == 100
    assert parse_device("X1F")[1] == 0x1F          # hex címzés
    assert parse_device("Y20")[1] == 0x20
    assert parse_device("M0")[1] == 0
    print("[teszt] parse_device OK")

    c = SlmpClient("127.0.0.1", port, timeout=2.0)
    with c:
        # --- WORD kör ---
        c.write_words("D100", [1, 2, 0xABCD, 65535])
        words = c.read_words("D100", 4)
        assert words == [1, 2, 0xABCD, 65535], words
        print(f"[teszt] word kör OK: {words}")

        # negatív / komplemens
        c.write_words("D200", [-1])  # -> 0xFFFF
        assert c.read_words("D200", 1) == [0xFFFF]
        print("[teszt] negatív word OK")

        # --- BIT kör (páratlan hossz is) ---
        c.write_bits("M0", [1, 0, 1, 1, 0])
        bits = c.read_bits("M0", 5)
        assert bits == [1, 0, 1, 1, 0], bits
        print(f"[teszt] bit kör OK: {bits}")

        # --- hex címzésű bit (X/Y) ---
        c.write_bits("Y10", [1, 1, 0, 1])
        ybits = c.read_bits("Y10", 4)
        assert ybits == [1, 1, 0, 1], ybits
        print(f"[teszt] hex-címzett bit (Y10) OK: {ybits}")

    srv.close()
    print("\n=== MINDEN TESZT SIKERES ===" if ok else "HIBA")


if __name__ == "__main__":
    main()

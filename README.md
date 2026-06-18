# SLMP PLC vezérlő

Web-alapú olvasó/író felület Mitsubishi MELSEC **Q-sorozatú** PLC-hez,
**SLMP** protokollon keresztül. Word és bit egységben is tud olvasni/írni.
Az IP címet és portot a weblapon lehet beállítani.

- **Protokoll:** SLMP, 3E keret, **BINARY** kód, **TCP/IP** felett
- **Parancsok:** Batch Read (`0401`) és Batch Write (`1401`), Word és Bit egységben
- **Backend:** Flask (állapotmentes — minden kérés saját TCP kapcsolatot nyit/zár)
- **Frontend:** egyszerű weblap (vanilla JS), az IP/port a böngészőben megőrződik

## Fájlok

| Fájl | Szerep |
|------|--------|
| `slmp.py` | SLMP kliens (keretösszeállítás, eszközkódok, read/write word/bit) |
| `app.py` | Flask backend és REST API |
| `templates/index.html` | weblap |
| `static/style.css`, `static/app.js` | frontend |
| `mock_plc.py` | mock SLMP PLC szerver teszteléshez (valódi PLC nélkül) |
| `test_roundtrip.py` | end-to-end teszt a mock ellen |

## Indítás

```bash
pip install -r requirements.txt
python3 app.py            # -> http://0.0.0.0:5000
```

Nyisd meg a böngészőben a `http://<gép-ip>:5000` címet, add meg a PLC IP-jét
és portját (alapból a Q-sorozat SLMP TCP portja gyakran **5007** vagy a
GX Works-ben beállított érték), majd „Kapcsolat teszt”.

## Tesztelés valódi PLC nélkül

```bash
python3 mock_plc.py 5007      # 1. terminál: mock PLC
python3 app.py                # 2. terminál: webapp
# a weblapon IP=127.0.0.1, Port=5007
```

Automata kör-teszt:

```bash
python3 test_roundtrip.py
```

## REST API

| Végpont | Metódus | Törzs (JSON) |
|---------|---------|--------------|
| `/api/test` | POST | `{ip, port, timeout?}` |
| `/api/read` | POST | `{ip, port, device, count, mode:"word"|"bit"}` |
| `/api/write` | POST | `{ip, port, device, mode, values}` |
| `/api/devices` | GET | — (támogatott eszköztípusok) |

- **device:** pl. `D100`, `M0`, `X1F`, `Y20` (X/Y/B/W/SB/SW/DX/DY címe **hexa**, a többié decimális)
- **word értékek:** decimális vagy `0x` hex, `0–65535` (negatív → 16 bites kettes komplemens)
- **bit értékek:** `0`/`1` (`on`/`off` is elfogadott)

## Támogatott eszközök

`SM, SD, X, Y, M, L, F, V, B, D, W, TS, TC, TN, SS, SC, SN, CS, CC, CN, SB, SW, DX, DY, R, ZR, Z`

Bit egységben csak a bit-eszközök írhatók/olvashatók (pl. `M`, `X`, `Y`, `B`);
a szó-eszközök (pl. `D`, `W`, `R`) csak word módban.

## Megjegyzések / bővíthetőség

- Az SLMP keret paraméterei (hálózat sz., PLC sz., modul I/O `0x03FF`,
  állomás sz., monitor timer) a `SlmpClient` konstruktorában állíthatók;
  jelenleg a közvetlen CPU-kapcsolat alapértékeit használja.
- Jelenleg 3E binary/TCP. ASCII kód vagy 4E keret igény szerint bővíthető a `slmp.py`-ban.
- Éles üzemhez a Flask fejlesztői szerver helyett WSGI szervert (pl. `gunicorn`) érdemes használni.

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
python3 app.py            # -> http://127.0.0.1:5000  (csak helyi gép)
```

Nyisd meg a böngészőben a `http://127.0.0.1:5000` címet, add meg a PLC IP-jét
és portját (alapból a Q-sorozat SLMP TCP portja gyakran **5007** vagy a
GX Works-ben beállított érték), majd „Kapcsolat teszt”.

### Környezeti változók

| Változó | Alap | Szerep |
|---------|------|--------|
| `SLMP_HOST` | `127.0.0.1` | A webszerver kötési címe. LAN-eléréshez: `0.0.0.0`. |
| `SLMP_PORT` | `5000` | A webszerver portja. |
| `SLMP_DEBUG` | (ki) | `1` esetén Flask debug mód. **Soha ne kapcsold be elérhető környezetben** (RCE!). |
| `SLMP_TOKEN` | (nincs) | Ha be van állítva, minden `/api/` hívás tokent igényel. |

LAN-eléréshez + hitelesítéssel:

```bash
SLMP_HOST=0.0.0.0 SLMP_TOKEN=valami-erős-titok python3 app.py
```

Ekkor a weblapon az „API token” mezőbe ugyanezt a tokent kell beírni.

## Biztonság

Ez egy **ICS/PLC vezérlő** eszköz — PLC-be írni fizikai következménnyel járhat.
Az automata biztonsági review három pontot jelzett, ezeket így kezeljük:

1. **Flask debug mód (RCE):** alapból **kikapcsolva**; csak `SLMP_DEBUG=1`
   mellett aktiválódik. Ne használd elérhető hálózaton.
2. **Hitelesítés:** opcionális, `SLMP_TOKEN` környezeti változóval bekapcsolható
   Bearer/`X-API-Token` token. **Ha a szervert a localhoston kívül is eléri
   bárki, mindenképp állíts be tokent** (vagy tedd reverse proxy mögé mTLS-sel).
   Alapból az `SLMP_HOST=127.0.0.1` kötés miatt csak a helyi gépről érhető el.
3. **Tetszőleges IP/port elérés (SSRF / portszkenner):** ez részben *funkció* —
   a cél, hogy a PLC IP/portja a weblapon beállítható legyen. Ha nem megbízható
   hálózaton fut, korlátozd az elérhető célokat (pl. tűzfal/reverse proxy a
   PLC felé), és kapcsold be a tokent. A `/api/test` a kapcsolódási hibát
   visszaadja a diagnosztika kedvéért — megbízhatatlan környezetben ez
   információt szivárogtathat, ezért ott auth mögé tartozik.

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

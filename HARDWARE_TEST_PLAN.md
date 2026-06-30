# Plan testów na sprzęcie i napraw

Znane huby testowe:

| Hub | Domyślny adres | Uwagi |
|---|---|---|
| SBUS | `http://<SBUS_HUB_IP>` | może używać statycznego tokenu API |
| WTP | `http://<WTP_HUB_IP>` | login hasłem przez `/api/v1/login` |
| Video | `http://<VIDEO_HUB_IP>` | kamery IP/ONVIF, wymaga osobnej walidacji |

Sekrety nie mogą być zapisane w repozytorium. Testy live uruchamiaj przez env:

```bash
export SINUM_SMOKE_HUBS="WTP=http://<WTP_HUB_IP>,SBUS=http://<SBUS_HUB_IP>,VIDEO=http://<VIDEO_HUB_IP>"
export SINUM_USERNAME="admin"
export SINUM_PASSWORD="<hub-password>"
python3 scripts/hardware_smoke_check.py
```

Dla hubów z tokenem można użyć zmiennej per label, np. `SINUM_SBUS_TOKEN`.
Token HA podawaj wyłącznie poza repo, np. jako sekret CI lub lokalny env.

---

## Smoke test sprzętowy (2026-06-24)

Read-only test API wykonany na obu hubach (logowanie + odczyt endpointów krytycznych):

| Hub | Login | `/api/v1/info` | `/api/v1/devices/wtp` | `/api/v1/devices/sbus` | `/api/v1/devices/virtual` |
|---|---|---|---|---|---|
| `<WTP_HUB_IP>` (WTP) | 200 | 200 | 200 | 200 | 200 |
| `<SBUS_HUB_IP>` (SBUS) | 200 | 200 | 200 | 200 | 200 |

Wniosek: łączność i autoryzacja działają, kluczowe endpointy zwracają poprawne odpowiedzi.

## Smoke test sprzętowy (2026-06-30)

Read-only smoke wykonany na pięciu aktywnych hubach przez `scripts/hardware_smoke_check.py`.
Źródło: `docs/hardware_smoke_latest.md`.

| Hub | `/api/v1/info` | `/api/v1/devices/wtp` | `/api/v1/devices/sbus` | `/api/v1/devices/virtual` |
|---|---:|---:|---:|---:|
| tablica-wtp (`<WTP_HUB_IP>`) | 200 | 200 | 200 | 200 |
| sinum-tablica-sbus-1 (`<SBUS_HUB_IP>`) | 200 | 200 | 200 | 200 |
| tablica-video-nowa (`<VIDEO_HUB_IP>`) | 200 | 200 | 200 | 200 |
| tablicaKlimak (`<KLIMAK_HUB_IP>`) | 200 | 200 | 200 | 200 |
| sinum-tablica-sbus2 (`<SBUS2_HUB_IP>`) | 200 | 200 | 200 | 200 |

Dodatkowo:
- HIL API coverage: 5/5 PASS, 0 critical failures.
- HIL smoke: 5/5 PASS.
- Kamera `tablica-video-nowa`: snapshot device `27` zwrócił HTTP 200.
- HIL WebSocket format: 4/4 non-video huby PASS.
- HA/RPi deploy check: zainstalowany manifest `0.5.21`, 5 config entries Sinum, registry migration przez HA WebSocket API usunęła 322 stare kolizje, pozostałe kandydaty migracji: 0.
- Finalny post-deploy smoke: 5/5 hubów PASS, źródło `docs/hardware_smoke_latest.md`.

---

## Bramka wydania (CC + sprzęt)

Ten projekt traktuje testy jako walidację funkcji, nie "liczbę testów".
Przed każdym release obowiązuje bramka:

1. **CC (Coverage Check)** w CI (`ci.yml`) musi przejść z progiem `--cov-fail-under=80`.
2. **Functional Smoke Tests** (`tests.yml`) muszą przejść na PR/release.
3. **Manualny test sprzętowy** poniżej musi zostać odhaczony i udokumentowany.

### Manualny smoke test sprzętowy (release checklist)

Wykonaj na żywych hubach SBUS/WTP i zapisz wynik (OK/NOK + krótka notatka):

| Obszar | Scenariusz | Wynik |
|---|---|---|
| API/Auth | Ponowne logowanie token/JWT po restarcie HA | ☐ |
| MQTT | Zmiana stanu urządzenia propaguje się < 1 s | ☐ |
| Climate | `set_temperature` i `set_hvac_mode` działają | ☐ |
| Light | SBUS RGB: kolor + jasność + temp. barwowa | ☐ |
| Cover | Brama/roleta reaguje na open/close/stop | ☐ |
| Switch | Relay on/off zgodny ze stanem fizycznym | ☐ |
| Sensor | Odczyty temperatury/wilgotności bez regresji | ☐ |

Release bez pełnego przejścia tej checklisty powinien być traktowany jako RC, nie final.

---

## ELEMENT 1: RGB controller — jasność/kolor/temperatura
**Status: DONE ✓ (2026-06-22)**

### Metoda:
SBUS rgb_controller NIE obsługuje REST PATCH dla color/brightness — pola są read-only.
Rozwiązanie: trwała scena Lua per urządzenie (PATCH lua + activate).

### Potwierdzone Lua calls (SBUS):
- `sbus[id]:call("set_color", {"#RRGGBB", 200})` — zmienia kolor, zachowuje brightness
- `sbus[id]:call("set_brightness", {pct})` — zmienia jasność 0-100
- `sbus[id]:call("set_temperature", {kelvin, pct})` — ustawia temperaturę barwową

### Wyniki testów na sprzęcie (device 119 SBUS):
- turn_on(hs_color=[0,100], brightness=127) → bright=50, led=#800000 (czerwony 50%) ✓
- turn_on(hs_color=[120,100], brightness=255) → bright=100, led=#00ff00 (zielony 100%) ✓
- turn_on(brightness=77) → bright=30, led=#004d00 (zachował kolor, zmienił brightness 30%) ✓
- turn_on(color_temp_kelvin=6500) → mode=temperature ✓
- turn_off → state=False ✓

### Implementacja:
- `api.py`: `create_scene`, `patch_scene_lua`, `delete_scene`, `get_or_create_scene`
- `light.py` SinumBusRgbLight: `_ensure_lua_scene()`, `_run_lua()`, przepisany `async_turn_on`
- WTP rgb_controller: REST PATCH (Lua nie działa na WTP firmware RGB-P4 v1.1.1)

### Znane ograniczenia:
- WTP rgb_controller (226): Lua nie działa, REST color/brightness może być ignorowane w trybie temperature
- Po zmianie koloru przez Lua, harmonogram SBUS może przywrócić tryb temperature przy kolejnym cyklu

---

## ELEMENT 2: Dimmer (WTP/SBUS) — brightness
**Status: DONE ✓ (2026-06-22)**

### Wyniki testów (light.dimmer_122 → SBUS device 122):
- turn_on(brightness=128) → hub target_level=50 (128/255×100) ✓
- turn_on(brightness=255) → hub target_level=100 ✓
- turn_off → hub state=False ✓

---

## ELEMENT 3: Climate (termostat) — set_hvac_mode/set_temperature
**Status: DONE ✓ (2026-06-22)**

### Wyniki testów (climate.parter_1_termostat_1):
- set_temperature(22.0) → HA temperature=22.0 ✓
- set_hvac_mode(off) → HA state=off ✓
- set_hvac_mode(heat) → HA state=heat ✓

---

## ELEMENT 4: Cover (roleta/brama) — open/close/stop/position
**Status: PARTIAL (2026-06-22)**

### Wyniki testów:
- cover.brama (gate): komendy open/close dostarczone, state=open (brama fizycznie otwarta)
- cover.wirtualny_integrator_rolet: state=unknown, pos=None — wirtualne integratory nie mają feedbacku pozycji z fizycznych urządzeń WTP
- WTP hub: 0 urządzeń typu "blind" (rolety kontrolowane przez virtual integrators)

### Do zbadania:
- Czy komendy open/close dla wirtualnych integratorów docierają do hubu
- Brama: sprawdzić czy state zmienia się po czasie

---

## ELEMENT 5: Switch (relay) — on/off
**Status: DONE ✓ (2026-06-22)**

### Wyniki testów (switch.wirtualny_integrator_przekaznikow):
- turn_on → state=on ✓
- turn_off → state=off ✓

---

## ELEMENT 6: Sensor — odczyty temperatury/wilgotności
**Status: DONE ✓ (2026-06-22)**

### Wyniki:
- 374 sensory temperature/humidity w HA
- Porównanie z climate.current_temperature:
  - parter_3_temperatura: HA=26.5°C, climate.current=26.6°C ✓ (±0.1)
  - parter_5_temperatura: HA≈31.5°C, climate.current=31.5°C ✓
- Sensory z 0.0°C: termostaty bez fizycznego czujnika (current=None w climate) — poprawne zachowanie

### Znane issue:
- Termostaty bez czujnika pokazują 0.0°C zamiast "unavailable" — kosmetyczne

---

## Realizacja

Każdy element: test na sprzęcie → naprawić kod jeśli coś nie gra → test jednostkowy → przejść dalej.

## Podsumowanie

| Element | Status | Uwagi |
|---------|--------|-------|
| 1: RGB | ✓ DONE | Lua scene-based, działa pełna kontrola |
| 2: Dimmer | ✓ DONE | target_level działa poprawnie |
| 3: Climate | ✓ DONE | temp i hvac_mode działają |
| 4: Cover | PARTIAL | gate OK, virtual integrators bez pozycji |
| 5: Switch | ✓ DONE | on/off działa |
| 6: Sensor | ✓ DONE | wartości poprawne, 0.0 dla brak czujnika |

# Sinapse — integracja Sinum dla Home Assistant

**Sinapse** łączy centralę automatyki budynkowej [TECH Sterowniki](https://www.techsterowniki.pl) **Sinum EH-01** z Home Assistant przez sieć lokalną. Urządzenia fizyczne i wirtualne z centrali są widoczne w HA jako natywne encje z pełnym odczytem, sterowaniem i aktualizacjami stanu w czasie rzeczywistym.

**Język:** [English](README.md) | Polski

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/testy-1648%20OK-brightgreen.svg)](tests/)
[![CC Gate](https://img.shields.io/badge/CC-%E2%89%A44%20everywhere-brightgreen.svg)](tests/test_code_quality.py)
[![Version](https://img.shields.io/badge/wersja-0.5.21-blue.svg)](custom_components/sinum/manifest.json)
[![License](https://img.shields.io/badge/licencja-Source%20Available-lightgrey.svg)](LICENSE)

---

## Co zyskujesz

- **5 produkcyjnych central** skonfigurowanych w Home Assistant; 4 123 encje Sinum w registry przed oczyszczeniem kolizji
- **12 platform encji**: climate, sensor, binary\_sensor, switch, cover, light, event, button, number, update, alarm\_control\_panel, camera
- **7 lokalnych powierzchni API**: Virtual, WTP, SBUS, LoRa, SLINK, Modbus, Video — odpytywane równolegle co 30 s
- **Aktualizacje w czasie rzeczywistym** przez WebSocket (opóźnienie \< 1 s), most MQTT jako wariant awaryjny
- **1 648 przechodzących testów** w 46 plikach, CC ≤ 4 w każdej funkcji, czysty ruff i mypy

---

## Szybki start

```
1. HACS → Integrations → ⋮ → Custom repositories
   URL: https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
   Category: Integration

2. Zainstaluj "Sinum (Sinapse)" → Uruchom ponownie Home Assistant

3. Settings → Devices & Services → Add Integration → wyszukaj "Sinum"
   Wpisz adres IP centrali i token API

4. Settings → … → Sinum → Configure → włącz WebSocket real-time transport
```

→ **[Pełny przewodnik instalacji ze zrzutami ekranu](docs/installation.pl.md)**

---

## Dokumentacja

| Dokument | Zawartość |
|---|---|
| [Przewodnik instalacji](docs/installation.pl.md) | HACS, instalacja ręczna, generowanie tokena, zrzuty ekranu |
| [Referencja encji](docs/entities.pl.md) | Wszystkie platformy, atrybuty, przykłady automatyzacji |
| [Transport czasu rzeczywistego](docs/real-time.pl.md) | Konfiguracja WebSocket + most MQTT (wariant awaryjny) |
| [Przewodnik developera](docs/development.pl.md) | Środowisko, testy, reguły CC, nowe typy urządzeń |
| [Historia zmian](CHANGELOG.md) | Pełna historia wersji |
| [Bezpieczeństwo](SECURITY.md) | Zgłaszanie podatności |
| [Wkład w projekt](CONTRIBUTING.md) | Jak współtworzyć, styl kodu, lista kontrolna PR |

---

## Architektura

```
Centrala Sinum
    │  REST API (HTTP/JSON)  PATCH /api/v1/devices/{magistrala}/{id}
    ▼
SinumClient (api.py)
    │  aiohttp · auto-odświeżanie JWT · ponowna próba przy 408 · SinumNotSupportedError
    ▼
SinumCoordinator (coordinator.py)
    │  DataUpdateCoordinator · równoległy odczyt magistral · fallback na cache
    │  śledzenie removed_ids → czyszczenie przestarzałych encji z rejestru
    │
    ├──► Platformy encji (climate · sensor · switch · cover · light · …)
    │    Odczyt: coordinator.{magistrala}_devices[id]
    │    Zapis: coordinator.client.patch_{magistrala}_device(id, payload)
    │
    ├──► Most WebSocket (websocket.py)       ← zalecane
    │    Centrala wysyła zdarzenia device_state_changed
    │    Cache koordynatora aktualizowany natychmiast → encje odświeżane < 1 s
    │
    └──► Most MQTT (mqtt.py + lua_scripts/mqtt_bridge.lua)  ← wariant awaryjny
         Skrypt Lua w centrali publikuje zmiany do brokera MQTT
         Integracja subskrybuje i aktualizuje cache koordynatora
```

**Logowanie**: preferowany statyczny token API (bez wygaśnięcia). Alternatywnie login + hasło z JWT z automatycznym odświeżaniem przy 401.

**Obsługa błędów**: `SinumConnectionError` przy problemach sieciowych/JSON. Koordynator zwraca stan z cache podczas niedostępności centrali. Operacje zapisu trafiają do użytkownika jako `HomeAssistantError` w UI HA. HTTP 408 (zajęta magistrala) — jedna ponowna próba po 1 s.

---

## Obsługiwane urządzenia

### Platformy encji

| Platforma | Zakres |
|---|---|
| `climate` | Termostaty wirtualne · fan coile WTP/SBUS · regulatory temperatury · manager pompy ciepła |
| `sensor` | Temperatura · wilgotność · CO₂ · ciśnienie · natężenie światła · PM · IAQ · moc · energia · napięcie · prąd · pogoda · diagnostyka centrali · Energy Center · status automatyzacji · harmonogramy |
| `binary_sensor` | Zalanie · ruch · otwarcie · dym · wejście dwustanowe · stan zaworu fan coila WTP · łączność urządzeń nadrzędnych |
| `switch` | Integratory przekaźników · przekaźniki WTP/SBUS · elektrozaczep · pompa zaworu · zawór wspólny |
| `cover` | Integratory rolet wirtualnych · brama · sterowniki rolet WTP/SBUS |
| `light` | Integratory ściemniaczy/RGB · ściemniacze WTP/SBUS · sterowniki RGB WTP/SBUS |
| `event` | Zdarzenia przycisków fizycznych — idealne do automatyzacji HA |
| `button` | Sceny Sinum Lua (uruchamiane przez `POST /activate`) |
| `number` | Numeryczne zmienne środowiskowe Lua · wyjście analogowe SBUS (0–10 V) |
| `update` | Śledzenie firmware urządzeń nadrzędnych |
| `alarm_control_panel` | System alarmowy (jeśli dostępny w centrali) |
| `camera` | Kamery IP/ONVIF przez proxy snapshotów centrali |

### Typy urządzeń na magistralach

**Virtual** — `thermostat` · `relay_integrator` · `blind_controller_integrator` · `gate` · `wicket` · `dimmer_rgb_controller_integrator` · `dimmer_rgb_integrator` · `heat_pump_manager`

**WTP** — `temperature_sensor` · `humidity_sensor` · `pressure_sensor` · `light_sensor` · `co2_sensor` · `iaq_sensor` · `aq_sensor` · `motion_sensor` · `flood_sensor` · `opening_sensor` · `smoke_sensor` · `two_state_input_sensor` · `relay` · `dimmer` · `rgb_controller` · `blind_controller` · `energy_meter` · `fan_coil` · `fan_coil_v2` · `temperature_regulator` · `button`

**SBUS** — `temperature_sensor` · `humidity_sensor` · `light_sensor` · `motion_sensor` · `two_state_input_sensor` · `analog_input` · `analog_output` · `impulse_meter` · `relay` · `dimmer` · `rgb_controller` · `fan_coil` · `temperature_regulator` · `button` · `valve_pump` · `common_valve` · `pulse_width_modulation` · `blind_controller` · `energy_meter`

**LoRa** — `temperature_sensor` · `humidity_sensor` · `opening_sensor` · `flood_sensor` · `relay` · `two_state_input_sensor` · `smoke_sensor`

---

## Konfiguracja

### Opcje integracji (Settings → … → Sinum → Configure)

| Opcja | Domyślnie | Opis |
|---|---|---|
| Scan interval | 30 s | Interwał odpytywania REST (10–300 s). Zawsze aktywne jako ścieżka kontrolna. |
| Enable WebSocket real-time transport | wyłączone | Stałe połączenie WebSocket z centralą dla natychmiastowych aktualizacji. Zalecane. |
| WebSocket endpoint path | `/api/v1/ws` | Zmień tylko jeśli Twój firmware centrali używa innej ścieżki. |
| Enable MQTT real-time transport | wyłączone | Starszy wariant push przez Lua i MQTT. Używaj tylko gdy WebSocket nie działa. |
| MQTT topic prefix | `sinum` | Musi być zgodny z `TOPIC_PREFIX` w skrypcie `mqtt_bridge.lua`. |

### Reautoryzacja

Jeśli token lub hasło ulegną zmianie, HA wyświetli powiadomienie. Kliknij **Re-authenticate** i wpisz nowe dane — restart nie jest potrzebny.

### Wiele central

Wiele central Sinum można dodać jako oddzielne wpisy konfiguracyjne. Usługi (`sinum.send_notification`, `sinum.update_schedule`, `sinum.upload_mqtt_bridge`) akceptują opcjonalne pole `entry_id` wskazujące konkretną centralę.

---

## Usługi HA

### `sinum.send_notification`

Wysyła powiadomienie push przez centralę do aplikacji mobilnej Sinum.

```yaml
service: sinum.send_notification
data:
  title: "Home Assistant"
  message: "Drzwi wejściowe otwarte od 10 minut."
```

### `sinum.update_schedule`

Aktualizuje harmonogram termiczny Sinum. Przydatne do dynamicznych programów grzewczych z automatyzacji HA.

```yaml
service: sinum.update_schedule
data:
  schedule_id: 3
  payload:
    name: "Tryb letni"
    periods:
      - start: "08:00"
        temperature: 210   # °C × 10
```

### `sinum.upload_mqtt_bridge`

Renderuje i wgrywa skrypt Lua mostu MQTT do sceny w centrali. Zastępuje ręczne kopiowanie kodu.

```yaml
service: sinum.upload_mqtt_bridge
data:
  mqtt_scene_id: 1    # ID sceny w centrali do nadpisania
  mqtt_client_id: 1   # ID klienta MQTT z web UI Sinum
  dry_run: false      # true = podgląd skryptu Lua bez wgrywania
```

---

## Testowane centrale

| Centrala | IP | Firmware | Virtual | WTP | SBUS | SLINK | Modbus | Video | Alarm |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| tablica-wtp | 10.0.61.132 | 1.24.0-alpha.2 | 30 | 254 | 8 | 2 | 0 | 0 | 1 |
| sinum-tablica-sbus-1 | 10.0.62.167 | 1.24.0-alpha.4 | 171 | 35 | 436 | 0 | 1 | 0 | 3 |
| tablica-video-nowa | 10.0.62.117 | 1.24.0-alpha.4 | 6 | 21 | 77 | 0 | 1 | 6 | 0 |
| tablicaKlimak | 10.0.61.114 | 1.24.0-alpha.4 | 13 | 41 | 25 | 0 | 5 | 0 | 0 |
| sinum-tablica-sbus2 | 10.0.62.209 | 1.24.0-alpha.3 | 29 | 50 | 191 | 2 | 3 | 0 | 16 |

Read-only smoke, API coverage, HIL smoke i testy WebSocket przeszły na żywym sprzęcie (2026-06-30). HA ma obecnie 5 config entries Sinum oraz 582 encje registry z sufiksami kolizyjnymi oczekujące na migrację.

`tablica-wtp` (instalacja WTP-heavy): 108 przekaźników WTP, 18 sterowników rolet, 15 regulatorów temperatury, 28 przycisków, pełny zestaw czujników (temperatura/wilgotność/CO₂/IAQ/ciśnienie/światło/ruch/zalanie), 1 fan coil, 1 licznik energii.

`sinum-tablica-sbus-1` (instalacja SBUS-heavy): 83 termostaty wirtualne, 51 regulatorów SBUS, 69 przekaźników SBUS, 38 ściemniaczy SBUS, 6 sterowników RGB SBUS, 30 przycisków SBUS, 134 czujniki temperatury SBUS, 46 czujników wilgotności SBUS, 1 manager pompy ciepła.

---

## Znane ograniczenia

| Ograniczenie | Szczegóły |
|---|---|
| **Typ akcji przycisku SBUS bez transportu push** | Centrala SBUS zeruje pole `action` od razu po naciśnięciu. Naciśnięcie jest wykrywane przez `buttons_count`, ale `action` będzie `None` bez WebSocket/MQTT. |
| **Typ wirtualny `custom_device`** | Kontrakty Lua różnią się między instalacjami — nie mapowany na encje HA. Używaj scen i automatyzacji. |
| **`thermostat_output_group`** | Tylko diagnostyczny sensor (liczba wyjść), bez encji sterujących. |
| **WTP RGB w trybie temperatury barwowej** | Firmware centrali ignoruje wartości koloru gdy aktywny jest tryb color-temperature. Działa tylko `color_temp_kelvin`. |
| **Integratory rolet wirtualnych** | Raportują `position = None` gdy brak podłączonych sterowników fizycznych (kwestia konfiguracji centrali). |
| **Energy Center** | Sensory pojawiają się tylko gdy firmware eksponuje `/api/v1/energy-center/*`. |
| **Harmonogramy** | Tylko odczyt + usługa `sinum.update_schedule`. Pełny edytor UI harmonogramów nie jest zaimplementowany. |
| **LoRa / SLINK / Video** | Wymagają specyficznych modułów sprzętowych. Przekaźniki i liczniki energii SLINK są mapowane; kamery używają ścieżek snapshot/WebRTC przez hub. Zapis LoRa jest zaimplementowany, ale wymaga walidacji na przekaźniku LoRa. |
| **Błędy 408 firmware alpha** | Sporadyczne przy odpytywaniu magistral. Integracja ponawia raz, potem serwuje stan z cache. |

---

## Bezpieczeństwo

Centrala komunikuje się po HTTP w sieci lokalnej.

- **Sieć**: umieść centralę na dedykowanym VLAN IoT. Zezwól tylko HA na dostęp do portu 80. Zablokuj bezpośredni dostęp z internetu.
- **Token zamiast hasła**: wygeneruj dedykowany token API dla integracji HA. Jest ograniczony zakresem, nie daje dostępu do powłoki i można go odwołać niezależnie.
- **Nie ujawniaj**: nie wklejaj tokena do zgłoszeń GitHub, logów, zrzutów ekranu ani wiadomości. Integracja usuwa go z diagnostyki HA.
- **TLS (opcjonalnie)**: umieść odwrotne proxy nginx lub Caddy na tym samym VLAN, które terminuje TLS i przekierowuje do centrali.
- **Ochrona reautoryzacji**: integracja blokuje reautoryzację po 5 kolejnych nieudanych próbach na 5 minut.

Szczegóły: [SECURITY.md](SECURITY.md)

---

## Oficjalne zasoby Sinum

| Zasób | URL |
|---|---|
| Dokumentacja REST API Sinum | <https://apidocs.sinum.tech/> |
| Podręcznik skryptowania Lua | <https://www.techsterowniki.pl/!uploads/SINUM/LUA_user_manual.pdf> |
| FAQ Sinum | <https://www.techsterowniki.pl/blog/system-sinum-najczesciej-zadawane-pytania> |
| Baza wiedzy | <https://www.techsterowniki.pl/blog/kategoria/sinum> |
| Integracja z Google Home | <https://www.techsterowniki.pl/blog/polaczenie-centrali-sinum-z-usluga-google-home> |
| Aplikacja Sinum Cloud | <https://sinum.tech/sign-in> |

---

## Informacja prawna

To nieoficjalny projekt społecznościowy. Nie jest powiązany z TECH Sterowniki, autoryzowany przez nich ani przez nich utrzymywany. Nazwy „TECH", „Sinum" oraz powiązane oznaczenia mogą być znakami towarowymi ich właścicieli. Integracja korzysta z lokalnego API centrali do sterowania urządzeniami we własnej instalacji użytkownika. Użytkownik odpowiada za zgodność użycia z prawem i regulaminami dostawcy.

---

## Licencja

**Source Available — Ograniczone użycie komercyjne**

© 2026 Tomasz Panek · Wszelkie prawa zastrzeżone

Użytek osobisty i niekomercyjna automatyka domowa: **bezpłatne**.  
Wdrożenie komercyjne, organizacyjne lub produktowe: **wymagana licencja** — kontakt: zaba9214@gmail.com.

Pełne warunki: [LICENSE](LICENSE)

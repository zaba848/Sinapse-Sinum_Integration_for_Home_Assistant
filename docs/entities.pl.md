# Referencja encji — Sinapse / Sinum Integration

**[← Powrót do README](../README.pl.md)**

---

## Spis treści

- [Przegląd platform](#przegląd-platform)
- [Climate — klimat](#climate--klimat)
- [Sensor — czujnik](#sensor--czujnik)
- [Binary Sensor — czujnik binarny](#binary-sensor--czujnik-binarny)
- [Switch — przełącznik](#switch--przełącznik)
- [Cover — osłony](#cover--osłony)
- [Light — oświetlenie](#light--oświetlenie)
- [Event — zdarzenia przycisków](#event--zdarzenia-przycisków)
- [Button — sceny Sinum](#button--sceny-sinum)
- [Number — liczba](#number--liczba)
- [Update — aktualizacje](#update--aktualizacje)
- [Alarm Control Panel — panel alarmowy](#alarm-control-panel--panel-alarmowy)
- [Camera — kamera](#camera--kamera)
- [Dostępność urządzeń](#dostępność-urządzeń)

---

## Przegląd platform

| Platforma | Opis | Magistrale |
|---|---|---|
| `climate` | Termostaty, fan coile, regulatory, manager pompy ciepła | Virtual, WTP, SBUS |
| `sensor` | Temperatura, wilgotność, CO₂, energia, diagnostyka i inne | Virtual, WTP, SBUS, LoRa, SLINK, Modbus |
| `binary_sensor` | Zalanie, ruch, otwarcie, dym, stan zaworu, łączność | WTP, SBUS, LoRa |
| `switch` | Przekaźniki, elektrozaczep, pompa zaworu, zawór wspólny | Virtual, WTP, SBUS, LoRa |
| `cover` | Sterowniki rolet, bramy | Virtual, WTP, SBUS |
| `light` | Ściemniacze, sterowniki RGB | Virtual, WTP, SBUS |
| `event` | Zdarzenia naciśnięcia fizycznych przycisków | WTP, SBUS |
| `button` | Sceny Lua Sinum | Poziom centrali |
| `number` | Zmienne środowiskowe Lua, wyjście analogowe SBUS | Virtual, SBUS |
| `update` | Śledzenie firmware urządzeń nadrzędnych | Poziom centrali |
| `alarm_control_panel` | System alarmowy | Poziom centrali |
| `camera` | Kamery IP/ONVIF — zdjęcia RTSP + obraz na żywo WebRTC | Poziom centrali |

---

## Climate — klimat

### Termostat wirtualny (`thermostat`)

Steruje wirtualną strefą termostatyczną.

- **Tryby HVAC**: `heat` / `off`
- **Zakres temperatury**: odczytywany z centrali (`target_temperature_minimum` / `target_temperature_maximum`); wartości spoza zakresu są ograniczane przed wysłaniem
- **Temperatura bieżąca**: wyświetlana gdy czujnik fizyczny jest powiązany; w przeciwnym razie `unknown`
- **Format unique_id**: `{entry_id}_virtual_{device_id}`

### Fan Coil — WTP (`fan_coil`, `fan_coil_v2`)

Pełne sterowanie HVAC jednostką fan coil WTP.

- **Tryby HVAC**: `heat`, `cool`, `fan_only`, `off`
- **Tryby wentylatora**: `low`, `medium`, `high`
- **Temperatura zadana**: zapis przez REST PATCH

Fan coile WTP eksponują też encję `binary_sensor` ze stanem zaworu (`is_on = zawór otwarty`).

### Fan Coil — SBUS (`fan_coil`)

Identyczny jak fan coil WTP powyżej, ale komunikuje się przez magistralę SBUS.

### Regulator temperatury (`temperature_regulator` — WTP i SBUS)

Regulator grzewczy włącz/wyłącz z kontrolą temperatury.

- **Tryby HVAC**: `heat` / `off`
- **Temperatura zadana**: odczyt/zapis

### Manager pompy ciepła (`heat_pump_manager`)

Zarządza grupą centralnej pompy ciepła.

- **Tryby HVAC**: `heat`, `cool`, `off`
- **Temperatura zadana**: stosowana do zarządzanej grupy
- **Dodatkowe atrybuty stanu**: stany termostatów podrzędnych jako dane diagnostyczne

---

## Sensor — czujnik

### Jakość odczytu

Czujniki temperatury/wilgotności centrali zwracają `unknown` (nie `0.0`) gdy:
- Surowa wartość z centrali wynosi `0` i urządzenie nie ma czujnika fizycznego (`zero_is_unavailable = True`)
- Urządzenie raportuje `status = "offline"`
- Obecna jest wartość strażnikowa centrali `−3276.8` (wewnętrzny kod SBUS oznaczający „brak odczytu")

Zapobiega to pojawianiu się fałszywych odczytów 0,0 °C na wirtualnych termostatach bez powiązanego sprzętu.

### Typy czujników

| Klasa urządzenia | Jednostka | Skala | Uwagi |
|---|---|---|---|
| Temperatura | °C | ×0,1 | Surowa wartość to °C × 10 |
| Wilgotność | %RH | ×0,1 | Surowa wartość to %RH × 10 |
| CO₂ | ppm | ×1 | |
| Natężenie światła | lx | ×1 | |
| Ciśnienie | hPa | ×0,1 | |
| PM2,5 | µg/m³ | ×1 | |
| PM10 | µg/m³ | ×1 | |
| Indeks IAQ | — | ×1 | Wskaźnik jakości powietrza |
| Moc | W | ×1 | |
| Energia | kWh | ×0,001 | Surowa wartość w Wh |
| Napięcie | V | ×0,1 | |
| Prąd | A | ×0,01 | |
| Licznik impulsów | — | ×1 | Licznik skumulowany |
| Wejście analogowe | V | mapowane 0–10 V | Skala SBUS 0–100 |
| Pogoda | — | — | Enum: słonecznie, pochmurnie, deszcz, śnieg, … |

### Czujniki specjalne

**Diagnostyka centrali**: wersja firmware, wersja API, nazwa centrali, czas pracy — eksponowane jako encje `sensor.sinum_*_hub_info_*`.

**Energy Center**: temperatura zasilania, temperatura zasobnika, statystyki produkcji — pojawiają się tylko gdy firmware centrali udostępnia `/api/v1/energy-center/*`.

**Status automatyzacji**: znacznik czasu `last_run` i tekst `status` dla każdego skryptu automatyzacji Sinum.

**Podsumowania harmonogramów**: nazwa aktywnego okresu i temperatura zadana dla harmonogramów termicznych.

**Temperatura zadana regulatora SBUS**: temperatura zadana jako dedykowany czujnik (uzupełnienie encji climate).

### Czujniki LoRa

Urządzenia LoRa komunikują się przez sieć bezprzewodową małej mocy. Każde urządzenie fizyczne jest pogrupowane pod **urządzeniem nadrzędnym** (brama Lora device) za pomocą mechanizmu `via_device` HA — w HA widoczna jest jedna karta urządzenia na fizyczny czujnik z wszystkimi jego encjami.

**Obsługiwane typy urządzeń LoRa** (sensor + binary_sensor):

| Typ urządzenia centrali | Czujniki | Binary sensory |
|---|---|---|
| `temperature_sensor` | temperatura, poziom baterii %, sygnał % | — |
| `humidity_sensor` | wilgotność, poziom baterii %, sygnał % | — |
| `opening_sensor` | poziom baterii %, sygnał % | otwarcie/kontakt |
| `flood_sensor` | poziom baterii %, sygnał % | zalanie |
| `smoke_sensor` | poziom baterii %, sygnał % | dym |
| `relay` | — | — (encja switch) |
| `two_state_input_sensor` | poziom baterii %, sygnał % | wejście dwustanowe |

**Pola rejestru urządzeń HA** (Ustawienia → Urządzenia):

| Pole | Źródło | Przykład |
|---|---|---|
| Numer seryjny | EUI LoRa (pole `eui`) | `70B3D59BA000A200` |
| Firmware | Pole `software_version` | `ACW THO v4.x/v5.x` |
| Producent | Stałe | `TECH Sterowniki` |
| Model | Klasa urządzenia centrali | `Sinum LoRa Temperature Sensor` |

EUI jednoznacznie identyfikuje fizyczny moduł radiowy i pojawia się w rejestrze urządzeń HA pod **Numer seryjny**. Przydatne do identyfikacji krzyżowej z interfejsem webowym Sinum lub serwerem sieci LoRa.

---

## Binary Sensor — czujnik binarny

| Typ urządzenia | Znaczenie `is_on` | Magistrala |
|---|---|---|
| `flood_sensor` | Wykryto zalanie | WTP, SBUS, LoRa |
| `motion_sensor` | Wykryto ruch | WTP, SBUS |
| `opening_sensor` | Kontakt otwarty | WTP, LoRa |
| `smoke_sensor` | Wykryto dym | WTP, LoRa |
| `two_state_input_sensor` | Wejście aktywne | WTP, SBUS |
| Stan zaworu `fan_coil` | Zawór otwarty | WTP |
| Urządzenie nadrzędne | Połączony | Poziom centrali |

### Dodatkowe atrybuty fan coil

Czujniki binarne fan coil WTP eksponują stany biegów jako dodatkowe atrybuty:

```
gear_1_active: true
gear_2_active: false
gear_3_active: false
```

---

## Switch — przełącznik

Fizyczne przekaźniki na magistralach WTP i SBUS oraz wirtualne integratory przekaźników.

### Filtrowanie

Przekaźniki oznaczone etykietą `managed_by_thermostat` w Sinum są **wykluczone** z encji switch — są sterowane przez platformę `climate`. Zapobiega to konfliktom podwójnego sterowania.

### Typy specjalne

| Typ | Opis |
|---|---|
| `relay_integrator` | Wirtualny przekaźnik (bez fizycznej magistrali) |
| `wicket` | Elektrozaczep / zwolnienie drzwi |
| `valve_pump` | Sterownik pompy zaworu SBUS |
| `common_valve` | Zawór wspólny SBUS |

---

## Cover — osłony

### Sterownik rolet — WTP (`blind_controller`)

- **Funkcje**: otwieranie, zamykanie, zatrzymanie, ustawianie pozycji (0–100%)
- **Stan**: `open`, `closed`, `opening`, `closing`, `stopped`
- **Śledzenie pozycji**: z pola `current_opening` centrali
- **Wykrywanie ruchu**: `is_opening` / `is_closing` porównuje `target_opening` z `current_opening`
- **Przywracanie po restarcie**: pozycja przywracana z ostatniego stanu HA

### Integrator rolet wirtualnych (`blind_controller_integrator`)

Takie same funkcje jak roleta WTP. Stan jest `unknown`, a pozycja `None` gdy brak podłączonych sterowników fizycznych (problem konfiguracji centrali, nie błąd integracji).

### Brama — wirtualna (`gate`)

- **Funkcje**: otwieranie, zamykanie, zatrzymanie
- **Automat stanów**: open/close/opening/closing/stopped wyznaczane z pola `state` centrali
- **Pozycja**: nie obsługiwana (bramy nie raportują pozycji)

### Sterownik rolet SBUS (`blind_controller`)

- **Funkcje**: otwieranie, zamykanie, zatrzymanie, ustawianie pozycji, opcjonalnie pochylenie (gdy pola `current_tilt`/`target_tilt` są obecne)
- **Wykrywanie pochylenia**: automatyczne — encja obsługuje `SET_TILT_POSITION` gdy pola pochylenia są obecne w urządzeniu

---

## Light — oświetlenie

### Ściemniacz — WTP / SBUS (`dimmer`)

- **Funkcje**: włącz/wyłącz, jasność 0–100%
- **Sterowanie**: REST PATCH do centrali
- **Tryb koloru**: `BRIGHTNESS`

### Sterownik RGB — WTP (`rgb_controller`)

- **Funkcje**: włącz/wyłącz, jasność, kolor RGB, temperatura barwowa
- **Sterowanie**: REST PATCH
- **Tryb koloru**: `HS` dla koloru, `COLOR_TEMP` dla temperatury barwowej
- **Ograniczenie**: w trybie temperatury barwowej firmware centrali ignoruje wartości koloru; działa tylko `color_temp_kelvin`

### Sterownik RGB — SBUS (`rgb_controller`)

- **Funkcje**: włącz/wyłącz, jasność, kolor RGB, temperatura barwowa
- **Sterowanie**: scena Lua centrali — każda encja RGB SBUS używa dedykowanej trwałej sceny o nazwie `_ha_rgb_sbus_{id}`
- **Sekwencja komend**: GET/POST do find-or-create sceny → PATCH kodu Lua sceny → POST `/activate`
- **Ważne**: `set_color` jest wysyłane przed `set_brightness` — firmware resetuje jasność przy zmianie koloru

### Podświetlenie przycisku (`button`)

Kolor podświetlenia RGB fizycznego przycisku WTP. Pojawia się na stronie konfiguracji urządzenia encji.

- **Kategoria encji**: `config`
- **Funkcje**: włącz/wyłącz, kolor HS
- **Sterowanie**: REST PATCH pola `color`

### Wirtualne integratory ściemniaczy / RGB

Urządzenia wirtualne agregujące fizyczne ściemniacze lub sterowniki RGB. Taki sam interfejs sterowania jak ich fizyczne odpowiedniki.

---

## Event — zdarzenia przycisków

Fizyczne przyciski WTP i SBUS są eksponowane jako encje **Event** (`event.sinum_*`). Każde naciśnięcie generuje zdarzenie `pressed` z typem naciśnięcia.

### Jak działa wykrywanie

Koordynator porównuje dwa pola przy każdym odpytywaniu:

| Pole | Znaczenie |
|---|---|
| `action` | Typ naciśnięcia: `"single"`, `"double"`, `"hold"`, … |
| `buttons_count` | Skumulowany licznik naciśnięć — rośnie przy każdym naciśnięciu |

Oba pola są porównywane z poprzednim odpytywaniem. Zdarzenie generuje się gdy którekolwiek zmieni wartość. `buttons_count` wykrywa szybkie naciśnięcia tego samego typu, które inaczej zostałyby pominięte.

### Opóźnienie wykrywania naciśnięć

| Transport | Typowe opóźnienie |
|---|---|
| Tylko odpytywanie REST | Do 30 s (interwał odpytywania) |
| WebSocket włączony | < 1 s |
| Most MQTT włączony | < 1 s |

### Atrybuty zdarzenia

| Atrybut | Przykład | Opis |
|---|---|---|
| `action` | `"single"`, `"double"`, `"hold"` | Typ naciśnięcia z centrali |
| `buttons_count` | `42` | Skumulowany licznik po stronie centrali |

### Ograniczenie przycisków SBUS

Przyciski SBUS zerują pole `action` do `""` natychmiast po naciśnięciu. Do czasu odpytywania przez koordynator pole `action` może być już puste. Naciśnięcie JEST wykrywane przez `buttons_count`, ale `action` będzie `None` w zdarzeniu. Włącz WebSocket lub MQTT dla wykrywania typu naciśnięcia w czasie rzeczywistym.

### Automatyzowanie naciśnięć przycisków

**Opcja A — Wyzwalacz urządzenia (zalecana dla automatyzacji przez UI):**

```yaml
automation:
  - alias: "Długie naciśnięcie → Scena noc"
    trigger:
      - platform: device
        domain: sinum
        device_id: !secret button_device_id
        type: pressed
        subtype: hold
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.noc
```

**Opcja B — Wyzwalacz stanu:**

```yaml
automation:
  - alias: "Przycisk salonu → przełącz światła"
    trigger:
      - platform: state
        entity_id: event.sinum_przycisk_salon
    action:
      - service: light.toggle
        target:
          area_id: salon
```

**Opcja C — Zdarzenie MQTT (najszybsze, wymaga mostu MQTT):**

```yaml
automation:
  - alias: "Przycisk przez zdarzenie MQTT"
    trigger:
      - platform: event
        event_type: sinum_button_event
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.action == 'single' }}"
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.wieczor
```

---

## Button — sceny Sinum

Sceny Sinum typu `code` są eksponowane jako encje `button`. Naciśnięcie przycisku wywołuje `POST /api/v1/scenes/{id}/activate`.

```yaml
service: button.press
target:
  entity_id: button.sinum_zamknij_rolety
```

Eksponowane są tylko sceny typu `code` — sceny status/trigger są tylko do odczytu (wyświetlane jako czujniki automatyzacji).

---

## Number — liczba

### Zmienne środowiskowe Lua

Zmienne numeryczne współdzielone przez skrypty Lua w centrali. Odczyt i zapis z automatyzacji HA pozwala przekazywać wartości zadane lub warunki wyzwalania do logiki po stronie centrali.

```yaml
# Ustaw wartość zadaną z HA
service: number.set_value
target:
  entity_id: number.sinum_temperatura_sypialnia
data:
  value: 22.5
```

```lua
-- Odczyt w scenie Sinum
local temperatura = variable[1]:getValue()
sbus[42]:setValue("target_temperature", temperatura * 10)
```

### Wyjście analogowe SBUS (0–10 V)

Bezpośrednie sterowanie wyjściem napięciowym. Zakres HA: `0`–`100` mapowany na `0–10 V`.

---

## Update — aktualizacje

Śledzenie firmware urządzeń nadrzędnych. Każde urządzenie nadrzędne Sinum (moduł sprzętowy) pojawia się jako encja `update` pokazująca zainstalowaną wersję firmware. Aktualizacja firmware przez tę encję nie jest obsługiwana — użyj interfejsu webowego Sinum.

---

## Alarm Control Panel — panel alarmowy

Dostępny tylko gdy centrala ma system alarmowy (`/api/v1/devices/alarm-system` zwraca dane).

- **Stany**: `disarmed`, `armed_home`, `armed_away`, `triggered`
- **Dodatkowe atrybuty**: lista wejść w formacie `{klasa}/{id}`
- **Wymagany kod**: zależy od konfiguracji centrali

---

## Camera — kamera

Kamery IP i ONVIF (`ip_camera`, `onvif_camera`) skonfigurowane w Sinum są eksponowane jako encje kamery HA.

- **Snapshoty**: pobierane przez endpoint proxy centrali `/api/v1/devices/video/{id}/snapshot` (JPEG odkodowany z base64).
- **Transmisja na żywo**: włączona dla typów `ip_camera` i `onvif_camera` przez `CameraEntityFeature.STREAM`. HA obsługuje połączenie RTSP wewnętrznie — adres URL nie jest przesyłany do przeglądarki. Przy starcie transmisji odpytywany jest endpoint `/api/v1/devices/video/{id}` celem pobrania niezamaskowanych danych uwierzytelniających. Jeśli centrala nadal maskuje hasło, HA wraca do trybu snapshot.
- **Status**: `is_on = True` gdy status kamery to `"online"`.
- **Marka**: pobierana z pola `variant` centrali (np. `hikvision`); typ `generic` nie wyświetla marki.
- **Dodatkowe atrybuty**: `video_type`, `ip`, `port`, `url_path`, `mac`, `status`, `purpose`, `room_id` — dane uwierzytelniające nigdy nie są eksponowane.
- **Dostępność**: wynika z `CoordinatorEntity.available` (flaga `last_update_success` koordynatora).

---

## Dostępność urządzeń

Wszystkie encje Sinum używają `available = bool(self._device)`. Gdy centrala jest niedostępna i koordynator wraca do cache, wszystkie encje pozostają dostępne ze stanem z cache. Jeśli cache jest pusty (świeży restart HA z niedostępną centralą), encje pokazują `unavailable`.

Gdy urządzenie zostanie trwale usunięte z centrali, encje HA dla tego urządzenia są automatycznie usuwane z rejestru encji i rejestru urządzeń przy kolejnym udanym odświeżeniu koordynatora.

## Nazwy urządzeń w konfiguracji z wieloma centralami

Gdy skonfigurowana jest tylko jedna centrala Sinum, nazwy urządzeń wyświetlane są bez prefiksu (np. `Energy Meter 1`). Gdy aktywne są dwie lub więcej central, nazwa centrali jest automatycznie dodawana jako prefiks do każdej nazwy urządzenia (np. `tablica-wtp: Energy Meter 1`), aby zapobiec kolizjom między identycznie nazwanymi urządzeniami na różnych centralach.

Prefiks jest dodawany dynamicznie — pojawia się gdy tylko załadowany zostanie drugi wpis konfiguracji centrali i znika, gdy liczba powróci do jednej (po restarcie HA).

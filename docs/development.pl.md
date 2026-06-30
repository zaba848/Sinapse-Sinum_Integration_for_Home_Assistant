# Przewodnik dewelopera — Sinapse / Sinum Integration

**[← Powrót do README](../README.pl.md)**

---

## Spis treści

- [Struktura projektu](#struktura-projektu)
- [Środowisko deweloperskie](#środowisko-deweloperskie)
- [Uruchamianie testów](#uruchamianie-testów)
- [Bramki jakości kodu](#bramki-jakości-kodu)
- [Kluczowe elementy wewnętrzne](#kluczowe-elementy-wewnętrzne)
- [Dodawanie nowego czujnika](#dodawanie-nowego-czujnika)
- [Dodawanie nowej platformy encji](#dodawanie-nowej-platformy-encji)
- [Dodawanie nowego typu urządzenia wirtualnego](#dodawanie-nowego-typu-urządzenia-wirtualnego)
- [Pisanie testów](#pisanie-testów)
- [Debugowanie na żywej centrali](#debugowanie-na-żywej-centrali)
- [Wkład w projekt](#wkład-w-projekt)

---

## Struktura projektu

```
custom_components/sinum/
  ├── __init__.py              Punkt wejścia: setup, reload, unload, usługi HA
  ├── api.py                   Klient REST (SinumClient, typy błędów)
  ├── coordinator.py           DataUpdateCoordinator — odpytuje wszystkie magistrale równolegle
  ├── config_flow.py           Konfiguracja UI + reautoryzacja + opcje
  ├── const.py                 Wszystkie stałe: ścieżki API, typy urządzeń, wartości domyślne
  │
  ├── climate.py               Termostaty, fan coile, regulatory, manager pompy ciepła
  ├── sensor.py                Punkt wejścia platformy czujników
  ├── sensor_bus.py            Klasy encji czujników WTP / SBUS / LoRa
  ├── sensor_bus_descriptions.py  Dane SensorDescription + krotki WTP/SBUS/LoRa
  ├── sensor_virtual.py        Wirtualne, pogodowe, Energy Center, czujniki diagnostyczne centrali
  ├── sensor_schedule.py       Czujniki harmonogramów termicznych
  ├── binary_sensor.py         Zalanie, ruch, otwarcie, stan zaworu, łączność
  ├── switch.py                Przekaźniki, elektrozaczep, valve_pump, common_valve
  ├── cover.py                 Sterowniki rolet, bramy
  ├── light.py                 Ściemniacze, RGB (wirtualne + WTP + SBUS)
  ├── button.py                Sceny Sinum jako encje button HA
  ├── event.py                 Zdarzenia naciśnięcia fizycznych przycisków
  ├── number.py                Zmienne Lua + wyjście analogowe SBUS
  ├── camera.py                Kamery IP/ONVIF przez proxy snapshotów centrali
  ├── notify.py                send_notification → powiadomienie push centrali
  ├── update.py                Śledzenie firmware urządzeń nadrzędnych
  ├── alarm_control_panel.py   System alarmowy
  ├── websocket.py             Transport WebSocket (SinumWebSocketBridge)
  ├── mqtt.py                  Starszy transport przez most MQTT
  ├── diagnostics.py           Diagnostyki HA (ukrywa dane uwierzytelniające)
  │
  ├── services.yaml            Schematy usług HA
  ├── strings.json             Napisy UI (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua          Skrypt Lua mostu MQTT v0.8.1 — wgrać do centrali
  └── sinapse_api.lua          Opcjonalny diagnostyczny endpoint HTTP w centrali

tests/
  ├── conftest.py              Fixtures pytest (hass, make_response, itp.)
  ├── fixtures/
  │   └── sinum_devices.json   Przykładowe odpowiedzi API centrali używane w testach
  ├── test_code_quality.py     Bramka CC — wszystkie funkcje muszą mieć CC ≤ 4
  ├── hardware_in_loop/        Skrypty HIL do smoke testów na żywej centrali
  └── test_*.py                1648 przechodzących testów dla wszystkich platform i typów urządzeń
```

---

## Środowisko deweloperskie

```bash
git clone https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
cd sinapse-sinum-integration-for-home-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

Integracja używa Python 3.12+. Wszystkie adnotacje typów są wymagane. Brak magicznych ciągów — dodawaj stałe do `const.py`.

---

## Uruchamianie testów

```bash
# Pełna suita (~9 s)
pytest tests/

# Pojedynczy plik, szczegółowe wyniki
pytest -v tests/test_api.py

# Raport pokrycia kodu
pytest --cov=custom_components/sinum tests/

# Bramka złożoności cyklomatycznej
pytest tests/test_code_quality.py -v
```

Statystyki testów: **1648 przechodzących testów, 5 pominiętych testów live-write, 46 plików testów**, czas wykonania ~10 s. Wszystkie testy niesprzętowe muszą przejść przed mergem.

Markery pomijania:
- testy live-write w `tests/test_api_endpoint_write.py` są pomijane bez `SINUM_WRITE_TESTS=1` i danych dostępowych do live huba
- skrypty HIL w `tests/hardware_in_loop/` są samodzielnymi skryptami Pythona, nie zwykłymi modułami pytest

---

## Bramki jakości kodu

Wszystkie pull requesty muszą przejść:

| Bramka | Narzędzie | Wymaganie |
|---|---|---|
| Lint | `ruff check` | Zero błędów |
| Format | `ruff format` | Brak różnic |
| Typy | `mypy` | Zero błędów |
| Złożoność cyklomatyczna | `radon` przez `tests/test_code_quality.py` | Wszystkie funkcje CC ≤ 4 |
| Testy | `pytest` | Wszystkie 1648 testów niesprzętowych przechodzą |
| HACS | hacs-action | Poprawne `hacs.json` i manifest |

```bash
ruff check custom_components/        # lint
ruff format custom_components/       # auto-formatowanie
mypy custom_components/sinum/        # sprawdzanie typów
pytest tests/test_code_quality.py    # bramka CC
```

### Reguła CC ≤ 4

Każda funkcja w `custom_components/sinum/` musi mieć złożoność cyklomatyczną ≤ 4. Wymuszane przez `tests/test_code_quality.py` (używa `radon`). Słownik `_LEGACY_ALLOWANCE` jest pusty — brak wyjątków.

Gdy dodajesz kod, który przekroczyłby CC 4, wyodrębnij pomocnicze funkcje na poziomie modułu.

Co dodaje +1 do CC w radon:
- `if` / `elif` / `else`
- `for` / `while`
- `try` / `except`
- `and` / `or`
- wyrażenie trójargumentowe (`x if warunek else y`)
- `any()` / `all()` z wyrażeniami generatorów
- Wyrażenia listowe z warunkami

---

## Kluczowe elementy wewnętrzne

### `SinumClient` (`api.py`)

Asynchroniczny klient HTTP. Jedna instancja na wpis koordynatora.

- **Uwierzytelnianie**: statyczny nagłówek `api_token` lub JWT z `_refresh_jwt()` przy 401
- **Ponowna próba**: jedna automatyczna ponowna próba przy HTTP 408 (magistrala zajęta), po 1 s
- **Typy błędów**: `SinumConnectionError` (sieć/timeout/JSON), `SinumAuthError` (dane uwierzytelniające), `SinumNotSupportedError` (404 — endpoint niedostępny w tej centrali)
- **`_read_json()`**: odczytuje surowe bajty, obsługuje puste ciało, rzuca `SinumConnectionError` przy nie-JSON

### `SinumCoordinator` (`coordinator.py`)

Rozszerza `DataUpdateCoordinator`. Przy każdym odpytywaniu:

1. Pobiera pomieszczenia (listy ID urządzeń + metadane pomieszczeń)
2. Pobiera wszystkie kolekcje urządzeń magistral równolegle (`asyncio.gather`)
3. Przy błędzie bulk API: wraca do poprzedniego słownika (encje pozostają żywe)
4. Przy błędzie per-urządzenie: loguje ostrzeżenie, zachowuje starą wartość dla tego urządzenia
5. Wstrzykuje nazwę pomieszczenia, piętra i model sprzętu nadrzędnego do każdego słownika urządzenia
6. Oblicza `removed_ids` (urządzenia nieobecne od ostatniego odpytywania) do czyszczenia rejestru encji

### `SinumSensorDescription` (`sensor_bus_descriptions.py`)

Klasa danych rozszerzająca `SensorEntityDescription`. Dodatkowe pola:

| Pole | Typ | Cel |
|---|---|---|
| `source` | `str` | Magistrala: `"wtp"`, `"sbus"`, `"lora"` |
| `api_key` | `str` | Klucz w surowym słowniku urządzenia |
| `scale` | `float` | Mnożnik surowej wartości (np. `0.1` dla °C×10) |
| `zero_is_unavailable` | `bool` | Zwróć `None` zamiast `0.0` gdy surowa wartość wynosi zero |
| `wtp_type` / `sbus_type` / `lora_type` | `str` | Typ urządzenia dostarczający to pole |

### Dostępność encji

Wszystkie encje Sinum rozszerzają `SinumDeviceAvailableMixin`:

```python
@property
def available(self) -> bool:
    return bool(self._device)
```

`self._device` zwraca słownik urządzenia z koordynatora (`coordinator.wtp_devices.get(id, {})`). Pusty słownik jest fałszywy — encje przechodzą w stan `unavailable` gdy urządzenie nie ma w najnowszych danych koordynatora.

---

## Dodawanie nowego czujnika

### Czujnik na istniejącej magistrali (WTP / SBUS / LoRa)

Dodaj wpis `SinumSensorDescription` do odpowiedniej krotki w `sensor_bus_descriptions.py`:

```python
# W krotce WTP_SENSORS
SinumSensorDescription(
    key="pm2_5",                           # unikalny klucz w tym typie urządzenia
    api_key="pm2_5",                       # nazwa pola w surowym JSON centrali
    source="wtp",
    wtp_type="air_quality_sensor",         # typ urządzenia centrali z tym polem
    device_class=SensorDeviceClass.PM25,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="µg/m³",
    scale=1.0,
    suggested_display_precision=0,
    # zero_is_unavailable=True,            # ustaw jeśli 0 oznacza "brak czujnika"
),
```

Nie są potrzebne inne zmiany — `sensor.py` importuje krotki i tworzy encje automatycznie.

### Czujnik dla nowego typu urządzenia

Jeśli typ urządzenia jest nowy (jeszcze nieobsługiwany przez żaden opis czujnika), najpierw dodaj stałą typu do `const.py`:

```python
WTYPE_AIR_QUALITY = "air_quality_sensor"
```

Następnie dodaj wpisy `SinumSensorDescription` jak powyżej, odwołując się do nowego typu w `wtp_type`.

---

## Dodawanie nowej platformy encji

1. Utwórz `custom_components/sinum/mojaplatforma.py`
2. Zdefiniuj klasę encji rozszerzającą odpowiednią bazę HA:

```python
from homeassistant.components.switch import SwitchEntity
from .coordinator import SinumCoordinator

class MojaEncjaSinum(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        self._coordinator = coordinator
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_wtp_{device_id}_mojaplatforma"

    @property
    def _device(self) -> dict:
        return self._coordinator.wtp_devices.get(self._device_id, {})

    @property
    def available(self) -> bool:
        return bool(self._device)

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs):
        await self._coordinator.client.patch_wtp_device(self._device_id, {"state": True})
        self._coordinator.wtp_devices[self._device_id]["state"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._coordinator.client.patch_wtp_device(self._device_id, {"state": False})
        self._coordinator.wtp_devices[self._device_id]["state"] = False
        self.async_write_ha_state()
```

3. Dodaj `async_setup_entry`:

```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = [
        MojaEncjaSinum(coordinator, device_id, entry.entry_id)
        for device_id, device in coordinator.wtp_devices.items()
        if device.get("type") == "moj_typ_urzadzenia"
    ]
    async_add_entities(entities)
```

4. Dodaj platformę do `PLATFORMS` w `__init__.py`:

```python
from homeassistant.const import Platform

PLATFORMS: list[Platform] = [
    ...,
    Platform.SWITCH,   # już tam jest — dodaj swoją nową
]
```

---

## Dodawanie nowego typu urządzenia wirtualnego

Urządzenia wirtualne żyją w `coordinator.virtual_devices`. Filtruj po `device.get("type")`:

```python
entities = [
    MojeUrządzenieWirtualne(coordinator, device_id, entry.entry_id)
    for device_id, device in coordinator.virtual_devices.items()
    if device.get("type") == "moj_typ_wirtualny"
]
```

Zapisuj zmiany przez `coordinator.client.patch_virtual_device(id, payload)`.

Dodaj stałą typu do `const.py`:

```python
VTYPE_MOJ_TYP_WIRTUALNY = "moj_typ_wirtualny"
```

---

## Pisanie testów

Wszystkie testy żyją w `tests/test_*.py`. Użyj helpera `make_response()` do mockowania odpowiedzi HTTP centrali:

```python
from unittest.mock import AsyncMock, MagicMock
import json

def make_response(status: int, data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=json.dumps(_data).encode())
    return resp
```

Mockuj koordynator dla testów encji:

```python
def _make_coordinator(virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    return c
```

Wymagania dotyczące struktury testów:
- Każdy nowy typ urządzenia: co najmniej 3 testy (tworzenie encji, odczyt stanu, komenda zapisu)
- Każda nowa platforma: test `async_setup_entry`, właściwości encji i akcji zapisu
- Każda ścieżka błędu: test że `HomeAssistantError` jest rzucany ze znaczącym komunikatem

Dodaj dane fixture do `tests/fixtures/sinum_devices.json` dla złożonych payloadów urządzeń współdzielonych między testami.

---

## Debugowanie na żywej centrali

Włącz logowanie debug w `configuration.yaml` HA:

```yaml
logger:
  logs:
    custom_components.sinum: debug
```

Następnie użyj read-only smoke runnera (sekrety przez env, nigdy w repo):

```bash
export SINUM_SMOKE_HUBS="SBUS=http://10.0.62.167"
export SINUM_PASSWORD=twoje_haslo
python3 scripts/hardware_smoke_check.py
```

Do głębszych probe uruchom samodzielne skrypty HIL z tokenem:

```bash
python3 tests/hardware_in_loop/hil_smoke.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
python3 tests/hardware_in_loop/hil_api_coverage.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
python3 tests/hardware_in_loop/hil_websocket.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
```

---

## Wkład w projekt

Zobacz [CONTRIBUTING.md](../CONTRIBUTING.md) dla pełnego przewodnika.

Szybka lista kontrolna przed zgłoszeniem PR:

- [ ] `ruff check custom_components/` przechodzi
- [ ] `ruff format custom_components/` nie daje różnic
- [ ] `mypy custom_components/sinum/` przechodzi
- [ ] `pytest tests/` — wszystkie 1648 testów niesprzętowych przechodzą
- [ ] `pytest tests/test_code_quality.py` — bramka CC czysta (bez nowych wpisów `_LEGACY_ALLOWANCE`)
- [ ] Nowe typy urządzeń mają stałe w `const.py`
- [ ] Nowa funkcjonalność ma co najmniej 3 testy
- [ ] `CHANGELOG.md` zaktualizowany pod `[Unreleased]`

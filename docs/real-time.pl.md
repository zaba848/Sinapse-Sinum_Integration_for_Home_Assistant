# Transport czasu rzeczywistego — Sinapse / Sinum Integration

**[← Powrót do README](../README.pl.md)**

---

Bez transportu czasu rzeczywistego stany encji aktualizują się co 30 sekund (odpytywanie REST). Integracja obsługuje dwa transporty push redukujące to do poniżej 1 sekundy.

| Transport | Opóźnienie | Wymagania | Zalecany |
|---|---|---|---|
| **WebSocket** | < 1 s | Firmware centrali z `/api/v1/ws` | ✅ Tak |
| **Most MQTT** | < 1 s | Broker MQTT + skrypt Lua w centrali | Tylko awaryjnie |
| Odpytywanie REST | 30 s (domyślnie) | Zawsze aktywne | Siatka bezpieczeństwa |

Odpytywanie REST zawsze działa równolegle jako ścieżka uzgadniania — wychwytuje wszystko, co zostało pominięte przez transporty push.

---

## Spis treści

- [Transport WebSocket](#transport-websocket)
- [Most MQTT w czasie rzeczywistym (wariant awaryjny)](#mqtt-most-w-czasie-rzeczywistym-wariant-awaryjny)

---

## Transport WebSocket

WebSocket jest zalecanym transportem. Bez brokera, bez skryptu Lua — centrala wysyła zdarzenia bezpośrednio przez trwałe połączenie.

### Jak działa

Integracja otwiera trwałe połączenie WebSocket do `/api/v1/ws` na centrali. Centrala wysyła tablice zdarzeń `device_state_changed` przy każdej zmianie stanu urządzenia. Każda ramka jest przetwarzana natychmiast: tylko zmienione pole (`details`) jest aktualizowane w cache koordynatora, a dotknięte encje są odświeżane natychmiast.

Przykład payloadu wysyłanego przez centralę:

```json
[
  {
    "data": {
      "type": "device_state_changed",
      "details": "humidity",
      "payload": { "class": "sbus", "id": 12, "humidity": 445 }
    }
  }
]
```

Obsługiwane magistrale: `virtual`, `wtp`, `sbus`, `lora`, `modbus`, `video`.

Jeśli połączenie zostanie przerwane, most automatycznie łączy się ponownie po 5 sekundach.

### Konfiguracja

1. Przejdź do **Ustawienia → Urządzenia i usługi** → znajdź **Sinum (Sinapse)** → kliknij **Konfiguruj**.
2. Włącz **„Włącz transport WebSocket w czasie rzeczywistym"**.
3. Pozostaw ścieżkę jako `/api/v1/ws` (domyślna — zmień tylko gdy firmware centrali używa innego endpointu).
4. Kliknij **Zatwierdź**.

Restart nie jest wymagany. Most łączy się natychmiast.

### Weryfikacja WebSocket

Otwórz **Narzędzia deweloperskie → Zdarzenia → Nasłuchuj zdarzeń** i wpisz `sinum_device_state_changed`. Wywołaj dowolną zmianę stanu w centrali (przełącz przekaźnik, otwórz drzwi, naciśnij przycisk). Zdarzenie powinno pojawić się w czasie poniżej sekundy.

### Rozwiązywanie problemów WebSocket

| Objaw | Prawdopodobna przyczyna | Rozwiązanie |
|---|---|---|
| Encje nadal aktualizują się w 30-sekundowych odstępach | WebSocket nie włączony lub firmware centrali nie ma `/api/v1/ws` | Sprawdź opcje, sprawdź wersję firmware centrali |
| `PermissionError: WebSocket unauthorized` w logach | Token API nieważny lub wygasły | Reautoryzuj integrację |
| Częste rekonekty w logach | Niestabilne połączenie WebSocket centrali | Sprawdź wersję firmware, rozważ most MQTT jako wariant awaryjny |
| Zdarzenia są generowane, ale stan się nie aktualizuje | Niezgodność pola `details` | Zgłoś błąd z surowym payloadem zdarzenia |

### Zachowanie po rekonekcie WebSocket

Most implementuje automatyczne ponowne łączenie z 5-sekundowym opóźnieniem. Po rekonekcie koordynator wykonuje natychmiastowe pełne odświeżenie REST, aby uzgodnić zmiany stanu pominięte podczas przerwy.

---

## MQTT — most w czasie rzeczywistym (wariant awaryjny)

Użyj mostu MQTT tylko gdy WebSocket nie jest dostępny w firmware centrali. Wymagania:

- Działający broker MQTT (np. dodatek Mosquitto w HA)
- Skrypt `mqtt_bridge.lua` wgrany do centrali Sinum

**Priorytet:** integracja próbuje najpierw WebSocket. MQTT jest uruchamiany tylko gdy WebSocket jest wyłączony w opcjach.

### Architektura

```
Centrala Sinum
  └── mqtt_bridge.lua (automatyzacja, wgrana przez usługę sinum.upload_mqtt_bridge)
        Przy każdej zmianie stanu urządzenia:
        PUBLISH  {prefiks}/state/{magistrala}/{device_id}   ← pełny JSON urządzenia
        PUBLISH  {prefiks}/event/heartbeat                  ← co 60 s
        PUBLISH  {prefiks}/event/button_press               ← po naciśnięciu przycisku

Broker MQTT (np. dodatek Mosquitto w HA)
  │
  ▼
Integracja MQTT HA
  └── Sinapse mqtt.py
        SUBSCRIBE  {prefiks}/state/+
        Po wiadomości: aktualizacja cache koordynatora → natychmiastowe odświeżenie encji
```

### Krok 1 — Dodanie klienta MQTT w centrali

Otwórz interfejs webowy Sinum (użyj własnego IP/nazwy hosta centrali):

**Ustawienia → System → Integracje → Klient MQTT → Dodaj klienta MQTT**

![Dodaj klienta MQTT](images/setup/sinum-05-add-mqtt-client.png)

Skonfiguruj:
- **IP brokera**: adres IP hosta HA (gdzie działa Mosquitto)
- **Port**: `1883`
- **Dane uwierzytelniające**: zgodne z konfiguracją Mosquitto
- Zanotuj przydzielone **ID klienta** (np. `1`)

### Krok 2 — Wgranie skryptu Lua mostu

Użyj usługi HA `sinum.upload_mqtt_bridge` — bez ręcznej edycji. Usługa renderuje skrypt Lua i wysyła go bezpośrednio do sceny centrali przez PATCH.

Najpierw utwórz pustą scenę w Sinum (typ: Automatyzacja lub Scena) i zanotuj jej ID. Następnie:

```yaml
service: sinum.upload_mqtt_bridge
data:
  mqtt_scene_id: 1    # ID sceny do nadpisania skryptem mostu
  mqtt_client_id: 1   # ID klienta MQTT z Kroku 1
```

Parametry opcjonalne:

```yaml
service: sinum.upload_mqtt_bridge
data:
  entry_id: "01KV874N4F3B2W3ZPEXYFC3RVA"   # wymagane tylko przy wielu centralach Sinum
  mqtt_scene_id: 1
  mqtt_client_id: 1
  dry_run: true    # zapisz skrypt Lua do logu bez wgrywania (podgląd)
```

### Krok 3 — Włączenie MQTT w integracji

1. Przejdź do **Ustawienia → Urządzenia i usługi → Sinum (Sinapse) → Konfiguruj**.
2. Włącz **„Włącz transport MQTT w czasie rzeczywistym"**.
3. Ustaw **prefiks tematów MQTT** zgodnie ze skryptem Lua (domyślnie: `sinum`).
4. Kliknij **Zatwierdź**.

### Referencja tematów MQTT

| Temat | Kierunek | Zawartość |
|---|---|---|
| `{prefiks}/state/{magistrala}/{device_id}` | Centrala → HA | Pełny JSON stanu urządzenia |
| `{prefiks}/event/heartbeat` | Centrala → HA | Heartbeat (generowany co 60 s) |
| `{prefiks}/event/button_press` | Centrala → HA | Zdarzenie naciśnięcia przycisku |

Temat heartbeat może być używany w HA do wykrywania, czy skrypt Lua przestał działać.

### Rozwiązywanie problemów MQTT

| Objaw | Prawdopodobna przyczyna | Rozwiązanie |
|---|---|---|
| Encje nadal aktualizują się w 30 s | MQTT nie włączony w opcjach lub niezgodność prefiksu tematu | Sprawdź opcje; zweryfikuj `TOPIC_PREFIX` w Lua względem ustawień integracji |
| Brak heartbeat przez 2+ minuty | Automatyzacja Lua zatrzymana lub klient MQTT offline | Sprawdź listę automatyzacji Sinum; sprawdź status klienta MQTT w Sinum |
| `sinum_heartbeat` nigdy nie pojawia się w HA | Broker niedostępny z centrali | Zweryfikuj IP brokera i dane uwierzytelniające w konfiguracji klienta MQTT Sinum |
| Aktualizacje stanu docierają, ale dla złego urządzenia | Problem z routingiem tematów | Sprawdź wersję `mqtt_bridge.lua` — użyj `sinum.upload_mqtt_bridge` do ponownego wgrania |

### Wersja skryptu Lua

Dołączony skrypt Lua to `mqtt_bridge.lua` v0.8.1. Po każdej aktualizacji integracji wgraj świeżą kopię — format skryptu może się zmieniać między wersjami.

```bash
# Z katalogu głównego repozytorium
cat lua_scripts/mqtt_bridge.lua
```

Lub wywołaj `sinum.upload_mqtt_bridge` z `dry_run: true`, aby wyświetlić podgląd wyrenderowanego kodu Lua bez wgrywania.

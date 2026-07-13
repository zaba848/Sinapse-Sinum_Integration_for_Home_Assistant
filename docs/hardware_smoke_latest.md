# Hardware Smoke Test (Latest)

Generated: 2026-07-13 03:56:28Z

| Hub | Login | /info | /devices/wtp | /devices/sbus | /devices/virtual | /devices/lora | /devices/slink | /devices/modbus |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WTP | TOKEN | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| SBUS | TOKEN | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| VIDEO | TOKEN | ERR | ERR | ERR | ERR | ERR | ERR | ERR |
| KLIMAK | TOKEN | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| SBUS2 | TOKEN | ERR | ERR | ERR | ERR | ERR | ERR | ERR |
| LORA | TOKEN | 200 | 200 | 200 | 200 | 200 | 200 | 200 |

## LoRa Devices

### LORA
  EUI=70B3D59BA000A200 name='Temperature sensor 1'
  EUI=70B3D59BA000A200 name='Humidity sensor 1'

## Result

FAIL

## Diagnosis (2026-07-13)

| Hub | Status | Likely cause | Remediation |
|---|---|---|---|
| VIDEO (`<VIDEO_HUB_IP>`, alt `<VIDEO_HUB_INTERNAL_IP>`) | ERR — no TCP | Hub offline or wrong IP | Power/network check; update `SINUM_SMOKE_HUBS` if IP changed |
| SBUS2 (`<SBUS2_HUB_IP>`) | ERR — no TCP | Hub offline | Same as VIDEO |

**Note:** Smoke run from local workstation on LAN — WTP, SBUS, KLIMAK, LORA all 200. HA entries for VIDEO/SBUS2 confirmed `setup_retry` via live HA API query. Tokens are valid and configured; issue is hub reachability, not integration code. Unchanged since 2026-07-09.

**Runner:** GitHub Actions `sinum-lan` still unregistered. RPi Docker blocked by HA SSH add-on Protection Mode; backup runner host still offline.
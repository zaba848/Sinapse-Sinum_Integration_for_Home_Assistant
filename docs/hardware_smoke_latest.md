# Hardware Smoke Test (Latest)

Generated: 2026-07-07 12:30:48Z

> **2026-07-08 maintenance cycle:** Lab credentials (`SINUM_SMOKE_HUBS`, tokens) were not available in this environment. Re-run when on lab network:
> `SINUM_SMOKE_HUBS="..." python3 scripts/hardware_smoke_check.py`
> `python3 scripts/validate_api_writes.py` (KLIMAK + SBUS hubs)

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

FAIL — VIDEO and SBUS2 hubs unreachable; WTP, SBUS, KLIMAK and LORA passed all endpoints.

## HIL Summary

Generated: 2026-07-07 (post-HA-online)

| Hub | Smoke | HA config entry |
|---|---|---|
| WTP | PASS | `tablica-wtp` loaded |
| SBUS | PASS | `sinum-tablica-sbus-1` loaded |
| KLIMAK | PASS | `ehome-wojtek` loaded |
| LORA | PASS | `sinum-lora` loaded |
| VIDEO | NOT RUN | `tablica-video-nowa` setup_retry |
| SBUS2 | NOT RUN | `sinum-tablica-sbus2` setup_retry |

## Overall

Hardware validation **PASS for 4/6 hubs**. HA RPi online with v0.8.0 deployed (3937 entities). VIDEO and SBUS2 require lab-network reachability fix.
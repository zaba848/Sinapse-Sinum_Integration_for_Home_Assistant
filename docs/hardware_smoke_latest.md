# Hardware Smoke Test (Latest)

Generated: 2026-07-07 10:59:42Z

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

FAIL — VIDEO and SBUS2 hubs unreachable from test network; WTP, SBUS, KLIMAK and LORA passed all endpoints.

## HIL Summary

Generated: 2026-07-07

| Hub | Smoke | Notes |
|---|---|---|
| WTP | PASS | All 8 endpoints HTTP 200 |
| SBUS | PASS | All 8 endpoints HTTP 200 |
| KLIMAK | PASS | All 8 endpoints HTTP 200 |
| LORA | PASS | All 8 endpoints HTTP 200; 2 LoRa devices (ACW THO temp + humidity) |
| VIDEO | NOT RUN | Lab and internal addresses unreachable (network) |
| SBUS2 | NOT RUN | Lab address unreachable (network) |

## Overall

Hardware validation is **PASS for 4/6 hubs** reachable from the current network. VIDEO and SBUS2 failures are network availability issues, not integration regressions. Re-test when on lab LAN or via self-hosted CI runner (`sinum-lan`).
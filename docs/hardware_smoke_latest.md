# Hardware Smoke Test (Latest)

Generated: 2026-07-08 04:46:16Z

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

## Diagnosis (2026-07-08)

| Hub | Status | Likely cause | Remediation |
|---|---|---|---|
| VIDEO | ERR on all endpoints | Hub offline, IP changed, or expired `SINUM_VIDEO_TOKEN` | Verify reachability from `sinum-lan` runner; rotate token in GitHub Secrets |
| SBUS2 | ERR on all endpoints | Hub offline, IP changed, or expired `SINUM_SBUS2_TOKEN` | Same as VIDEO — check `vars.SINUM_SMOKE_HUBS` hub URL + per-hub token secret |

**Note:** WTP, SBUS, KLIMAK, LORA hubs respond 200 — integration code is not implicated.
Re-run: `gh workflow run hardware-nightly.yml` on self-hosted runner after fixing secrets.
# Handoff

> Updated: 2026-07-09 06:50

## Goal

Domknięcie wydania **Sinapse v0.8.1** — integracja Home Assistant dla hubów TECH Sinum. Release opublikowany; deploy v0.8.1 na RPi wykonany. Pozostały: runner `sinum-lan` dla hardware-nightly oraz fizyczna naprawa hubów VIDEO/SBUS2.

## Current State

- **v0.8.1**: tag + release + deploy na RPi (`<HA_RPI_IP>`, manifest 0.8.1)
- **HA integracja**: 4/6 `loaded` (SBUS-1, WTP, Klimak, LoRa); 2/6 `setup_retry` (VIDEO, SBUS2 — „Cannot reach Sinum hub”)
- **GitHub Secrets**: 6 tokenów + `SINUM_SMOKE_HUBS` — skonfigurowane
- **Smoke z RPi** (2026-07-09 04:45 UTC): 4/6 PASS; VIDEO/SBUS2 ERR — brak TCP z RPi (ping fail na `<VIDEO_HUB_IP>`, `<SBUS2_HUB_IP>`, `<VIDEO_HUB_INTERNAL_IP>`)
- **Runner `sinum-lan`**: **0 zarejestrowanych** — próba Docker na RPi zablokowana przez **HA SSH add-on Protection Mode**; `x1` (`<X1_RUNNER_IP>`) offline
- **Workflow hardware-nightly**: stare runy `28927298026`, `28919604233` **anulowane** (24h+ w kolejce bez runnera)

## Next Steps

- [ ] **Huby VIDEO + SBUS2**: włączyć / podłączyć do sieci — ping z RPi musi przejść
- [ ] **Runner** — wybierz jedną opcję:
  - **A)** Przywrócić `x1` (`<X1_RUNNER_IP>`) i zarejestrować runner natywnie
  - **B)** HA → Apps → Advanced SSH → **Protection Mode OFF** → restart → Docker runner na RPi:
    ```bash
    REG=$(gh api -X POST repos/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/actions/runners/registration-token --jq .token)
    docker run -d --restart unless-stopped --name sinum-lan-runner \
      -e REPO_URL='https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant' \
      -e RUNNER_TOKEN="$REG" -e RUNNER_NAME=sinum-lan \
      -e RUNNER_LABELS='self-hosted,sinum-lan' myoung34/github-runner:latest
    ```
- [ ] Po runnerze online: `gh workflow run hardware-nightly.yml`
- [ ] Opcjonalnie: commit zaktualizowanego `docs/hardware_smoke_latest.md`

## Decisions and Constraints

- Smoke FAIL VIDEO/SBUS2 **nie blokuje** v0.8.1 — potwierdzone z RPi LAN, nie problem kodu ani tokenów
- RPi (Alpine/musl) nie obsługuje natywnego GitHub runnera — wymaga Docker lub osobnej maszyny Linux/glibc
- Sekrety hubów tylko w GitHub Secrets / lokalne env — nigdy w repo

## Open Questions

- Czy huby VIDEO (`<VIDEO_HUB_IP>`) i SBUS2 (`<SBUS2_HUB_IP>`) są celowo wyłączone?
- Czy VIDEO ma nowy IP (internal `<VIDEO_HUB_INTERNAL_IP>` też niedostępny z RPi)?

## References

- Release: https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/releases/tag/v0.8.1
- `scripts/deploy_rpi.sh`, `scripts/hardware_smoke_check.py`
- `SECURITY_SETUP.md` — konfiguracja runnera

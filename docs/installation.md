# Installation Guide — Sinapse / Sinum Integration

**[← Back to README](../README.md)** · **[Polski](installation.pl.md)**

---

## Contents

- [Requirements](#requirements)
- [Install via HACS (recommended)](#install-via-hacs-recommended)
- [Manual Install](#manual-install)
- [Step 1 — Create an API Token on the Hub](#step-1--create-an-api-token-on-the-hub)
- [Step 2 — Add the Integration in Home Assistant](#step-2--add-the-integration-in-home-assistant)
- [Step 3 — Enable Real-Time Updates](#step-3--enable-real-time-updates)
- [Step 4 — Optional: MQTT Fallback](#step-4--optional-mqtt-fallback)
- [Troubleshooting Setup](#troubleshooting-setup)
- [Re-authentication](#re-authentication)
- [Rollback](#rollback)

---

## Requirements

| Requirement | Minimum |
|---|---|
| Home Assistant | 2024.1 |
| Python | 3.12 (bundled with HA) |
| Sinum hub firmware | Any (WebSocket requires hub support for `/api/v1/ws`) |
| Network | Hub reachable from HA on the local network |
| HACS | 1.x (optional, for HACS install method) |

> The integration communicates with the hub over plain HTTP on the local network. For security recommendations see [Security Best Practices](../README.md#security-best-practices).

---

## Install via HACS (recommended)

HACS is the Home Assistant Community Store. It manages installation and updates automatically.

1. Open HACS in the HA sidebar.
2. Click **Integrations** → top-right menu **⋮** → **Custom repositories**.
3. Add URL: `https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant`  
   Category: **Integration**
4. Search for **Sinum** or **Sinapse** and click **Download**.
5. Restart Home Assistant.

After restart, continue with [Step 1 — Create an API Token](#step-1--create-an-api-token-on-the-hub).

---

## Manual Install

Use this method if you don't have HACS or prefer direct control.

```bash
# From the repo root
cp -r custom_components/sinum /config/custom_components/
```

Or download the latest release ZIP from GitHub Releases, extract it, and copy the `sinum/` folder to `/config/custom_components/sinum/`.

Restart Home Assistant, then continue with [Step 1](#step-1--create-an-api-token-on-the-hub).

---

## Step 1 — Create an API Token on the Hub

The integration prefers a **static API token** over username + password. A token is scoped, doesn't expire, and can be revoked independently of your admin password.

Open the Sinum web UI on the same local network as Home Assistant. The address is the hub's IP or hostname — for example `http://sinum.local` or `http://10.0.62.167` (use your own hub address, not this example).

![Sinum local sign-in](images/setup/sinum-01-sign-in.png)

After signing in, navigate to **Settings → System → Integrations**.

![Sinum Settings → System → Integrations](images/setup/sinum-02-settings-system-integrations.png)

In the **External integration tokens** section:

1. Click **Add token**.
2. Enter a descriptive name — for example `Home Assistant`.
3. Select the token type.
4. Click **Save**.
5. **Copy the generated token immediately** — it is shown only once.

![Add external integration token](images/setup/sinum-04-add-token.png)

You can review or revoke tokens later under **Settings → System → Integrations → External integration tokens → Token list**.

![Token list](images/setup/sinum-03-token-list.png)

> **Security**: Never paste the token into GitHub issues, log files, screenshots, or chat messages. If the token is exposed, create a new one and revoke the old one in the Sinum web UI.

**Official Sinum resources from TECH Sterowniki:**
- REST API reference: <https://apidocs.sinum.tech/>
- Lua scripting manual: <https://www.techsterowniki.pl/!uploads/SINUM/LUA_user_manual.pdf>
- Knowledge base: <https://www.techsterowniki.pl/blog/kategoria/sinum>
- Sinum FAQ: <https://www.techsterowniki.pl/blog/system-sinum-najczesciej-zadawane-pytania>

---

## Step 2 — Add the Integration in Home Assistant

Go to: **Settings → Devices & Services → Add Integration → search "Sinum"**

The setup wizard has two screens.

### Screen 1 — Hub address and auth method

| Field | What to enter |
|---|---|
| **Host** | IP address or hostname of your hub — e.g. `10.0.62.167`. No `http://`. |
| **Auth method** | `api_token` (recommended) or `username_password` |

> If you don't know the hub IP, try `sinum.local`. If that doesn't resolve, check the DHCP lease list in your router.

### Screen 2 — Credentials

| Auth method | Field | Value |
|---|---|---|
| API Token | Token | Paste the token from Step 1 |
| Username / Password | Username | Your Sinum web UI username |
| Username / Password | Password | Your Sinum web UI password |

Click **Submit**. Home Assistant discovers all devices and creates entities automatically. This takes a few seconds on large installations.

---

## Step 3 — Enable Real-Time Updates

Without this step, entity states update every 30 seconds (REST polling). With WebSocket, updates arrive in under 1 second.

1. Go to **Settings → Devices & Services** → find **Sinum (Sinapse)** → click **Configure**.
2. Enable **"Enable WebSocket real-time transport"**.
3. Leave the path as `/api/v1/ws` (default).
4. Click **Submit**.

The bridge connects immediately — no restart needed.

**Verify it works:** open **Developer Tools → Events → Listen** and type `sinum_device_state_changed`. Trigger any state change on the hub (toggle a switch, open a door). The event should appear in under a second.

> If your hub firmware doesn't support WebSocket, fall back to the [MQTT bridge](../docs/real-time.md#mqtt-real-time-bridge-legacy).

---

## Step 4 — Optional: MQTT Fallback

Skip this step if WebSocket works. Use MQTT only when:
- Your hub firmware doesn't expose `/api/v1/ws`
- You see frequent WebSocket reconnects in logs

See the full MQTT setup guide: [Real-Time Transports → MQTT](real-time.md#mqtt-real-time-bridge-legacy).

---

## Troubleshooting Setup

### "Cannot connect to hub"

| Cause | Fix |
|---|---|
| Wrong IP or hostname | Verify the hub is reachable: `curl http://<hub-ip>/api/v1/info` |
| Hub on different VLAN | Ensure HA and hub are on the same network or routing is configured |
| Firewall blocking port 80 | Allow TCP 80 from HA to hub |

### "Invalid credentials" / "Unauthorized"

| Cause | Fix |
|---|---|
| Wrong token pasted | Regenerate and copy again from Sinum web UI |
| Username/password wrong | Try logging into the Sinum web UI with the same credentials |
| Token revoked | Create a new token in Sinum web UI |

### No entities created after setup

1. Check Home Assistant logs for `custom_components.sinum` errors.
2. Enable debug logging temporarily:
   ```yaml
   # configuration.yaml
   logger:
     logs:
       custom_components.sinum: debug
   ```
3. Reload the integration and check logs again.

### Entities show "unavailable"

The hub is temporarily unreachable. The integration serves cached state for up to the poll interval (default 30 s). Check hub connectivity and wait for the next poll.

---

## Re-authentication

If the hub token or password changes, HA shows a persistent notification. Click **Re-authenticate** and enter the new credentials. No restart needed.

The integration blocks re-authentication after 5 consecutive failures for 5 minutes to prevent brute-force attempts.

---

## Rollback

If an update causes a regression:

1. Download the previous release ZIP from [GitHub Releases](https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant/releases).
2. Replace `/config/custom_components/sinum/` with the older version.
3. Restart Home Assistant.
4. Verify entity availability and automations.
5. [Open an issue](https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant/issues) with logs and version pair.

Keep the previous two release ZIPs archived locally for production environments.

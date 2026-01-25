# Cloudflare Tunnel & Zero Trust Setup for SigmaTrader (Win11 + Linux)

This document captures the **end‑to‑end, battle‑tested steps** to expose **SigmaTrader** securely to the internet using **Cloudflare Tunnel**, covering **both Windows 11 and Linux (Ubuntu/Kubuntu)**.

It is written as a **repeatable reference** for future setup, recovery, or migration (Win11 → Linux), and reflects the exact issues, fixes, and best practices discovered during real setup.

---

## 1. Architecture Overview

### Goals
- Expose SigmaTrader **without opening inbound ports**
- Support:
  - Web UI (Frontend)
  - Backend API
  - TradingView webhooks (alerts)
- Work identically on **Win11 and Linux**
- Allow easy migration across machines

### High‑level design

```
Internet
   │
   ▼
Cloudflare (HTTPS, DNS, WAF, Access)
   │
   ▼
cloudflared (outbound tunnel)
   │
   ├── Frontend  (localhost:5173)
   ├── Backend   (localhost:8000)
   └── Webhooks  (localhost:8000/webhook/tradingview)
```

### Hostnames used

| Purpose | Hostname | Local Service |
|------|--------|---------------|
| UI | sigmatrader.co.in | http://localhost:5173 |
| API | api.sigmatrader.co.in | http://localhost:8000 |
| TradingView alerts | alerts.sigmatrader.co.in | http://localhost:8000 |

---

## 2. Prerequisites

### Common (Both OS)
- Cloudflare account
- Domain added to Cloudflare (DNS managed by Cloudflare)
- SigmaTrader running locally (FE + BE)

### Local ports assumed
- Frontend: `5173` (Vite / React)
- Backend: `8000` (FastAPI)

Adjust ports if your setup differs.

---

## 3. Installing cloudflared

### 3.1 Windows 11

1. Download cloudflared (Windows amd64)
2. Rename to:
   ```
   cloudflared.exe
   ```
3. Place it in:
   ```
   C:\cloudflared\cloudflared.exe
   ```
4. Add `C:\cloudflared` to **System PATH**
5. Restart terminal

Verify:
```powershell
cloudflared --version
```

---

### 3.2 Linux (Ubuntu / Kubuntu)

```bash
sudo apt update
sudo apt install cloudflared
```

Verify:
```bash
cloudflared --version
```

---

## 4. Authenticate with Cloudflare (per machine)

Run once on each machine:

```bash
cloudflared tunnel login
```

- Browser opens
- Select correct Cloudflare account
- This creates:
  ```
  ~/.cloudflared/cert.pem
  ```

> `cert.pem` is **account‑wide**, not tunnel‑specific.

---

## 5. Create / Verify Tunnel

List tunnels:
```bash
cloudflared tunnel list
```

If tunnel does not exist:
```bash
cloudflared tunnel create sigmatrader
```

This creates a **tunnel UUID**, e.g.
```
5b084b2f-c1f7-469b-953d-f258364dc18f
```

---

## 6. Recover tunnel credentials on a new machine (IMPORTANT)

### Problem
- Tunnel exists in Cloudflare
- New machine does not have `<UUID>.json`
- Error:
  ```
  tunnel credentials file not found
  ```

### Solution (works on Win11 + Linux)

Generate credentials from tunnel token:

#### Windows (PowerShell)
```powershell
$uuid = "<TUNNEL-UUID>"
$dst  = "$env:USERPROFILE\.cloudflared\$uuid.json"

cloudflared tunnel token --cred-file $dst $uuid
```

#### Linux
```bash
cloudflared tunnel token --cred-file ~/.cloudflared/<TUNNEL-UUID>.json <TUNNEL-UUID>
```

Verify file exists and is non‑empty.

> This step is **critical** when moving from Linux → Win11 or vice‑versa.

---

## 7. Tunnel Configuration (`config.yml`)

Location:
- Windows: `C:\Users\<user>\.cloudflared\config.yml`
- Linux: `~/.cloudflared/config.yml`

### Final working config

```yaml
tunnel: sigmatrader
credentials-file: /path/to/<TUNNEL-UUID>.json

ingress:
  # Frontend UI
  - hostname: sigmatrader.co.in
    service: http://localhost:5173

  # Backend API
  - hostname: api.sigmatrader.co.in
    service: http://localhost:8000

  # TradingView webhooks
  - hostname: alerts.sigmatrader.co.in
    service: http://localhost:8000

  - service: http_status:404
```

> Cloudflare Tunnel uses **strict hostname matching**.
> If a hostname is missing here, Cloudflare returns 404.

---

## 8. DNS Routing (one‑time per hostname)

Run once for each hostname:

```bash
cloudflared tunnel route dns sigmatrader sigmatrader.co.in
cloudflared tunnel route dns sigmatrader api.sigmatrader.co.in
cloudflared tunnel route dns sigmatrader alerts.sigmatrader.co.in
```

This creates CNAME records pointing to the tunnel.

---

## 9. Running the Tunnel

### Foreground (dev / debug)
```bash
cloudflared tunnel run sigmatrader
```

Verify:
```bash
cloudflared tunnel list
```
`CONNECTIONS` should show `1`.

---

### Windows Service (recommended)

```powershell
cloudflared service install
net start cloudflared
```

Benefits:
- Auto‑start on reboot
- Survives terminal close

---

## 10. TradingView Webhook Setup

### Webhook URL
```
https://alerts.sigmatrader.co.in/webhook/tradingview
```

### Requirements
- Method: POST
- Content‑Type: application/json
- Endpoint must return **2xx**

### Recommended security
- Include a shared secret in payload
- Validate secret server‑side

---

## 11. Cloudflare Zero Trust (Optional but Recommended)

### Team name
Choose once:
```
sigmatrader.cloudflareaccess.com
```

### Best practice
- Protect **UI** with Cloudflare Access (Google / Email OTP)
- DO NOT protect:
  - `/webhook/tradingview`

TradingView cannot pass Access auth.

---

## 12. Security Notes (Win11 vs Linux)

### Why this setup is safe
- No inbound ports opened
- Outbound‑only tunnel
- HTTPS terminated at Cloudflare
- Bitdefender / Linux firewall still active

### OS recommendation

| Use case | Recommended OS |
|------|----------------|
| Dev / testing | Win11 or Linux |
| Long‑running prod | Linux / VPS |

Migration requires **no Cloudflare changes**.

---

## 13. Common Failure Modes & Fixes

| Symptom | Cause | Fix |
|------|------|----|
| 404 at domain | Hostname missing in ingress | Add hostname to config.yml |
| Tunnel exists but won’t start | Missing `<UUID>.json` | Regenerate via `tunnel token` |
| TradingView alerts not received | alerts hostname missing | Add alerts.* ingress + DNS |
| JSON shown at root | Domain points to backend | Route UI hostname to FE |

---

## 14. Final Notes

- This setup is **portable, secure, and production‑grade**
- Same tunnel, same DNS works across machines
- Only credentials JSON is machine‑specific

This document should be kept as the **canonical Cloudflare reference** for SigmaTrader.

---

_Last verified on: Windows 11 + Ubuntu (Kubuntu)_


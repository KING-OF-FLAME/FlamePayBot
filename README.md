# FlamePayBot

Telegram payment bot + webhook service for BTCPayments/ggusonepay pay-in flow, internal ledger, and manual payout approvals.

## Architecture overview

## Bot capabilities

What this bot can do:
- Create payment orders & payment links
- Auto payment confirmation via callback (`/notify`)
- Order status check and admin reconcile flow
- Internal balance system inside Telegram
- Access-code / permission-based bot usage
- Fixed global fee (default 15%) across gateways

- **Telegram bot (aiogram)** handles user activation, recharge order creation, status checks, internal balances, payout requests, and admin actions.
- **Webhook service (FastAPI)** receives `/notify` callback, verifies signature, performs idempotency checks, updates order state (0-6), and credits balance on success state `2`.
- **MySQL (XAMPP)** stores users, access codes, gateway/packages, orders, ledger entries, payouts, audit logs, and callback events.
- **Provider client** calls `POST /api/pay/create`, `POST /api/pay/query`, `POST /api/pay/close` with signed JSON payloads.

## Quick start (Windows RDP + XAMPP)

1. Copy `.env.example` to `.env` and fill secrets (`BOT_TOKEN`, `PROVIDER_KEY`, `ADMIN_IDS`, `NOTIFY_URL`).
2. Open XAMPP and start **MySQL**.
3. Import database schema from project root:
   ```powershell
   mysql -u root -p < sql/schema.sql
   ```
4. Create and activate Python 3.12 venv (PowerShell):
   ```powershell
   py -0p
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install -r requirements.txt
   ```
5. Run bot process:
   ```powershell
   python -m app.bot_app
   ```
6. Run webhook process (second terminal):
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m app.webhook_app
   ```

## Quick start (Linux/macOS)

1. Copy `.env.example` → `.env` and fill secrets.
2. Create DB + tables:
   ```bash
   mysql -u root -p < sql/schema.sql
   ```
3. Install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Start bot: `python -m app.bot_app`
5. Start webhook API: `python -m app.webhook_app`

## Local development notifyUrl without domain (RDP + XAMPP)

Use HTTPS tunnel so provider can reach your local webhook.

### Option A: ngrok
```powershell
ngrok http 8000
```
Use the generated HTTPS URL in `.env` as:
```env
NOTIFY_URL=https://<ngrok-id>.ngrok-free.app/notify
```

### Option B: cloudflared
```powershell
cloudflared tunnel --url http://localhost:8000
```
Then set the provided `https://...trycloudflare.com/notify` URL.

> No own domain is required. Keep tunnel running continuously; otherwise callbacks will fail.

## Production checklist

- Put bot + webhook behind process manager.
- Use public HTTPS reverse proxy (Nginx/Apache) in front of FastAPI.
- Restrict DB user permissions.
- Rotate merchant key and bot token; keep only in `.env`.
- Add daily backups for MySQL.
- Monitor webhook 4xx/5xx and reconciliation tasks.

## Testing plan

- Create activation code with `/gencode` and test `/activate <code>`.
- Configure gateway and package with `/gateway` + `/package_add`.
- Create order via `/pay` and verify `cashierUrl` exists.
- Simulate callback to `/notify` with valid `sign`; verify:
  - order status updates
  - duplicate callback ignored by `callback_events`
  - state `2` credits available balance and ledger entry
- Run `/reconcile <mchOrderNo>` to query provider and compare status.
- Submit `/payoutrequest`, then admin `/payout_approve` and `/payout_reject` scenarios.

## Notes

- Amount for provider requests is always **integer cents**.
- Fee is globally configured by `GLOBAL_FEE_PERCENT` (default 15).
- Logging avoids printing secret keys/tokens.


## Troubleshooting: `getaddrinfo failed` on package click

If you see `httpx.ConnectError: [Errno 11001] getaddrinfo failed`, your bot cannot resolve/reach provider host.

Checklist:
- Ensure `.env` has a valid provider URL:
  - `PROVIDER_BASE_URL=https://www.ggusonepay.com`
- Ensure provider currency is 3-letter lowercase for create API:
  - `DEFAULT_CURRENCY=usd`
- Do not include spaces or invalid hostname in `PROVIDER_BASE_URL`.
- Confirm Windows/RDP machine DNS and firewall allow outbound HTTPS.
- Restart bot after `.env` changes.

The bot now catches this error and returns a user-friendly message instead of crashing.

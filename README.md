# FlamePayBot

Telegram payment bot + webhook service for BTCPayments/ggusonepay pay-in flow, internal ledger, and manual payout approvals.

## Architecture overview

- **Telegram bot (aiogram)** handles user activation, recharge order creation, status checks, internal balances, payout requests, and admin actions.
- **Webhook service (FastAPI)** receives `/notify` callback, verifies signature, performs idempotency checks, updates order state (0-6), and credits balance on success state `2`.
- **MySQL (XAMPP)** stores users, access codes, gateway/packages, orders, ledger entries, payouts, audit logs, and callback events.
- **Provider client** calls `POST /api/pay/create`, `POST /api/pay/query`, `POST /api/pay/close` with signed JSON payloads.

## Quick start

1. Copy `.env.example` → `.env` and fill secrets.
2. Create DB and import `sql/schema.sql`.
3. Install deps:
   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Start bot:
   ```bash
   python -m app.bot_app
   ```
5. Start webhook API:
   ```bash
   python -m app.webhook_app
   ```

## Local development notifyUrl without domain (RDP + XAMPP)

Use HTTPS tunnel so provider can reach your local webhook:

### Option A: ngrok
```bash
ngrok http 8000
```
Use the generated HTTPS URL in `.env` as:
```env
NOTIFY_URL=https://<ngrok-id>.ngrok-free.app/notify
```

### Option B: cloudflared
```bash
cloudflared tunnel --url http://localhost:8000
```
Then set the provided `https://...trycloudflare.com/notify` URL.

> No own domain is required. Keep tunnel running continuously.

## Production checklist

- Put bot + webhook behind process manager (systemd/supervisor/pm2 equivalent).
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

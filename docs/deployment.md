# Deployment Guide (RDP / XAMPP / no domain)

## Local on RDP without domain

### 1) Python setup on Windows (PowerShell)
```powershell
py -0p
cd C:\xampp\htdocs\2\FlamePayBot-main\FlamePayBot-main
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### 2) Initialize database in XAMPP
- Open phpMyAdmin and import `sql/schema.sql`, **or** run:

```powershell
mysql -u root -p < sql/schema.sql
```

This creates database `flamepaybot` and all required tables.

### 3) Run services
Terminal A:
```powershell
.\.venv\Scripts\Activate.ps1
python -m app.bot_app
```

Terminal B:
```powershell
.\.venv\Scripts\Activate.ps1
python -m app.webhook_app
```

### 4) Expose webhook publicly (required)
Use one tunnel command:

```powershell
ngrok http 8000
```
or
```powershell
cloudflared tunnel --url http://localhost:8000
```

Set `.env`:
```env
NOTIFY_URL=https://<public-https-host>/notify
```

## Optional Apache reverse proxy with XAMPP
Enable modules: `proxy`, `proxy_http`, `ssl` and add vhost mapping:

```apache
ProxyPass "/notify" "http://127.0.0.1:8000/notify"
ProxyPassReverse "/notify" "http://127.0.0.1:8000/notify"
```

You still need public HTTPS, so keep tunnel or use cloud VM static IP + cert.

## Production
- Use Linux VM with fixed DNS/domain + TLS cert.
- Run webhook under Uvicorn/Gunicorn, behind Nginx.
- Run bot as separate service.
- Rotate env secrets and enforce firewall.

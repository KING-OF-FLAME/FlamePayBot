# Deployment Guide (RDP / XAMPP / no domain)

## Local on RDP without domain
1. Run MySQL from XAMPP.
2. Run bot + webhook python processes.
3. Start HTTPS tunnel (ngrok/cloudflared) for port `8000`.
4. Set `NOTIFY_URL` in `.env` to `<public_https>/notify`.
5. Restart python services.

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
- Run bot as separate systemd service.
- Rotate env secrets and enforce firewall.

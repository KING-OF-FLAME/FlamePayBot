# Project Structure

This branch is a clean structure branch intended to be merged to main.

```text
FlamePayBot/
├── .env.example
├── README.md
├── PROJECT_STRUCTURE.md
├── requirements.txt
├── docs/
│   └── deployment.md
├── sql/
│   └── schema.sql
└── app/
    ├── __init__.py
    ├── bot_app.py
    ├── webhook_app.py
    ├── init_db.py
    ├── api/
    │   ├── __init__.py
    │   └── webhook.py
    ├── bot/
    │   ├── __init__.py
    │   ├── handlers/
    │   │   ├── __init__.py
    │   │   ├── admin.py
    │   │   └── user.py
    │   └── keyboards/
    │       └── common.py
    ├── core/
    │   ├── __init__.py
    │   ├── config.py
    │   └── logging.py
    ├── db/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── models.py
    │   └── session.py
    └── services/
        ├── __init__.py
        ├── provider_client.py
        ├── repositories.py
        └── signing.py
```

import uvicorn

from app.api.webhook import app
from app.core.config import get_settings
from app.core.logging import configure_logging


if __name__ == '__main__':
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(app, host=settings.webhook_host, port=settings.webhook_port)

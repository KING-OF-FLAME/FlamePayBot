from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'development'
    log_level: str = 'INFO'

    bot_token: str = Field(alias='BOT_TOKEN')
    bot_username: str = Field(alias='BOT_USERNAME')
    admin_ids: List[int] = Field(default_factory=list, alias='ADMIN_IDS')

    mysql_host: str = Field(alias='MYSQL_HOST')
    mysql_port: int = Field(alias='MYSQL_PORT')
    mysql_user: str = Field(alias='MYSQL_USER')
    mysql_password: str = Field(alias='MYSQL_PASSWORD')
    mysql_db: str = Field(alias='MYSQL_DB')

    provider_base_url: str = Field(alias='PROVIDER_BASE_URL')
    provider_mch_no: str = Field(alias='PROVIDER_MCH_NO')
    provider_username: str = Field(alias='PROVIDER_USERNAME')
    provider_key: str = Field(alias='PROVIDER_KEY')
    provider_sign_type: str = Field(alias='PROVIDER_SIGN_TYPE')
    provider_timeout_seconds: int = Field(default=15, alias='PROVIDER_TIMEOUT_SECONDS')
    provider_retry_alt_sign: bool = Field(default=False, alias='PROVIDER_RETRY_ALT_SIGN')

    global_fee_percent: float = Field(default=15.0, alias='GLOBAL_FEE_PERCENT')
    default_currency: str = Field(default='USD', alias='DEFAULT_CURRENCY')
    notify_url: str = Field(alias='NOTIFY_URL')
    return_url: str = Field(alias='RETURN_URL')

    bot_polling_timeout: int = Field(default=20, alias='BOT_POLLING_TIMEOUT')
    webhook_host: str = Field(default='0.0.0.0', alias='WEBHOOK_HOST')
    webhook_port: int = Field(default=8000, alias='WEBHOOK_PORT')

    @field_validator('provider_base_url', mode='before')
    @classmethod
    def normalize_provider_base_url(cls, value: str) -> str:
        v = (value or '').strip()
        if not v:
            raise ValueError('PROVIDER_BASE_URL is required')
        if not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v.rstrip('/')

    @field_validator('admin_ids', mode='before')
    @classmethod
    def parse_admin_ids(cls, value: str | int | List[int]) -> List[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        if not value:
            return []
        return [int(x.strip()) for x in str(value).split(',') if x.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        password = self.mysql_password
        return f'mysql+pymysql://{self.mysql_user}:{password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4'


@lru_cache
def get_settings() -> Settings:
    return Settings()

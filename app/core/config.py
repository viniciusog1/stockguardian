"""Configuração tipada da aplicação via pydantic-settings.

Todas as variáveis de ambiente são carregadas e validadas aqui. Nenhum outro
módulo deve ler `os.environ` diretamente — sempre importar `settings`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Aplicação ----
    PROJECT_NAME: str = "StockGuardian"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # ---- PostgreSQL ----
    POSTGRES_USER: str = "stockguardian"
    POSTGRES_PASSWORD: str = "stockguardian"
    POSTGRES_DB: str = "stockguardian"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # ---- Redis ----
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ---- Segurança / JWT ----
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # ---- Seed ----
    FIRST_SUPERUSER_EMAIL: str = "admin@stockguardian.com"
    FIRST_SUPERUSER_PASSWORD: str = "Admin@123"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """DSN async (asyncpg) usada pelo engine da aplicação."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """DSN síncrona (psycopg) — usada apenas por ferramentas offline do Alembic."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Singleton de Settings (cacheado) — facilita override em testes."""
    return Settings()


settings = get_settings()

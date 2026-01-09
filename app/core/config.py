"""Конфигурация приложения через переменные окружения."""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки приложения.
    
    Загружаются из переменных окружения или файла .env
    """
    
    # Приложение
    APP_NAME: str = "MGP AI Assistant"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # API сервер
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Tourvisor API
    TOURVISOR_API_KEY: str = ""
    TOURVISOR_BASE_URL: str = "http://tourvisor.ru/xml"
    TOURVISOR_TIMEOUT: int = 30  # Таймаут запросов в секундах
    TOURVISOR_MOCK: bool = True  # Mock-режим для тестирования без API
    
    # YandexGPT API
    YANDEX_FOLDER_ID: str = ""
    YANDEX_API_KEY: str = ""
    YANDEX_MODEL: str = "yandexgpt-lite"
    YANDEX_GPT_ENABLED: bool = False  # Включить YandexGPT (иначе mock)
    
    # Настройки поиска
    DEFAULT_NIGHTS_MIN: int = 7
    DEFAULT_NIGHTS_MAX: int = 14
    MAX_TOUR_OFFERS: int = 5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Получение настроек приложения с кэшированием."""
    return Settings()


settings = get_settings()

"""
ИИ-ассистент МГП — Точка входа FastAPI приложения.

Запуск:
    uvicorn app.main:app --reload

Или:
    python -m app.main
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.endpoints.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle события приложения.
    
    Startup: инициализация сервисов
    Shutdown: освобождение ресурсов
    """
    # Startup
    print(f"🚀 Запуск {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"📍 Сервер: http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Документация: http://{settings.HOST}:{settings.PORT}/docs")
    
    yield
    
    # Shutdown
    print("👋 Остановка сервера...")


# Создание FastAPI приложения
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## ИИ-ассистент туристического агентства МГП

### Возможности:
- 🔍 **Поиск туров** через интеграцию с Tourvisor API
- 🤖 **Интеллектуальный диалог** на базе YandexGPT
- ❓ **FAQ** по визам, оплате, возвратам
- 📝 **Создание заявок** на бронирование

### Бизнес-логика:
- Поддержка групп от 1 до 6 взрослых
- Дети: младенцы (0-2 года) и дети (2-15 лет)
- Автоматический расчёт ночей из дат
- Иерархия: Страна → Регион → Курорт → Город → Отель
- Выдача 3-5 карточек предложений
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Middleware для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["root"])
async def root():
    """Корневой эндпоинт с информацией о сервисе."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "ИИ-ассистент туристического агентства МГП",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    Проверка состояния сервиса.
    
    Используется для мониторинга и балансировщиков нагрузки.
    """
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


# Подключение API роутеров
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

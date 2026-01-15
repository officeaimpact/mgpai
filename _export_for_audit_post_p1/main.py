"""
ИИ-ассистент МГП — Точка входа FastAPI приложения.

Запуск:
    uvicorn main:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from api.chat import router as chat_router
from api.requests import router as requests_router


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
    ИИ-ассистент туристического агентства МГП.
    
    Функционал:
    - Подбор туров через интеграцию с Tourvisor API
    - Интеллектуальный диалог на базе YandexGPT
    - FAQ по визам, оплате, возвратам
    - Создание заявок на бронирование
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

# Подключение роутеров
app.include_router(chat_router, prefix="/api")
app.include_router(requests_router, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    """Корневой эндпоинт с информацией о сервисе."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

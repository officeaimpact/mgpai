"""
ИИ-ассистент МГП — Точка входа FastAPI приложения.

Запуск:
    uvicorn app.main:app --reload

Или:
    python -m app.main

Функции:
- Авто-синхронизация справочников Tourvisor (каждые 24 часа)
- REST API для чата с ИИ-ассистентом
"""

from contextlib import asynccontextmanager
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.api.v1.endpoints.chat import router as chat_router

# Настройка логгера
logger = logging.getLogger(__name__)

# Глобальный экземпляр планировщика
scheduler: Optional[AsyncIOScheduler] = None


async def sync_tourvisor_job():
    """
    Фоновая задача синхронизации справочников Tourvisor.
    Запускается каждые 24 часа.
    """
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from scripts.sync_tourvisor_data import sync_dictionaries
        
        logger.info("🔄 [SCHEDULER] Запуск авто-синхронизации справочников...")
        countries, departures = await sync_dictionaries(verbose=False)
        logger.info(f"🔄 [SCHEDULER] Синхронизировано: {countries} стран, {departures} городов")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Ошибка синхронизации: {e}")


async def initial_sync():
    """
    Начальная синхронизация при старте приложения.
    Выполняется если файл констант отсутствует или устарел.
    """
    from pathlib import Path
    from datetime import datetime, timedelta
    
    constants_file = Path(__file__).parent / "core" / "tourvisor_constants.py"
    
    should_sync = False
    
    if not constants_file.exists():
        logger.info("📋 Файл констант не найден — требуется синхронизация")
        should_sync = True
    else:
        # Проверяем возраст файла (синхронизируем если старше 24 часов)
        try:
            from app.core.tourvisor_constants import LAST_SYNC
            last_sync = datetime.fromisoformat(LAST_SYNC)
            age = datetime.now() - last_sync
            if age > timedelta(hours=24):
                logger.info(f"📋 Константы устарели ({age.total_seconds() / 3600:.1f}ч) — требуется синхронизация")
                should_sync = True
            else:
                logger.info(f"📋 Константы актуальны (возраст: {age.total_seconds() / 3600:.1f}ч)")
        except Exception:
            should_sync = True
    
    if should_sync:
        await sync_tourvisor_job()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle события приложения.
    
    Startup:
    - Инициализация планировщика задач
    - Начальная синхронизация справочников (если нужно)
    - Запуск периодической синхронизации каждые 24 часа
    
    Shutdown:
    - Остановка планировщика
    - Освобождение ресурсов
    """
    global scheduler
    
    # === STARTUP ===
    print(f"🚀 Запуск {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"📍 Сервер: http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Документация: http://{settings.HOST}:{settings.PORT}/docs")
    
    # Инициализируем планировщик
    scheduler = AsyncIOScheduler()
    
    # Добавляем задачу синхронизации справочников (каждые 24 часа)
    scheduler.add_job(
        sync_tourvisor_job,
        trigger=IntervalTrigger(hours=24),
        id="tourvisor_sync",
        name="Синхронизация справочников Tourvisor",
        replace_existing=True,
        max_instances=1,
    )
    
    # Запускаем планировщик
    scheduler.start()
    logger.info("📅 [SCHEDULER] Планировщик запущен (синхронизация каждые 24ч)")
    
    # Начальная синхронизация (если нужно)
    await initial_sync()
    
    yield
    
    # === SHUTDOWN ===
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("📅 [SCHEDULER] Планировщик остановлен")
    
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

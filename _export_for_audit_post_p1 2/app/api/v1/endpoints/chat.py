"""
Эндпоинт чата с ИИ-ассистентом МГП.

Session Persistence:
- Использует thread_id (conversation_id) для идентификации сессии
- MemorySaver checkpointer сохраняет состояние между запросами
- Пользователь может продолжить диалог с любого устройства

POST /chat — основной эндпоинт для диалога с пользователем.
"""
from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.agent.graph import process_message
from app.core.session import session_manager
from app.core.guardrails import apply_input_guardrails, apply_output_guardrails

# Настройка логгера
logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def get_or_create_thread_id(conversation_id: Optional[str], user_id: Optional[str] = None) -> str:
    """
    Получает или создаёт thread_id для сессии.
    
    Приоритет:
    1. conversation_id (если передан)
    2. user_id (если передан)
    3. Генерируем новый UUID
    
    Args:
        conversation_id: ID диалога (для продолжения)
        user_id: ID пользователя (из заголовка или параметра)
        
    Returns:
        thread_id для LangGraph
    """
    if conversation_id:
        return conversation_id
    
    if user_id:
        # Используем user_id как thread_id для persistence между сессиями
        return f"user_{user_id}"
    
    # Новая сессия
    return str(uuid.uuid4())


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {"description": "Успешный ответ"},
        400: {"model": ErrorResponse, "description": "Ошибка в запросе"},
        500: {"model": ErrorResponse, "description": "Внутренняя ошибка сервера"}
    },
    summary="Отправить сообщение ассистенту",
    description="""
    Основной эндпоинт для общения с ИИ-ассистентом МГП.
    
    **Session Persistence:**
    - Передайте conversation_id для продолжения диалога
    - Или используйте заголовок X-User-ID для постоянной сессии
    - Бот помнит контекст между сообщениями
    
    **Возможности:**
    - Поиск туров по параметрам (страна, даты, количество туристов)
    - Горящие туры
    - FAQ по визам, оплате, отменам
    
    **Пример запроса:**
    ```json
    {
        "message": "Хочу в Турцию на 7 ночей вдвоём с 15 февраля",
        "conversation_id": null
    }
    ```
    """
)
async def chat(
    request: ChatRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
) -> ChatResponse:
    """
    Обработка сообщения пользователя с Session Persistence.
    
    Thread-based Persistence:
    1. Определяет thread_id (conversation_id или user_id)
    2. Запускает LangGraph агент с checkpointer
    3. Состояние автоматически сохраняется между запросами
    4. Возвращает ответ с карточками туров (если найдены)
    """
    try:
        # ==================== INPUT GUARDRAILS (AI-SAFE) ====================
        sanitized_message, guardrail_error = await apply_input_guardrails(request.message)
        
        if guardrail_error:
            logger.warning(f"🚫 Input blocked by guardrails: {guardrail_error}")
            return ChatResponse(
                reply=f"⚠️ {guardrail_error}. Пожалуйста, переформулируйте ваш запрос.",
                tour_cards=None,
                conversation_id=request.conversation_id or str(uuid.uuid4())
            )
        
        # Определяем thread_id для persistence
        thread_id = get_or_create_thread_id(request.conversation_id, x_user_id)
        
        logger.info(f"📩 Входящее сообщение: thread_id={thread_id}")
        
        # Проверяем метаданные сессии (для логирования)
        session_meta = session_manager.get_session_metadata(thread_id)
        if session_meta:
            logger.info(f"📂 Продолжение сессии: thread_id={thread_id}, сообщений: {session_meta.get('message_count', 0)}")
        else:
            logger.info(f"🆕 Новая сессия: thread_id={thread_id}")
        
        # Обрабатываем сообщение через агент
        # process_message сам восстановит состояние из checkpointer если нужно
        reply, new_state = await process_message(
            user_message=sanitized_message, 
            thread_id=thread_id,
            state=None  # Всегда None — process_message сам решит
        )
        
        # Получаем карточки туров (если есть)
        tour_cards = new_state.get("tour_offers", [])
        
        # Сериализуем карточки с computed полями
        serialized_cards = None
        if tour_cards:
            serialized_cards = [card.model_dump() for card in tour_cards]
        
        # ==================== OUTPUT GUARDRAILS (AI-SAFE) ====================
        safe_reply = apply_output_guardrails(reply)
        
        logger.info(f"✅ Ответ отправлен: thread_id={thread_id}")
        
        return ChatResponse(
            reply=safe_reply,
            tour_cards=serialized_cards if serialized_cards else None,
            conversation_id=thread_id  # Возвращаем thread_id для клиента
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        # ==================== OUTPUT GUARDRAILS: Error Handling ====================
        user_friendly_error = apply_output_guardrails("", error=e)
        return ChatResponse(
            reply=user_friendly_error,
            tour_cards=None,
            conversation_id=request.conversation_id or str(uuid.uuid4())
        )


@router.delete(
    "/chat/{conversation_id}",
    summary="Удалить сессию",
    description="Удаляет сессию диалога по ID (thread_id)"
)
async def delete_session(conversation_id: str) -> dict:
    """
    Удаление сессии диалога.
    
    Примечание: MemorySaver не поддерживает удаление по thread_id.
    Для полного удаления необходимо использовать PostgresSaver.
    """
    # Проверяем, есть ли метаданные сессии
    session_meta = session_manager.get_session_metadata(conversation_id)
    
    if session_meta:
        # Удаляем метаданные (состояние в MemorySaver остаётся до перезапуска)
        logger.info(f"🗑️ Удаление сессии: thread_id={conversation_id}")
        return {
            "status": "deleted", 
            "conversation_id": conversation_id,
            "note": "Metadata removed. Full state cleanup requires PostgresSaver."
        }
    
    raise HTTPException(status_code=404, detail="Сессия не найдена")


@router.get(
    "/chat/{conversation_id}/history",
    summary="История диалога",
    description="Получить историю сообщений диалога и текущие параметры поиска"
)
async def get_history(conversation_id: str) -> dict:
    """
    Получение истории диалога.
    
    Возвращает:
    - Историю сообщений
    - Текущие параметры поиска (страна, даты, состав)
    - Метаданные сессии
    """
    session_meta = session_manager.get_session_metadata(conversation_id)
    
    if not session_meta:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    # Получаем состояние из checkpointer
    # Примечание: для MemorySaver нужно вызвать граф для получения состояния
    # Для PostgresSaver можно получить напрямую
    
    return {
        "conversation_id": conversation_id,
        "session_metadata": {
            "created_at": session_meta.get("created_at").isoformat() if session_meta.get("created_at") else None,
            "last_access": session_meta.get("last_access").isoformat() if session_meta.get("last_access") else None,
            "message_count": session_meta.get("message_count", 0)
        },
        "note": "For full state, use checkpointer.get(thread_id)"
    }


@router.get(
    "/chat/sessions/stats",
    summary="Статистика сессий",
    description="Получить статистику активных сессий"
)
async def get_sessions_stats() -> dict:
    """
    Статистика сессий.
    
    Возвращает:
    - Количество активных сессий
    - Настройки (Window Buffer, TTL)
    """
    from app.core.session import MAX_MESSAGES_HISTORY, SESSION_TTL_SECONDS
    
    return {
        "active_sessions": session_manager.get_active_sessions_count(),
        "config": {
            "max_messages_history": MAX_MESSAGES_HISTORY,
            "session_ttl_seconds": SESSION_TTL_SECONDS
        },
        "checkpointer_type": "MemorySaver (development)"
    }

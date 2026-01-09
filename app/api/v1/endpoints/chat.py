"""
Эндпоинт чата с ИИ-ассистентом МГП.

POST /chat — основной эндпоинт для диалога с пользователем.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.agent.state import AgentState, create_initial_state
from app.agent.graph import process_message


router = APIRouter(tags=["chat"])

# In-memory хранилище сессий (позже заменим на PostgreSQL/Redis)
sessions: dict[str, AgentState] = {}


def get_or_create_session(conversation_id: Optional[str]) -> tuple[str, AgentState]:
    """
    Получает существующую сессию или создаёт новую.
    
    Args:
        conversation_id: ID диалога (None для нового)
        
    Returns:
        Кортеж (conversation_id, state)
    """
    if conversation_id and conversation_id in sessions:
        return conversation_id, sessions[conversation_id]
    
    # Создаём новую сессию
    new_id = str(uuid.uuid4())
    new_state = create_initial_state()
    sessions[new_id] = new_state
    
    return new_id, new_state


def save_session(conversation_id: str, state: AgentState) -> None:
    """
    Сохраняет состояние сессии.
    
    Args:
        conversation_id: ID диалога
        state: Новое состояние
    """
    sessions[conversation_id] = state


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
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Обработка сообщения пользователя.
    
    1. Получает/создаёт сессию по conversation_id
    2. Запускает LangGraph агент
    3. Возвращает ответ с карточками туров (если найдены)
    """
    try:
        # Получаем или создаём сессию
        conversation_id, state = get_or_create_session(request.conversation_id)
        
        # Обрабатываем сообщение через агент
        reply, new_state = await process_message(request.message, state)
        
        # Сохраняем обновлённое состояние
        save_session(conversation_id, new_state)
        
        # Получаем карточки туров (если есть)
        tour_cards = new_state.get("tour_offers", [])
        
        return ChatResponse(
            reply=reply,
            tour_cards=tour_cards if tour_cards else None,
            conversation_id=conversation_id
        )
        
    except Exception as e:
        # Логируем ошибку (TODO: добавить логгер)
        print(f"Chat error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки сообщения: {str(e)}"
        )


@router.delete(
    "/chat/{conversation_id}",
    summary="Удалить сессию",
    description="Удаляет сессию диалога по ID"
)
async def delete_session(conversation_id: str) -> dict:
    """Удаление сессии диалога."""
    if conversation_id in sessions:
        del sessions[conversation_id]
        return {"status": "deleted", "conversation_id": conversation_id}
    
    raise HTTPException(status_code=404, detail="Сессия не найдена")


@router.get(
    "/chat/{conversation_id}/history",
    summary="История диалога",
    description="Получить историю сообщений диалога"
)
async def get_history(conversation_id: str) -> dict:
    """Получение истории диалога."""
    if conversation_id not in sessions:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    state = sessions[conversation_id]
    return {
        "conversation_id": conversation_id,
        "messages": state.get("messages", []),
        "search_params": state.get("search_params", {})
    }

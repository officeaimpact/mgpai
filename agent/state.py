"""Состояние диалога для LangGraph."""

from typing import TypedDict, Optional, Annotated
from operator import add
from models.schemas import TourSearchRequest, TourFilters, TourOffer, ChatMessage


class DialogState(TypedDict):
    """
    Состояние диалога с пользователем.
    
    Хранит контекст разговора, собранные параметры поиска и результаты.
    """
    # История сообщений
    messages: Annotated[list[ChatMessage], add]
    
    # Собранные параметры поиска тура
    search_params: Optional[TourSearchRequest]
    
    # Применённые фильтры
    filters: Optional[TourFilters]
    
    # Найденные предложения
    tour_offers: Optional[list[TourOffer]]
    
    # Текущий этап диалога
    current_step: str
    
    # Намерение пользователя (поиск тура, FAQ, горящие туры и т.д.)
    intent: Optional[str]
    
    # Недостающие параметры, которые нужно уточнить
    missing_params: list[str]
    
    # ID сессии
    session_id: str

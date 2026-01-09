"""
Состояние агента LangGraph для ИИ-ассистента МГП.

Хранит контекст диалога, накопленные параметры поиска,
недостающую информацию и результаты.
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict, Optional, Any
from app.models.domain import TourOffer, FoodType, Destination


class PartialSearchParams(TypedDict, total=False):
    """
    Частично заполненные параметры поиска.
    
    Используется для накопления информации из диалога,
    пока не будут собраны все обязательные поля.
    """
    # Туристы
    adults: int
    children: list[int]
    
    # Направление
    destination_country: str
    destination_region: str
    destination_resort: str
    destination_city: str
    
    # Отель
    hotel_name: str
    stars: int
    
    # Даты
    date_from: date
    date_to: date
    nights: int
    
    # Питание
    food_type: FoodType
    
    # Город вылета
    departure_city: str


class Message(TypedDict):
    """Сообщение в истории диалога."""
    role: str  # "user" или "assistant"
    content: str


class AgentState(TypedDict):
    """
    Состояние агента для LangGraph.
    
    Атрибуты:
        messages: История сообщений диалога
        search_params: Накопленные параметры поиска тура
        missing_info: Список недостающих обязательных параметров
        tour_offers: Найденные предложения туров
        response: Сгенерированный ответ пользователю
        intent: Распознанное намерение (search_tour, hot_tours, faq, booking)
        error: Сообщение об ошибке, если есть
        customer_name: Имя клиента для заявки
        customer_phone: Телефон клиента для заявки
        awaiting_phone: Флаг ожидания телефона от пользователя
        selected_tour_id: ID выбранного тура для бронирования
    """
    messages: list[Message]
    search_params: PartialSearchParams
    missing_info: list[str]
    tour_offers: list[TourOffer]
    response: str
    intent: Optional[str]
    error: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    awaiting_phone: bool
    selected_tour_id: Optional[str]


# Обязательные параметры для поиска тура
REQUIRED_PARAMS = [
    "destination_country",  # Куда
    "date_from",           # Когда
    "adults",              # Сколько человек
]

# Названия параметров на русском для формирования вопросов
PARAM_NAMES_RU = {
    "destination_country": "страна назначения",
    "destination_region": "регион",
    "destination_resort": "курорт",
    "date_from": "дата начала поездки",
    "date_to": "дата окончания поездки",
    "nights": "количество ночей",
    "adults": "количество взрослых",
    "children": "дети",
    "hotel_name": "отель",
    "stars": "звёздность отеля",
    "food_type": "тип питания",
    "departure_city": "город вылета",
}

# Вопросы для уточнения параметров
CLARIFICATION_QUESTIONS = {
    "destination_country": "Куда бы вы хотели поехать?",
    "date_from": "На какие даты планируете поездку?",
    "adults": "Сколько взрослых поедет?",
    "children": "Будут ли с вами дети? Укажите их возрасты.",
    "nights": "На сколько ночей планируете поездку?",
    "food_type": "Какой тип питания предпочитаете? (всё включено, завтраки и т.д.)",
    "stars": "Отели какой категории рассматриваете? (3-5 звёзд)",
    "departure_city": "Из какого города планируете вылет?",
}


def get_missing_required_params(params: PartialSearchParams) -> list[str]:
    """
    Определяет недостающие обязательные параметры.
    
    Args:
        params: Текущие накопленные параметры
        
    Returns:
        Список ключей недостающих параметров
    """
    missing = []
    
    for param in REQUIRED_PARAMS:
        if param not in params or params.get(param) is None:
            missing.append(param)
    
    # Специальная логика: если указан hotel_name, не требуем stars
    if "hotel_name" in params and params.get("hotel_name"):
        if "stars" in missing:
            missing.remove("stars")
    
    # Если указаны date_from и date_to, nights не нужен
    if "date_from" in params and "date_to" in params:
        if "nights" in missing:
            missing.remove("nights")
    
    return missing


def create_initial_state() -> AgentState:
    """
    Создаёт начальное состояние агента.
    
    Returns:
        Пустое состояние для нового диалога
    """
    return AgentState(
        messages=[],
        search_params={},
        missing_info=[],
        tour_offers=[],
        response="",
        intent=None,
        error=None,
        customer_name=None,
        customer_phone=None,
        awaiting_phone=False,
        selected_tour_id=None
    )

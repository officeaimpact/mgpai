"""
Состояние агента LangGraph для ИИ-ассистента МГП.

Каскад вопросов (СТРОГИЙ ПОРЯДОК):
1. Куда? (страна)
2. Откуда? (город вылета) - ОБЯЗАТЕЛЬНО!
3. Когда? (даты)
4. Кто едет? (состав)
5. Детали (звёзды, питание)
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict, Optional
from app.models.domain import TourOffer, FoodType


class PartialSearchParams(TypedDict, total=False):
    """Частично заполненные параметры поиска."""
    # Туристы
    adults: int
    children: list[int]
    
    # Направление
    destination_country: str
    destination_region: str
    destination_resort: str
    destination_city: str
    
    # Даты
    date_from: date
    date_to: date
    nights: int
    
    # Город вылета - ОБЯЗАТЕЛЬНЫЙ ПАРАМЕТР!
    departure_city: str
    
    # Отель
    hotel_name: str
    stars: int
    
    # Питание
    food_type: FoodType
    
    # Флаги
    skip_quality_check: bool


class Message(TypedDict):
    """Сообщение в истории диалога."""
    role: str
    content: str


class AgentState(TypedDict):
    """Состояние агента для LangGraph."""
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
    cascade_stage: int
    quality_check_asked: bool
    is_first_message: bool
    # Флаг: было ли приветствие
    greeted: bool
    # Групповая заявка (>6 человек)
    is_group_request: bool
    group_size: int
    # Невалидная страна
    invalid_country: Optional[str]
    # Флаг гибкого поиска (±5 дней после согласия)
    flex_search: bool
    # Количество дней расширения поиска (по умолчанию 2, после согласия 5)
    flex_days: int
    # Флаг: бот предложил действие, ждём согласия
    awaiting_agreement: bool
    # Тип предложенного действия
    pending_action: Optional[str]  # "flex_dates", "any_hotel", etc.
    # Счётчик попыток поиска (для предотвращения зацикливания)
    search_attempts: int
    # Флаг: уже предлагали другой город вылета
    offered_alt_departure: bool
    # КРИТИЧНО: количество детей, для которых нужен возраст
    missing_child_ages: int


# ==================== КАСКАД ВОПРОСОВ ====================
# СТРОГИЙ ПОРЯДОК: Страна -> Откуда -> Когда -> Кто -> Детали

MASS_DESTINATIONS = ["Турция", "Египет", "ОАЭ", "Таиланд"]

# Сезонность стран (для умной обработки "нет результатов")
COUNTRY_SEASONS = {
    "Турция": {
        "high": [5, 6, 7, 8, 9, 10],  # Май-Октябрь
        "low": [11, 12, 1, 2, 3, 4],   # Ноябрь-Апрель
        "low_message": "В это время в Турции зимний сезон, купаться в море холодно. Пляжные отели закрыты."
    },
    "Египет": {
        "high": [1, 2, 3, 4, 5, 10, 11, 12],
        "low": [6, 7, 8, 9],
        "low_message": "Летом в Египте очень жарко (+40°C), но можно отдыхать."
    },
    "ОАЭ": {
        "high": [10, 11, 12, 1, 2, 3, 4],
        "low": [5, 6, 7, 8, 9],
        "low_message": "Летом в ОАЭ очень жарко (+45°C), большинство туристов не едут."
    },
    "Таиланд": {
        "high": [11, 12, 1, 2, 3],
        "low": [4, 5, 6, 7, 8, 9, 10],
        "low_message": "В это время в Таиланде сезон дождей, возможны кратковременные ливни."
    },
}

# Названия параметров
PARAM_NAMES_RU = {
    "destination_country": "страна",
    "departure_city": "город вылета",
    "date_from": "даты",
    "nights": "ночи",
    "adults": "туристы",
    "children": "дети",
    "stars": "звёздность",
    "food_type": "питание",
}

SKIP_QUALITY_PHRASES = [
    "всё равно", "все равно", "не важно", "неважно", "любой", "любые",
    "на ваш вкус", "на ваше усмотрение", "что-нибудь хорошее",
    "подбери сам", "подберите сами", "без разницы", "не принципиально",
    "оптимальное", "оптимальный", "какой отель", "какой угодно",
    "любой отель", "все равно какой", "всё равно какой", "хороший отель",
    "нормальный", "средний"
]

# Фразы согласия — пользователь согласен на предложенное действие
AGREEMENT_PHRASES = [
    "хорошо", "ок", "ok", "окей", "давай", "давайте", "погнали", "поехали",
    "да", "конечно", "согласен", "согласна", "пойдёт", "пойдет", "годится",
    "ладно", "можно", "валяй", "вперёд", "вперед", "супер", "отлично",
    "принимается", "договорились", "идёт", "идет", "норм", "нормально",
    "буду рад", "было бы хорошо", "почему бы и нет", "звучит хорошо"
]

# Для совместимости
BASE_PARAMS = ["destination_country", "departure_city", "date_from", "adults"]
DETAIL_PARAMS = ["stars", "food_type"]
REQUIRED_PARAMS = BASE_PARAMS.copy()
CLARIFICATION_QUESTIONS = {
    "destination_country": "В какую страну планируете поездку?",
    "departure_city": "Из какого города планируете вылет?",
    "date_from": "Когда планируете отпуск?",
    "adults": "Сколько человек поедет?",
}
QUALITY_CHECK_QUESTION = "Какой уровень отеля — 5 звёзд всё включено или рассмотрим варианты?"


def get_cascade_stage(params: PartialSearchParams) -> int:
    """
    Определяет текущий этап каскада.
    
    СТРОГИЙ ПОРЯДОК:
    1 — нужна страна
    2 — нужен город вылета (ОБЯЗАТЕЛЬНО!)
    3 — нужны даты
    4 — нужен состав
    5 — нужны детали (звёзды/питание)
    6 — всё собрано, можно искать
    """
    # Этап 1: нет страны
    if not params.get("destination_country"):
        return 1
    
    # Этап 2: нет города вылета - БЛОКИРУЕМ ПОИСК!
    if not params.get("departure_city"):
        return 2
    
    # Этап 3: нет дат
    if not params.get("date_from"):
        return 3
    
    # Этап 4: нет состава
    if not params.get("adults"):
        return 4
    
    # Этап 5: для массовых направлений нужны детали
    country = params.get("destination_country", "")
    is_mass = country in MASS_DESTINATIONS
    
    if is_mass and not params.get("skip_quality_check"):
        has_stars = params.get("stars") is not None
        has_food = params.get("food_type") is not None
        
        if not has_stars or not has_food:
            return 5
    
    # Всё собрано
    return 6


def get_missing_required_params(params: PartialSearchParams) -> list[str]:
    """Определяет недостающие обязательные параметры."""
    missing = []
    
    if not params.get("destination_country"):
        missing.append("destination_country")
    if not params.get("departure_city"):
        missing.append("departure_city")
    if not params.get("date_from"):
        missing.append("date_from")
    if not params.get("adults"):
        missing.append("adults")
    
    return missing


def get_funnel_stage(params: PartialSearchParams) -> str:
    """Определяет этап воронки (для совместимости)."""
    stage = get_cascade_stage(params)
    
    if stage <= 4:
        return "base"
    if stage == 5:
        return "details"
    return "search"


def needs_quality_check(params: PartialSearchParams) -> bool:
    """Проверяет, нужен ли вопрос о качестве."""
    if params.get("skip_quality_check"):
        return False
    if params.get("hotel_name"):
        return False
    
    country = params.get("destination_country", "")
    if country not in MASS_DESTINATIONS:
        return False
    
    has_stars = params.get("stars") is not None
    has_food = params.get("food_type") is not None
    
    return not (has_stars and has_food)


def check_skip_quality_phrase(text: str) -> bool:
    """Проверяет, хочет ли пользователь пропустить уточнение."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in SKIP_QUALITY_PHRASES)


def is_off_season(country: str, month: int) -> tuple[bool, str]:
    """
    Проверяет, является ли месяц несезоном для страны.
    
    Returns:
        (is_off_season, message)
    """
    if country not in COUNTRY_SEASONS:
        return False, ""
    
    season_info = COUNTRY_SEASONS[country]
    if month in season_info.get("low", []):
        return True, season_info.get("low_message", "")
    
    return False, ""


def format_context(params: PartialSearchParams) -> str:
    """Форматирует контекст (что уже известно) для ответа."""
    parts = []
    
    if params.get("destination_country"):
        parts.append(params["destination_country"])
    if params.get("destination_resort"):
        parts.append(params["destination_resort"])
    if params.get("departure_city"):
        parts.append(f"из {params['departure_city']}")
    if params.get("date_from"):
        d = params["date_from"]
        if isinstance(d, date):
            nights = params.get("nights", 7)
            parts.append(f"{d.strftime('%d.%m')}, {nights} ночей")
    if params.get("adults"):
        adults = params["adults"]
        if params.get("children"):
            kids = params["children"]
            parts.append(f"{adults} взр + {len(kids)} дет")
        else:
            parts.append(f"{adults} взр")
    if params.get("stars"):
        parts.append(f"{params['stars']}*")
    if params.get("food_type"):
        parts.append(params["food_type"].value)
    
    return ", ".join(parts) if parts else ""


def create_initial_state() -> AgentState:
    """Создаёт начальное состояние агента."""
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
        selected_tour_id=None,
        cascade_stage=1,
        quality_check_asked=False,
        is_first_message=True,
        greeted=False,
        is_group_request=False,
        group_size=0,
        invalid_country=None,
        flex_search=False,
        flex_days=2,  # По умолчанию ±2 дня для чартерных рейсов
        awaiting_agreement=False,
        pending_action=None,
        search_attempts=0,
        offered_alt_departure=False,
        missing_child_ages=0
    )

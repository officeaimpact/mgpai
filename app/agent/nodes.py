"""
Узлы графа LangGraph для ИИ-ассистента МГП.

Ключевые изменения:
- Город вылета ОБЯЗАТЕЛЕН для поиска
- Умная обработка "нет результатов" с объяснением причины
- Приветствие только один раз за сессию
- Проактивность: мягкая коррекция ожиданий
"""
from __future__ import annotations

import re
import logging
from datetime import date, timedelta
from typing import Optional

# Настройка логгера
logger = logging.getLogger(__name__)

from app.agent.state import (
    AgentState,
    PartialSearchParams,
    get_cascade_stage,
    get_missing_required_params,
    get_funnel_stage,
    needs_quality_check,
    check_skip_quality_phrase,
    format_context,
    is_off_season,
    MASS_DESTINATIONS,
    COUNTRY_SEASONS,
    AGREEMENT_PHRASES,
)
from app.models.domain import (
    SearchRequest,
    Destination,
    FoodType
)
from app.services.tourvisor import tourvisor_service
from app.core.config import settings
from app.agent.prompts import (
    FAQ_RESPONSES,
    DESTINATIONS_KNOWLEDGE,
)


# ==================== ENTITY EXTRACTION ====================

# ==================== ВАЛИДНЫЕ СТРАНЫ (Anti-Hallucination) ====================
# Только страны, которые мы реально продаём через Tourvisor

COUNTRIES_MAP = {
    "турция": "Турция", "турцию": "Турция", "turkey": "Турция",
    "египет": "Египет", "egypt": "Египет",
    "оаэ": "ОАЭ", "эмираты": "ОАЭ", "дубай": "ОАЭ", "uae": "ОАЭ",
    "таиланд": "Таиланд", "тай": "Таиланд", "thailand": "Таиланд", "пхукет": "Таиланд",
    "мальдивы": "Мальдивы", "кипр": "Кипр", "греция": "Греция",
    "испания": "Испания", "италия": "Италия", "черногория": "Черногория",
    "тунис": "Тунис", "доминикана": "Доминикана", "куба": "Куба",
    "шри-ланка": "Шри-Ланка", "вьетнам": "Вьетнам", "индонезия": "Индонезия", "бали": "Индонезия",
    # Россия
    "россия": "Россия", "russia": "Россия", "рф": "Россия",
    "сочи": "Россия", "крым": "Россия", "анапа": "Россия", "геленджик": "Россия",
    "краснодарский край": "Россия", "черное море": "Россия",
}

# Список валидных стран для проверки
VALID_COUNTRIES = set(COUNTRIES_MAP.values())

# Популярные альтернативы для предложения
POPULAR_ALTERNATIVES = ["Турция", "Египет", "ОАЭ", "Таиланд", "Россия (Сочи)"]

# ==================== ИЗВЕСТНЫЕ ОТЕЛИ (для извлечения) ====================
# КРИТИЧНО: НЕ привязываем бренды к странам!
# Rixos, Radisson, Marriott и др. есть в разных странах (Турция, Сочи, ОАЭ...)
# Страну определяем ТОЛЬКО из явного указания пользователя!

KNOWN_HOTELS = {
    # Международные сети (есть везде!)
    "rixos": "Rixos", "риксос": "Rixos",
    "rixos premium": "Rixos Premium", "риксос премиум": "Rixos Premium",
    "radisson": "Radisson", "рэдиссон": "Radisson", "редиссон": "Radisson",
    "marriott": "Marriott", "марриотт": "Marriott", "мариотт": "Marriott",
    "hilton": "Hilton", "хилтон": "Hilton",
    "hyatt": "Hyatt", "хаятт": "Hyatt",
    "sheraton": "Sheraton", "шератон": "Sheraton",
    
    # Турецкие бренды (но НЕ привязываем к Турции!)
    "calista": "Calista Luxury Resort", "калист": "Calista Luxury Resort",
    "regnum": "Regnum Carya", "регнум": "Regnum Carya",
    "titanic": "Titanic", "титаник": "Titanic",
    "gloria serenity": "Gloria Serenity Resort",
    "maxx royal": "Maxx Royal", "макс роял": "Maxx Royal",
    "orange county": "Orange County Resort", "оранж каунти": "Orange County Resort",
    "voyage belek": "Voyage Belek", "вояж белек": "Voyage Belek",
    "delphin": "Delphin Hotel", "дельфин": "Delphin Hotel",
    "barut": "Barut Hotels", "барут": "Barut Hotels",
    
    # Египетские бренды
    "steigenberger": "Steigenberger", "штайгенбергер": "Steigenberger",
    "rixos sharm": "Rixos Sharm El Sheikh",
    "sunrise": "Sunrise Hotels", "санрайз": "Sunrise Hotels",
    "jaz": "Jaz Hotels", "джаз": "Jaz Hotels",
    
    # ОАЭ бренды
    "atlantis": "Atlantis The Palm", "атлантис": "Atlantis The Palm",
    "jumeirah": "Jumeirah Hotels", "джумейр": "Jumeirah Hotels",
    "burj al arab": "Burj Al Arab", "бурдж аль араб": "Burj Al Arab",
}

RESORTS_MAP = {
    # Турция
    "белек": ("Турция", "Белек"), "кемер": ("Турция", "Кемер"),
    "анталья": ("Турция", "Анталья"), "анталия": ("Турция", "Анталья"),
    "сиде": ("Турция", "Сиде"), "алания": ("Турция", "Алания"),
    "бодрум": ("Турция", "Бодрум"), "мармарис": ("Турция", "Мармарис"),
    # Египет
    "шарм": ("Египет", "Шарм-эль-Шейх"), "шарм-эль-шейх": ("Египет", "Шарм-эль-Шейх"),
    "хургада": ("Египет", "Хургада"),
    # Россия
    "сочи": ("Россия", "Сочи"), "адлер": ("Россия", "Адлер"),
    "красная поляна": ("Россия", "Красная Поляна"), "роза хутор": ("Россия", "Роза Хутор"),
    "анапа": ("Россия", "Анапа"), "геленджик": ("Россия", "Геленджик"),
    "крым": ("Россия", "Крым"), "ялта": ("Россия", "Ялта"), "севастополь": ("Россия", "Севастополь"),
}


# ==================== SEARCH MODES (Strict Slot Filling) ====================
def detect_search_mode(text: str) -> str:
    """
    Определяет режим поиска из текста пользователя.
    
    Режимы:
    - "hotel_only" — только отель (НЕ требует departure_city)
    - "burning" — горящие туры (гибкие даты)
    - "package" — пакетный тур (требует departure_city)
    """
    text_lower = text.lower()
    
    # Режим "только отель" (без перелёта) — МАКСИМАЛЬНОЕ ПОКРЫТИЕ!
    hotel_only_triggers = [
        # Явные фразы
        "без перелет", "без перелёт", "без самолет", "без самолёт",
        "только отель", "только гостиниц", "только проживание",
        "отель без", "гостиница без",
        # Типы размещения
        "пансионат", "апартамент", "санатор", "база отдыха",
        "хостел", "гостевой дом", "глэмпинг",
        # Технические термины
        "наземное обслуживание", "наземка", "ground service",
        "без авиа", "без билет", "без перевозк",
        # Контекстные (Россия)
        "размещение в", "отдых в сочи", "отдых в крым",
    ]
    for trigger in hotel_only_triggers:
        if trigger in text_lower:
            logger.info(f"🔍 DETECTED SEARCH MODE: hotel_only (trigger: '{trigger}')")
            return "hotel_only"
    
    # Режим "горящие туры"
    burning_triggers = [
        "горящ", "горячий", "срочно",
        "ближайший вылет", "на ближайшие",
        "последняя минута", "last minute",
        "дешёвый тур", "дешевый тур"
    ]
    for trigger in burning_triggers:
        if trigger in text_lower:
            logger.info(f"🔍 DETECTED SEARCH MODE: burning (trigger: '{trigger}')")
            return "burning"
    
    # По умолчанию — пакетный тур
    logger.info("🔍 DETECTED SEARCH MODE: package (default)")
    return "package"


FOOD_TYPE_MAP = {
    # All Inclusive
    "всё включено": FoodType.AI, "все включено": FoodType.AI, "всё вкл": FoodType.AI,
    "all inclusive": FoodType.AI, "ai": FoodType.AI, "олл инклюзив": FoodType.AI,
    
    # Ultra All Inclusive
    "ультра всё включено": FoodType.UAI, "ультра все включено": FoodType.UAI,
    "ультра": FoodType.UAI, "ultra": FoodType.UAI, "uai": FoodType.UAI,
    
    # Bed & Breakfast
    "завтрак": FoodType.BB, "завтраки": FoodType.BB, "только завтрак": FoodType.BB,
    "только завтраки": FoodType.BB, "bb": FoodType.BB, "bed and breakfast": FoodType.BB,
    
    # Half Board (завтрак + ужин)
    "полупансион": FoodType.HB, "hb": FoodType.HB, "half board": FoodType.HB,
    "завтрак и ужин": FoodType.HB, "завтрак ужин": FoodType.HB,
    
    # Full Board (трёхразовое)
    "полный пансион": FoodType.FB, "fb": FoodType.FB, "full board": FoodType.FB,
    "трёхразовое": FoodType.FB, "трехразовое": FoodType.FB, "три раза": FoodType.FB,
    
    # Room Only (без питания)
    "без питания": FoodType.RO, "ro": FoodType.RO, "room only": FoodType.RO,
}

# ==================== GREETING CLEANER (Python Regex) ====================
# Удаляет приветствия и "мусорные" фразы из начала ответа

def clean_response_text(text: str, is_first_message: bool = False) -> str:
    """
    Очистка ответа от приветствий и "мусорных" фраз.
    
    Args:
        text: Текст ответа
        is_first_message: True если это первое сообщение в сессии (приветствие разрешено)
    
    Returns:
        Очищенный текст
    """
    if not text or is_first_message:
        return text
    
    # Паттерны для удаления (только в начале строки)
    garbage_patterns = [
        r'^(Здравствуйте|Привет|Добрый день|Добрый вечер|Доброе утро)[!,.\s]*',
        r'^(Hello|Hi|Hey)[!,.\s]*',
        r'^(Понял вас|Принято|Хорошо|Отлично|Отличный выбор|Хороший выбор)[!,.\s]*',
        r'^(Я помогу вам|Я подберу|Давайте подберём|Рад помочь)[^.!?]*[.!?]?\s*',
        r'^(Я ИИ-ассистент|Я ваш помощник|Я консультант)[^.!?]*[.!?]?\s*',
        r'^(Спасибо за обращение|Благодарю)[^.!?]*[.!?]?\s*',
    ]
    
    cleaned = text.strip()
    
    for pattern in garbage_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Убираем лишние пробелы и переносы в начале
    cleaned = cleaned.strip()
    
    # Если после очистки пусто — вернём оригинал
    if not cleaned:
        return text.strip()
    
    return cleaned


# ==================== МАППИНГ УСЛУГ ОТЕЛЕЙ (GAP Analysis) ====================
# Ключевые слова -> тип услуги для поиска в справочнике

SERVICES_KEYWORDS = {
    # Тип пляжа
    "песчаный пляж": "песчаный",
    "песок": "песчаный",
    "песочек": "песчаный",
    "галечный пляж": "галечный",
    "галька": "галечный",
    # Расположение
    "1-я линия": "первая линия",
    "первая линия": "первая линия",
    "на берегу": "первая линия",
    "у моря": "первая линия",
    "у самого моря": "первая линия",
    # Развлечения
    "аквапарк": "аквапарк",
    "горки": "горки",
    "водные горки": "горки",
    # Для детей
    "детский клуб": "детский",
    "анимация": "анимация",
    "для детей": "детский",
    "с детьми": "детский",
    # SPA
    "спа": "spa",
    "spa": "spa",
    "бассейн": "бассейн",
    "подогреваемый бассейн": "подогреваемый",
    "крытый бассейн": "крытый бассейн",
}

# ==================== МАППИНГ ТИПОВ ОТЕЛЕЙ (GAP Analysis) ====================
# Параметр hoteltypes для search.php

HOTEL_TYPES_MAP = {
    # Семейный отдых
    "семейный": "family",
    "для семьи": "family",
    "семейный отель": "family",
    "семьей": "family",
    # VIP / Люкс
    "vip": "deluxe",
    "вип": "deluxe",
    "люкс": "deluxe",
    "премиум": "deluxe",
    "роскошный": "deluxe",
    "luxury": "deluxe",
    # Пляжный
    "пляжный": "beach",
    "на пляже": "beach",
    # Городской
    "городской": "city",
    "в городе": "city",
    # Активный отдых
    "активный": "active",
    "спортивный": "active",
    # Спокойный отдых
    "спокойный": "relax",
    "релакс": "relax",
    "тихий": "relax",
    # Оздоровительный
    "оздоровительный": "health",
    "лечебный": "health",
    "санаторий": "health",
}

# ==================== МАППИНГ ТИПОВ ТУРОВ (GAP Analysis) ====================
# Параметр tourtype для search.php

TOUR_TYPES_MAP = {
    "пляжный": 1,
    "пляж": 1,
    "море": 1,
    "горнолыжный": 2,
    "лыжи": 2,
    "горы": 2,
    "экскурсионный": 3,
    "экскурсии": 3,
    "экскурсия": 3,
}

DEPARTURE_CITIES = {
    "москва": "Москва", "москвы": "Москва", "мск": "Москва",
    "питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "петербург": "Санкт-Петербург",
    "казань": "Казань", "казани": "Казань",
    "екатеринбург": "Екатеринбург", "екб": "Екатеринбург",
    "новосибирск": "Новосибирск", "новосиб": "Новосибирск",
    "краснодар": "Краснодар",
    "сочи": "Сочи",
    "ростов": "Ростов-на-Дону",
    "самара": "Самара",
    "уфа": "Уфа",
    "нижний": "Нижний Новгород",
    "воронеж": "Воронеж",
    "пермь": "Пермь",
    "челябинск": "Челябинск",
    "красноярск": "Красноярск",
    "минеральные воды": "Минеральные Воды", "минводы": "Минеральные Воды",
}


def extract_entities_regex(text: str) -> dict:
    """Извлечение сущностей из текста."""
    text_lower = text.lower()
    entities = {}
    
    # ==================== ГОРЯЩИЕ ТУРЫ / СРОЧНО ====================
    # Если пользователь хочет "горящий тур" — дата = завтра
    # НО: НЕ ставим nights автоматически! Агент ОБЯЗАН спросить.
    if any(word in text_lower for word in ["горящ", "горячий", "срочно", "на ближайшие", "ближайший вылет"]):
        entities["is_hot_tour"] = True
        # Дата вылета = завтра (это разумный дефолт для "горящих")
        entities["date_from"] = date.today() + timedelta(days=1)
        # НЕ СТАВИМ nights! Агент ОБЯЗАН спросить "На сколько дней?"
    
    # 1. Страна (из известного справочника)
    country_found = False
    for key, country in COUNTRIES_MAP.items():
        if key in text_lower:
            entities["destination_country"] = country
            country_found = True
            break
    
    # Если страна не найдена в справочнике — пробуем извлечь неизвестную
    # Паттерн: "хочу в [Страна]", "поехать в [Страна]", "в [Страна]у" и т.д.
    if not country_found:
        # Слова, которые НЕ являются странами
        skip_words = {
            # Месяцы
            "январе", "феврале", "марте", "апреле", "мае", "июне", 
            "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
            # Города
            "москву", "москвы", "москве", "питер", "питера", "казань", "казани",
            # Отели
            "отель", "отеле", "отелю",
            # Другие слова
            "тур", "туре", "поездку", "отпуск",
        }
        
        unknown_country_patterns = [
            r'(?:хочу|поеду|поехать|слетать|отдохнуть|тур)\s+в\s+([а-яё]+)\b',
        ]
        for pattern in unknown_country_patterns:
            match = re.search(pattern, text_lower)
            if match:
                potential_country = match.group(1)
                # Проверяем, что это не skip_word и длина > 3
                if potential_country not in skip_words and len(potential_country) > 3:
                    # Капитализируем для отображения
                    entities["destination_country"] = potential_country.title()
                    break
    
    # 2. Курорт
    for key, (country, resort) in RESORTS_MAP.items():
        if key in text_lower:
            entities["destination_country"] = country
            entities["destination_resort"] = resort
            break
    
    # 3. Город вылета (ВАЖНО!)
    for key, city in DEPARTURE_CITIES.items():
        if key in text_lower:
            entities["departure_city"] = city
            break
    
    # 4. Даты
    months_map = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    
    dates_found = []
    
    # dd.mm.yyyy
    for match in re.finditer(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?', text):
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else date.today().year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            if d < date.today():
                d = date(year + 1, month, day)
            dates_found.append(d)
        except ValueError:
            pass
    
    # "dd месяца"
    for match in re.finditer(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', text_lower):
        day = int(match.group(1))
        month = months_map[match.group(2)]
        year = date.today().year
        try:
            d = date(year, month, day)
            if d < date.today():
                d = date(year + 1, month, day)
            dates_found.append(d)
        except ValueError:
            pass
    
    # Месяц без даты — допускаем и с предлогом и без
    if not dates_found:
        month_patterns = [
            (r'(?:в|на|к)?\s*январ[еья]?', 1), (r'(?:в|на|к)?\s*феврал[еья]?', 2),
            (r'(?:в|на|к)?\s*март[еа]?', 3), (r'(?:в|на|к)?\s*апрел[еья]?', 4),
            (r'(?:в|на|к)?\s*ма[йюея]', 5), (r'(?:в|на|к)?\s*июн[еья]?', 6),
            (r'(?:в|на|к)?\s*июл[еья]?', 7), (r'(?:в|на|к)?\s*август[еа]?', 8),
            (r'(?:в|на|к)?\s*сентябр[еья]?', 9), (r'(?:в|на|к)?\s*октябр[еья]?', 10),
            (r'(?:в|на|к)?\s*ноябр[еья]?', 11), (r'(?:в|на|к)?\s*декабр[еья]?', 12),
        ]
        
        for pattern, month_num in month_patterns:
            if re.search(pattern, text_lower):
                year = date.today().year
                try:
                    target = date(year, month_num, 1)
                    if target < date.today():
                        target = date(year + 1, month_num, 1)
                    dates_found.append(target)
                except ValueError:
                    pass
                break
    
    if dates_found:
        dates_found.sort()
        # === ВАЛИДАЦИЯ: дата НЕ должна быть в прошлом! ===
        valid_dates = [d for d in dates_found if d >= date.today()]
        if valid_dates:
            entities["date_from"] = valid_dates[0]
            # Помечаем, что дата ТОЧНАЯ (указан конкретный день)
            entities["is_exact_date"] = True
            # === STRICT SLOT FILLING: дата ЯВНО подтверждена! ===
            entities["dates_confirmed"] = True
        if len(dates_found) > 1:
            entities["date_to"] = dates_found[-1]
            entities["nights"] = (dates_found[-1] - dates_found[0]).days
    
    # 5. Количество ночей
    # КРИТИЧНО: Валидация — nights не может быть > 21 без ЯВНОГО запроса!
    nights_match = re.search(r'(\d+)\s*(?:ноч|ночей|ночи|дней|дня|день)', text_lower)
    if nights_match:
        nights = int(nights_match.group(1))
        # Разумный диапазон: 1-21 ночей (стандартные туры)
        # Более 21 ночи — только если явно запросили (например "30 ночей")
        if 1 <= nights <= 21:
            entities["nights"] = nights
            if "date_from" in entities and "date_to" not in entities:
                entities["date_to"] = entities["date_from"] + timedelta(days=nights)
        elif nights > 21 and nights <= 30:
            # Длинный тур — помечаем явно, но принимаем
            entities["nights"] = nights
            entities["long_stay_explicit"] = True
            if "date_from" in entities and "date_to" not in entities:
                entities["date_to"] = entities["date_from"] + timedelta(days=nights)
        # Если > 30 — игнорируем (скорее всего ошибка/галлюцинация)
    
    # 6. Количество взрослых
    # ВАЖНО: Извлекаем даже если > 6 (для эскалации групповых заявок)
    adults_match = re.search(r'(\d+)\s*(?:взросл|человек|чел\.)', text_lower)
    if adults_match:
        adults = int(adults_match.group(1))
        if 1 <= adults <= 20:  # Разрешаем до 20 для групп
            entities["adults"] = adults
            entities["adults_explicit"] = True  # ЯВНО указано пользователем!
    
    # Слова для количества (только если не нашли число)
    if "adults" not in entities:
        if re.search(r'вдво[её]м|двое|на двоих|для двоих', text_lower):
            entities["adults"] = 2
            entities["adults_explicit"] = True
        elif re.search(r'втро[её]м|трое|на троих|для троих', text_lower):
            entities["adults"] = 3
            entities["adults_explicit"] = True
        elif re.search(r'вчетвером|четверо|на четверых', text_lower):
            entities["adults"] = 4
            entities["adults_explicit"] = True
        elif re.search(r'один|одного|сам\b|одна\b', text_lower):
            entities["adults"] = 1
            entities["adults_explicit"] = True
    
    # УБРАНО: Дефолтное adults=2 — теперь агент ОБЯЗАН спросить!
    # Если adults не указан явно — НЕ подставляем дефолт
    
    # 7. Дети (КРИТИЧНО: возраст ОБЯЗАТЕЛЕН!)
    children_ages = []
    children_count = 0  # Счётчик упомянутых детей
    
    # Паттерны для извлечения возраста
    age_patterns = [
        r'(?:реб[её]н(?:о?к)?|дочь?|сын|дочк[еуа]|сын[уа]?)\s*(?:,?\s*)?(\d{1,2})\s*(?:год|лет|года)',
        r'с\s+реб[её]нком\s+(\d{1,2})',
        r'(\d{1,2})\s*(?:год|лет|года)(?:\s+реб[её]нк)?',
        r'возраст(?:а|ом)?\s*(?:детей|ребенк[ау])?\s*[\-:]?\s*(\d{1,2})',
        r'(?:ему|ей|им)\s+(\d{1,2})\s*(?:год|лет|года)?',
    ]
    for pattern in age_patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            age = int(m) if isinstance(m, str) else int(m[0]) if isinstance(m, tuple) else int(m)
            if 0 <= age <= 17 and age not in children_ages:
                children_ages.append(age)
    
    # Множественные возрасты: "5 и 10 лет", "детям 3 и 7"
    multi_age_match = re.search(r'(\d{1,2})\s*(?:и|,)\s*(\d{1,2})\s*(?:год|лет|года)', text_lower)
    if multi_age_match:
        for i in [1, 2]:
            age = int(multi_age_match.group(i))
            if 0 <= age <= 17 and age not in children_ages:
                children_ages.append(age)
    
    # Определяем количество упомянутых детей БЕЗ возраста
    # "с ребенком", "с детьми", "2 детей" и т.д.
    children_mentioned_patterns = [
        (r'с\s+реб[её]нком', 1),
        (r'с\s+дет(?:ьми|ей)', 0),  # неизвестное количество
        (r'(\d+)\s+(?:реб[её]н|дет)', None),  # извлекаем число
        (r'реб[её]н(?:о?к|ка)', 1),
        (r'дети', 0),  # неопределённо
        (r'двое\s+детей', 2),
        (r'трое\s+детей', 3),
    ]
    
    for pattern, count in children_mentioned_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if count is None:  # Извлекаем число из группы
                children_count = max(children_count, int(match.group(1)))
            elif count > 0:
                children_count = max(children_count, count)
            else:  # count == 0 — просто упоминание "детей"
                if children_count == 0:
                    children_count = 1  # Минимум 1
    
    if children_ages:
        entities["children"] = children_ages
        entities["children_count"] = len(children_ages)
    
    # КРИТИЧНО: Если упомянуты дети, но возраст НЕ указан — помечаем!
    if children_count > 0 and not children_ages:
        entities["children_mentioned"] = True
        entities["children_count_mentioned"] = children_count
        # НЕ добавляем children с дефолтным возрастом!
    
    # ==================== ПРОВЕРКА "БЕЗ ДЕТЕЙ" ====================
    # Если пользователь явно сказал что без детей — помечаем
    no_children_patterns = [
        r'без\s+дет',
        r'детей\s+нет',
        r'нет\s+детей',
        r'только\s+взросл',
        r'одни\s+взросл',
        r'взрослые\s+без',
    ]
    for pattern in no_children_patterns:
        if re.search(pattern, text_lower):
            entities["no_children_explicit"] = True
            entities["children_mentioned"] = False  # Явно указано что детей нет
            break
    
    # ==================== СЕМАНТИКА СОСТАВА "Я и сын" / "Мы с мужем" ====================
    # "я и сын/дочь" → adults=1 + ребёнок
    if re.search(r'я\s+(?:и|с)\s+(?:сын|дочь|дочк|сыно)', text_lower):
        if "adults" not in entities:
            entities["adults"] = 1
            entities["adults_explicit"] = True
        entities["children_mentioned"] = True
        entities["children_count_mentioned"] = 1
    
    # "мы с мужем/женой" → adults=2
    if re.search(r'мы\s+с\s+(?:муж|жен|супруг)', text_lower):
        if "adults" not in entities:
            entities["adults"] = 2
            entities["adults_explicit"] = True
    
    # 8. Тип питания
    for key, food_type in FOOD_TYPE_MAP.items():
        if key in text_lower:
            entities["food_type"] = food_type
            entities["food_type_updated"] = True  # Флаг: обновлено в текущем шаге
            break
    
    # 9. Звёздность
    stars_match = re.search(r'(\d)\s*(?:\*|звезд|зв[её]зд)', text_lower)
    if stars_match:
        stars = int(stars_match.group(1))
        if 3 <= stars <= 5:
            entities["stars"] = stars
            entities["stars_updated"] = True  # Флаг: обновлено в текущем шаге
    
    # 10. Название отеля (поиск по известным)
    # КРИТИЧНО: НЕ определяем страну по бренду отеля!
    # Rixos есть в Турции, Сочи, ОАЭ — страну берём только из явного указания!
    for key, hotel_name in KNOWN_HOTELS.items():
        if key in text_lower:
            entities["hotel_name"] = hotel_name
            # НЕ перезаписываем destination_country — оставляем как есть!
            break
    
    # ==================== 11. УСЛУГИ ОТЕЛЕЙ (GAP Analysis) ====================
    # Извлекаем ключевые слова для фильтрации по услугам
    service_keywords_found = []
    for keyword, service_type in SERVICES_KEYWORDS.items():
        if keyword in text_lower:
            if service_type not in service_keywords_found:
                service_keywords_found.append(service_type)
    
    if service_keywords_found:
        entities["service_keywords"] = service_keywords_found
    
    # ==================== 12. ТИПЫ ОТЕЛЕЙ (GAP Analysis) ====================
    hotel_types_found = []
    for keyword, hotel_type in HOTEL_TYPES_MAP.items():
        if keyword in text_lower:
            if hotel_type not in hotel_types_found:
                hotel_types_found.append(hotel_type)
    
    if hotel_types_found:
        entities["hotel_types"] = hotel_types_found
    
    # ==================== 13. ТИП ТУРА (GAP Analysis) ====================
    for keyword, tour_type in TOUR_TYPES_MAP.items():
        if keyword in text_lower:
            entities["tour_type"] = tour_type
            break
    
    return entities


def detect_phone_number(text: str) -> Optional[str]:
    """Извлекает номер телефона."""
    patterns = [
        r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        r'(?:\+7|8)\d{10}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def detect_intent_regex(text: str, awaiting_phone: bool = False) -> str:
    """Определение намерения пользователя."""
    text_lower = text.lower()
    
    if awaiting_phone and detect_phone_number(text):
        return "phone_provided"
    
    # === ПАГИНАЦИЯ: "Ещё туры" (GAP Analysis) ===
    if any(word in text_lower for word in [
        "ещё туры", "еще туры", "ещё вариант", "еще вариант",
        "показать ещё", "показать еще", "покажи ещё", "покажи еще",
        "больше туров", "больше вариант", "другие туры", "другие вариант",
        "ещё предложен", "еще предложен", "следующие туры", "следующие вариант"
    ]):
        return "more_tours"
    
    # === УГЛУБЛЁННЫЙ ПОИСК: "Искать ещё" (GAP Analysis) ===
    if any(word in text_lower for word in [
        "искать ещё", "искать еще", "продолжить поиск", "ищи ещё",
        "ищи еще", "поискать ещё", "поискать еще", "дольше искать",
        "углублённый поиск", "глубже искать"
    ]):
        return "continue_search"
    
    if any(word in text_lower for word in ["заброниров", "забронируй", "оставь заявк", "оставить заявк", "хочу заказ"]):
        return "booking"
    
    if any(word in text_lower for word in ["горящ", "горячие", "скидк"]):
        return "hot_tours"
    
    if any(word in text_lower for word in ["виза", "паспорт", "въезд"]):
        return "faq_visa"
    if any(word in text_lower for word in ["оплат", "карт", "рассрочк"]):
        return "faq_payment"
    if any(word in text_lower for word in ["возврат", "отмен"]):
        return "faq_cancel"
    if any(word in text_lower for word in ["страхов", "полис"]):
        return "faq_insurance"
    if any(word in text_lower for word in ["документ", "справк"]):
        return "faq_documents"
    
    if any(word in text_lower for word in ["привет", "здравствуй", "добрый день"]):
        return "greeting"
    
    # General chat
    if any(word in text_lower for word in ["погода", "температур", "климат", "когда лучше"]):
        return "general_chat"
    if any(word in text_lower for word in ["посоветуй", "порекомендуй", "подскаж", "какой лучше", "что выбрать"]):
        return "general_chat"
    if any(word in text_lower for word in ["какой отель", "лучший отель", "отель для дет"]):
        return "general_chat"
    if any(word in text_lower for word in ["что посмотреть", "достопримечательн", "экскурси"]):
        return "general_chat"
    
    return "search_tour"


async def extract_entities_with_llm(text: str, awaiting_phone: bool = False) -> dict:
    """Извлечение сущностей (LLM + regex fallback)."""
    from app.agent.llm import llm_client
    
    llm_entities = {}
    llm_intent = None
    
    if settings.YANDEX_GPT_ENABLED:
        try:
            result = await llm_client.extract_entities(text)
            llm_entities = result.get("entities", {})
            llm_intent = result.get("intent")
            
            # ==================== ВАЛИДАЦИЯ ТИПОВ ОТ LLM ====================
            
            # date_from: str -> date (отфильтровываем невалидные значения)
            if "date_from" in llm_entities:
                val = llm_entities["date_from"]
                if isinstance(val, str):
                    # Отфильтровываем мусорные значения
                    if val.lower() in ("не указана", "не указано", "null", "none", ""):
                        del llm_entities["date_from"]
                    else:
                        try:
                            parsed_date = date.fromisoformat(val)
                            # === ВАЛИДАЦИЯ: дата НЕ должна быть в прошлом! ===
                            if parsed_date < date.today():
                                logger.info(f"   ⚠️ Дата {parsed_date} в прошлом — игнорируем")
                                del llm_entities["date_from"]
                            else:
                                llm_entities["date_from"] = parsed_date
                                llm_entities["dates_confirmed"] = True  # ЯВНО указана!
                        except ValueError:
                            del llm_entities["date_from"]
            
            # date_to: str -> date (отфильтровываем невалидные значения)
            if "date_to" in llm_entities:
                val = llm_entities["date_to"]
                if isinstance(val, str):
                    # Отфильтровываем мусорные значения
                    if val.lower() in ("не указана", "не указано", "null", "none", ""):
                        del llm_entities["date_to"]
                    else:
                        try:
                            llm_entities["date_to"] = date.fromisoformat(val)
                        except ValueError:
                            del llm_entities["date_to"]
            
            # food_type: str -> FoodType
            if "food_type" in llm_entities:
                val = llm_entities["food_type"]
                if isinstance(val, str):
                    try:
                        llm_entities["food_type"] = FoodType(val)
                    except ValueError:
                        del llm_entities["food_type"]
            
            # adults: str -> int (валидация 1-20, для групп > 6)
            # КРИТИЧНО: LLM НЕ ставит adults_explicit — только regex!
            # Это защита от галлюцинаций: LLM может "угадать" adults=1
            if "adults" in llm_entities:
                val = llm_entities["adults"]
                if isinstance(val, str):
                    try:
                        llm_entities["adults"] = int(val)
                    except ValueError:
                        del llm_entities["adults"]
                if isinstance(llm_entities.get("adults"), int):
                    # Разрешаем до 20 для групповых заявок
                    if not (1 <= llm_entities["adults"] <= 20):
                        del llm_entities["adults"]
                    # НЕ ставим adults_explicit! Только regex может это делать.
            
            # nights: str -> int (валидация 1-21, max 30)
            # КРИТИЧНО: nights > 21 — подозрительно (галлюцинация), > 30 — точно ошибка
            if "nights" in llm_entities:
                val = llm_entities["nights"]
                if isinstance(val, str):
                    try:
                        llm_entities["nights"] = int(val)
                    except ValueError:
                        del llm_entities["nights"]
                if isinstance(llm_entities.get("nights"), int):
                    nights_val = llm_entities["nights"]
                    # Отсекаем галлюцинации типа "364 ночи"
                    if nights_val > 30 or nights_val < 1:
                        del llm_entities["nights"]
                    elif nights_val > 21:
                        # Длинный тур — оставляем, но с осторожностью
                        llm_entities["long_stay_explicit"] = True
            
            # stars: str -> int (валидация 3-5)
            if "stars" in llm_entities:
                val = llm_entities["stars"]
                if isinstance(val, str):
                    try:
                        llm_entities["stars"] = int(val)
                    except ValueError:
                        del llm_entities["stars"]
                if isinstance(llm_entities.get("stars"), int):
                    if not (3 <= llm_entities["stars"] <= 5):
                        del llm_entities["stars"]
            
            # children: должен быть list[int]
            if "children" in llm_entities:
                val = llm_entities["children"]
                if isinstance(val, list):
                    validated_children = []
                    for age in val:
                        if isinstance(age, int) and 0 <= age <= 15:
                            validated_children.append(age)
                        elif isinstance(age, str):
                            try:
                                a = int(age)
                                if 0 <= a <= 15:
                                    validated_children.append(a)
                            except ValueError:
                                pass
                    llm_entities["children"] = validated_children if validated_children else None
                else:
                    del llm_entities["children"]
                    
        except Exception as e:
            print(f"LLM extraction failed: {e}")
    
    regex_entities = extract_entities_regex(text)
    regex_intent = detect_intent_regex(text, awaiting_phone)
    
    final_entities = regex_entities.copy()
    for key, value in llm_entities.items():
        if value is not None:
            # НЕ перезаписываем страну, если LLM вернул невалидное значение
            if key == "destination_country":
                # Если regex уже нашёл валидную страну - не перезаписываем
                if regex_entities.get("destination_country") and regex_entities["destination_country"] in VALID_COUNTRIES:
                    continue
                # Проверяем, что LLM вернул валидную страну
                if value not in VALID_COUNTRIES and value.lower() not in COUNTRIES_MAP:
                    continue
            
            # НЕ перезаписываем adults/nights если regex уже нашёл валидное значение
            if key in ("adults", "nights") and key in regex_entities:
                continue
            
            final_entities[key] = value
    
    intent = llm_intent if llm_intent else regex_intent
    
    if awaiting_phone and detect_phone_number(text):
        intent = "phone_provided"
    elif detect_intent_regex(text, awaiting_phone) == "booking":
        intent = "booking"
    elif regex_intent == "general_chat" and intent == "search_tour":
        intent = "general_chat"
    
    return {"intent": intent, "entities": final_entities}


# ==================== GRAPH NODES ====================

def check_agreement_phrase(text: str) -> bool:
    """Проверяет, является ли текст фразой согласия."""
    text_lower = text.lower().strip()
    # Короткие ответы (1-3 слова) проверяем на согласие
    if len(text_lower.split()) <= 3:
        for phrase in AGREEMENT_PHRASES:
            if phrase in text_lower:
                return True
    return False


async def input_analyzer(state: AgentState) -> AgentState:
    """Анализ ввода пользователя."""
    if not state["messages"]:
        return state
    
    last_message = state["messages"][-1]
    if last_message["role"] != "user":
        return state
    
    user_text = last_message["content"]
    awaiting_phone = state.get("awaiting_phone", False)
    
    # ==================== SEARCH MODE DETECTION ====================
    # Определяем режим поиска из текста пользователя
    detected_mode = detect_search_mode(user_text)
    current_mode = state.get("search_mode", "package")
    
    # ПРИНУДИТЕЛЬНО сохраняем режим поиска (даже если package)
    # hotel_only и burning режимы требуют особой обработки!
    if detected_mode != "package" or current_mode == "package":
        state["search_mode"] = detected_mode
    
    # Логируем ВСЕГДА
    logger.info(f"   🔍 SEARCH MODE: {state.get('search_mode', 'package')} (detected: {detected_mode})")
    
    # ==================== КОНТЕКСТНАЯ ОСВЕДОМЛЁННОСТЬ ====================
    # КРИТИЧНО: Если уже идёт сбор параметров (cascade_stage > 1) и ответ короткий,
    # это скорее всего ответ на предыдущий вопрос, а не новый intent!
    current_cascade_stage = state.get("cascade_stage", 1)
    current_params = state.get("search_params", {}) or {}
    
    # Логируем для отладки
    logger.info(f"   📊 Текущий cascade_stage: {current_cascade_stage}")
    logger.info(f"   📊 Текущие параметры: {current_params}")
    
    # ==================== ОБРАБОТКА СОГЛАСИЯ ====================
    # Если пользователь ответил "хорошо", "ок", "давай", "да" на предложение
    if state.get("awaiting_agreement") and check_agreement_phrase(user_text):
        pending_action = state.get("pending_action")
        current_params = state["search_params"].copy() if state["search_params"] else {}
        
        if pending_action == "flex_dates":
            # Согласие на гибкие даты — расширяем до ±5 дней
            state["flex_search"] = True
            state["flex_days"] = 5  # Расширенный диапазон после согласия
            state["awaiting_agreement"] = False
            state["pending_action"] = None
            state["intent"] = "search_tour"
            state["search_params"] = current_params
            state["cascade_stage"] = 6  # Принудительно ставим готовность к поиску
            state["missing_info"] = []
            state["error"] = None  # Сбрасываем ошибки
            state["search_attempts"] = state.get("search_attempts", 0)  # Не увеличиваем счётчик
            return state
        elif pending_action == "any_hotel":
            # Согласие на любой отель
            current_params["skip_quality_check"] = True
            state["search_params"] = current_params
            state["awaiting_agreement"] = False
            state["pending_action"] = None
            state["intent"] = "search_tour"
            state["cascade_stage"] = 6
            state["missing_info"] = []
            state["error"] = None
            return state
        elif pending_action == "alt_departure":
            # Согласие на альтернативный город вылета
            current_params["departure_city"] = "Москва"
            state["search_params"] = current_params
            state["awaiting_agreement"] = False
            state["pending_action"] = None
            state["intent"] = "search_tour"
            state["cascade_stage"] = 6
            state["missing_info"] = []
            state["error"] = None
            state["flex_days"] = 2  # Базовый диапазон для нового поиска
            return state
        elif pending_action == "alt_food":
            # === SMART FALLBACK: Согласие на другой тип питания (GAP Analysis) ===
            # Меняем AI/UAI на HB (полупансион)
            current_params["food_type"] = FoodType.HB
            state["search_params"] = current_params
            state["awaiting_agreement"] = False
            state["pending_action"] = None
            state["offered_alt_food"] = True
            state["intent"] = "search_tour"
            state["cascade_stage"] = 6
            state["missing_info"] = []
            state["error"] = None
            return state
        elif pending_action == "lower_stars":
            # === SMART FALLBACK: Согласие на понижение звёзд (GAP Analysis) ===
            current_stars = current_params.get("stars", 5)
            current_params["stars"] = max(3, current_stars - 1)  # Не ниже 3*
            state["search_params"] = current_params
            state["awaiting_agreement"] = False
            state["pending_action"] = None
            state["offered_lower_stars"] = True
            state["intent"] = "search_tour"
            state["cascade_stage"] = 6
            state["missing_info"] = []
            state["error"] = None
            return state
    
    # ==================== CONTEXT AWARENESS: Интерпретация коротких ответов ====================
    # Если пользователь ввёл только число (например "5"), смотрим контекст последнего вопроса
    user_text_stripped = user_text.strip()
    last_question = state.get("last_question_type")
    
    if user_text_stripped.isdigit() and last_question:
        number = int(user_text_stripped)
        current_params = state["search_params"].copy() if state["search_params"] else {}
        
        if last_question == "nights" and 1 <= number <= 21:
            # "5" в ответ на "На сколько ночей?" → nights=5
            current_params["nights"] = number
            state["search_params"] = current_params
            state["last_question_type"] = None  # Сбрасываем контекст
            
            # Пересчитываем cascade_stage (импорт уже вверху файла)
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params, state.get("search_mode", "package"))
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
        
        elif last_question == "adults" and 1 <= number <= 10:
            # "2" в ответ на "Сколько человек?" → adults=2
            current_params["adults"] = number
            current_params["adults_explicit"] = True
            state["search_params"] = current_params
            state["last_question_type"] = None
            
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params, state.get("search_mode", "package"))
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
        
        elif last_question == "stars" and 3 <= number <= 5:
            # "5" в ответ на "Какой уровень отеля?" → stars=5
            current_params["stars"] = number
            current_params["skip_quality_check"] = True
            state["search_params"] = current_params
            state["last_question_type"] = None
            state["quality_check_asked"] = True
            state["clarification_asked"] = True  # Пользователь ответил конкретно
            
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params, state.get("search_mode", "package"))
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
        
        elif last_question == "children_ages" and 0 <= number <= 17:
            # "7" в ответ на "Укажите возраст ребёнка" → children=[7]
            existing_children = current_params.get("children", [])
            if number not in existing_children:
                existing_children.append(number)
            current_params["children"] = existing_children
            current_params["children_mentioned"] = False  # Сбрасываем флаг
            current_params["children_count_mentioned"] = 0
            state["search_params"] = current_params
            state["last_question_type"] = None
            
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params, state.get("search_mode", "package"))
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
    
    # ==================== ОБРАБОТКА ОТВЕТА НА CHILDREN_CHECK ====================
    # Если спрашивали "поедут ли дети?" и пользователь ответил "нет"/"без детей"
    if last_question == "children_check":
        current_params = state["search_params"].copy() if state["search_params"] else {}
        
        # Проверяем негативные ответы
        no_children_words = ["нет", "без", "только взр", "одни", "не будет", "не едут", "не поед"]
        is_no_children = any(word in user_text.lower() for word in no_children_words)
        
        if is_no_children:
            current_params["no_children_explicit"] = True
            current_params["children_mentioned"] = False
            state["search_params"] = current_params
            state["last_question_type"] = None
            
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params, state.get("search_mode", "package"))
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
        
        # Проверяем позитивные ответы (есть дети, но нужен возраст)
        yes_children_words = ["да", "есть", "будут", "едут", "поед", "с реб", "с дет"]
        is_yes_children = any(word in user_text.lower() for word in yes_children_words)
        
        if is_yes_children:
            current_params["children_mentioned"] = True
            # Проверяем, указал ли возраст в этом же сообщении
            # Это сделает extract_entities_regex ниже
    
    result = await extract_entities_with_llm(user_text, awaiting_phone)
    intent = result.get("intent", "search_tour")
    entities = result.get("entities", {})
    
    # ==================== АНТИ-СБРОС INTENT ====================
    # КРИТИЧНО: Если мы в середине сбора параметров (cascade_stage > 1),
    # И пользователь ввёл короткий ответ (1-3 слова),
    # И были извлечены entities — это ОТВЕТ на вопрос, не новый intent!
    
    word_count = len(user_text.strip().split())
    has_useful_entities = bool(entities)  # Если что-то извлекли
    
    # Если cascade_stage > 1 и intent = greeting/search_tour, но есть entities — 
    # это ответ на вопрос, не сброс диалога!
    if current_cascade_stage > 1 and word_count <= 3:
        if intent == "greeting":
            # Короткий ответ типа "москва" ошибочно определён как greeting
            logger.info(f"   🔄 Переопределяю intent: greeting -> search_tour (середина каскада)")
            intent = "search_tour"
        
        # Если есть текущие параметры (страна уже известна) — продолжаем сбор
        if current_params and intent in ("greeting", "search_tour"):
            # Сохраняем текущие параметры, не сбрасываем
            logger.info(f"   ✅ Продолжаем каскад, сохраняем параметры")
    
    # ==================== ОБЪЕДИНЕНИЕ ПАРАМЕТРОВ ====================
    # КРИТИЧНО: merged_params = копия текущих параметров + новые из entities
    merged_params = current_params.copy() if current_params else {}
    
    # ==================== ПРИОРИТЕТ НОВЫХ ДАННЫХ ====================
    # Новые данные от пользователя ВСЕГДА добавляются/обновляются в merged_params
    date_changed = False
    country_changed = False
    critical_params_changed = False
    
    for key, value in entities.items():
        if value is not None:
            old_value = merged_params.get(key)
            
            # Особая обработка дат — новые даты ВСЕГДА заменяют старые
            if key in ("date_from", "date_to", "nights"):
                if old_value != value:
                    date_changed = True
                    critical_params_changed = True
            
            # Смена страны — критическое изменение
            elif key == "destination_country":
                if old_value and old_value != value:
                    country_changed = True
                    critical_params_changed = True
            
            # ДЕТИ И КОНТЕКСТ: Не затираем children_mentioned=True если в новом сообщении нет упоминания
            # Это защита от потери информации о детях при следующих проходах
            elif key == "children_mentioned":
                # Если уже было True, а новое значение False (неявное) — сохраняем True
                if old_value is True and value is False:
                    logger.info(f"   🛡️ Защита children_mentioned: сохраняем True")
                    continue  # Не затираем
            
            merged_params[key] = value
    
    # ==================== СБРОС ФЛАГОВ ПРИ КРИТИЧЕСКИХ ИЗМЕНЕНИЯХ ====================
    # При смене страны или даты — сбрасываем clarification_asked для нового поиска
    if critical_params_changed:
        state["awaiting_agreement"] = False
        state["pending_action"] = None
        state["error"] = None
        state["flex_search"] = False
        state["flex_days"] = 2  # Базовый диапазон ±2 дня
        state["search_attempts"] = 0
        state["offered_alt_departure"] = False
        
        # КРИТИЧНО: Сбрасываем ВСЕ флаги качества для нового запроса
        if country_changed:
            state["clarification_asked"] = False
            state["quality_check_asked"] = False
            state["skip_quality_check"] = False  # RESET FLAGS: для новой страны заново спросим про звёзды
            merged_params["skip_quality_check"] = False  # Также в параметрах
            logger.info(f"   🔄 Смена страны: {merged_params.get('destination_country')} → сброс ВСЕХ флагов качества")
    
    # ==================== КРИТИЧЕСКАЯ ПРОВЕРКА: ДЕТИ БЕЗ ВОЗРАСТА ====================
    # Если упомянуты дети, но возраст НЕ указан — БЛОКИРУЕМ поиск и спрашиваем
    children_mentioned = entities.get("children_mentioned") or merged_params.get("children_mentioned")
    children_count_mentioned = entities.get("children_count_mentioned") or merged_params.get("children_count_mentioned", 0)
    existing_children_ages = merged_params.get("children", [])
    
    if children_mentioned and not existing_children_ages:
        state["search_params"] = merged_params
        state["intent"] = "ask_child_ages"
        state["missing_child_ages"] = children_count_mentioned or 1
        # Не продолжаем — нужен возраст детей
        return state
    
    # Если новые возрасты извлечены — сбрасываем флаг
    if entities.get("children") and len(entities["children"]) > 0:
        merged_params["children_mentioned"] = False
        merged_params["children_count_mentioned"] = 0
    
    # ==================== ПРОВЕРКА ГРУППЫ > 6 ЧЕЛОВЕК ====================
    total_people = merged_params.get("adults", 0) + len(merged_params.get("children", []))
    if total_people > 6:
        # Групповая заявка — эскалация на менеджера
        state["search_params"] = merged_params
        state["intent"] = "group_booking"
        state["is_group_request"] = True
        state["group_size"] = total_people
        state["is_first_message"] = len(state["messages"]) <= 1 and not state.get("greeted", False)
        return state
    
    # ==================== ВАЛИДАЦИЯ СТРАНЫ (Anti-Hallucination) ====================
    # Проверяем только если пользователь явно указал страну, которой нет в справочнике
    country = merged_params.get("destination_country")
    if country:
        # Проверяем, есть ли страна в валидном списке
        if country not in VALID_COUNTRIES:
            # Страна не в нашем справочнике — не ищем
            state["search_params"] = merged_params
            state["intent"] = "invalid_country"
            state["invalid_country"] = country
            state["is_first_message"] = len(state["messages"]) <= 1 and not state.get("greeted", False)
            return state
    
    # ==================== SOCHI-TO-SOCHI DETECTION ====================
    # Если город вылета = город назначения — переключаем в hotel_only режим
    departure_city = merged_params.get("departure_city", "").lower().strip() if merged_params.get("departure_city") else ""
    dest_region = merged_params.get("destination_region", "").lower().strip() if merged_params.get("destination_region") else ""
    dest_resort = merged_params.get("destination_resort", "").lower().strip() if merged_params.get("destination_resort") else ""
    dest_country = merged_params.get("destination_country", "").lower().strip() if merged_params.get("destination_country") else ""
    
    if departure_city:
        # Проверяем совпадение по региону, курорту или стране (для внутренних поездок)
        is_local_travel = (
            (dest_region and departure_city in dest_region) or
            (dest_resort and departure_city in dest_resort) or
            (departure_city in dest_region if dest_region else False) or
            (departure_city in dest_resort if dest_resort else False) or
            # Точное совпадение (например, Сочи → Сочи)
            departure_city == dest_region or
            departure_city == dest_resort
        )
        
        if is_local_travel:
            logger.info(f"   🚗 LOCAL TRAVEL DETECTED: {departure_city} → {dest_region or dest_resort}. Switching to Hotel Only mode.")
            state["search_mode"] = "hotel_only"
            merged_params["departure_city"] = None  # Сбрасываем — не нужен для hotel_only
    
    # ==================== ЕСЛИ УКАЗАН ОТЕЛЬ — ПРОПУСКАЕМ ЗВЁЗДНОСТЬ ====================
    if merged_params.get("hotel_name"):
        # Не нужно спрашивать звёздность — отель конкретный
        merged_params["skip_quality_check"] = True
    
    # ==================== АНТИ-ЗАЦИКЛИВАНИЕ: Если stars/food_type обновлены — пропускаем ====================
    # КРИТИЧНО: Если пользователь ответил на вопрос о звёздах/питании — НЕ спрашиваем повторно!
    stars_updated = entities.get("stars_updated", False)
    food_type_updated = entities.get("food_type_updated", False)
    
    if stars_updated or food_type_updated:
        # Пользователь уже ответил — пропускаем quality_check
        merged_params["skip_quality_check"] = True
        state["quality_check_asked"] = True  # Помечаем что уже спрашивали
        state["clarification_asked"] = True  # Пользователь ответил конкретно
    
    # Проверка "мне всё равно" — может быть в любом сообщении
    # ВАЖНО: Не устанавливаем дефолтные stars/food_type при "мне всё равно"
    # Это позволит найти все доступные варианты
    if check_skip_quality_phrase(user_text):
        merged_params["skip_quality_check"] = True
        state["clarification_asked"] = True  # Пользователь дал понять что ему всё равно
        # НЕ устанавливаем stars и food_type — пусть поиск вернёт все варианты
    
    # Автоматический расчёт ночей
    if "date_from" in merged_params and "date_to" in merged_params:
        d_from = merged_params["date_from"]
        d_to = merged_params["date_to"]
        if isinstance(d_from, date) and isinstance(d_to, date):
            nights = (d_to - d_from).days
            if nights > 0:
                merged_params["nights"] = nights
    
    if "date_from" in merged_params and "nights" in merged_params and "date_to" not in merged_params:
        d_from = merged_params["date_from"]
        if isinstance(d_from, date):
            merged_params["date_to"] = d_from + timedelta(days=merged_params["nights"])
    
    # Обновляем состояние
    missing = get_missing_required_params(merged_params)
    cascade_stage = get_cascade_stage(merged_params, state.get("search_mode", "package"))
    
    # Определяем, первое ли это сообщение (для приветствия)
    is_first = len(state["messages"]) <= 1 and not state.get("greeted", False)
    
    # ==================== ВАЖНО: ЕСЛИ ВСЕ ПАРАМЕТРЫ СОБРАНЫ — ИЩЕМ ====================
    # Если cascade_stage == 6, значит все параметры собраны, принудительно переходим к поиску
    # Это гарантирует, что бот не будет "болтать" вместо поиска
    if cascade_stage == 6 and intent not in ("booking", "phone_provided", "group_booking", "invalid_country"):
        intent = "search_tour"
    
    state["search_params"] = merged_params
    state["missing_info"] = missing
    state["intent"] = intent
    state["cascade_stage"] = cascade_stage
    state["is_first_message"] = is_first
    
    return state


async def faq_handler(state: AgentState) -> AgentState:
    """Обработка FAQ."""
    intent = state.get("intent", "")
    
    # ==================== АНТИ-ПОВТОРНОЕ ПРИВЕТСТВИЕ ====================
    # Если это "greeting" intent в середине диалога — отвечаем кратко
    if intent == "greeting":
        messages_count = len(state.get("messages", []))
        already_greeted = state.get("greeted", False)
        
        if already_greeted or messages_count > 2:
            # Уже здоровались — отвечаем кратко
            state["response"] = "Чем могу помочь?"
        else:
            # Первое приветствие — только в первой сессии
            # НЕ используем "Здравствуйте" — бот должен сразу к делу
            state["response"] = "В какую страну планируете поездку?"
            state["greeted"] = True
        return state
    
    if intent in FAQ_RESPONSES:
        state["response"] = FAQ_RESPONSES[intent]
    else:
        state["response"] = "К сожалению, не нашёл ответ. Свяжитесь с менеджером."
    
    return state


async def invalid_country_handler(state: AgentState) -> AgentState:
    """Обработка невалидной страны (Anti-Hallucination)."""
    invalid_country = state.get("invalid_country", "это направление")
    
    alternatives = ", ".join(POPULAR_ALTERNATIVES)
    
    state["response"] = (
        f"К сожалению, мы пока не продаём туры в {invalid_country}.\n\n"
        f"Но я могу предложить отличные альтернативы:\n"
        f"• {alternatives}\n\n"
        f"Какое направление Вас интересует?"
    )
    
    # Очищаем невалидную страну из параметров
    if state.get("search_params"):
        state["search_params"].pop("destination_country", None)
    
    return state


async def child_ages_handler(state: AgentState) -> AgentState:
    """
    Обработчик для запроса возраста детей.
    
    КРИТИЧНО по ТЗ: Если пользователь упомянул детей, но не указал возраст,
    мы ОБЯЗАНЫ спросить — возраст влияет на цену тура!
    """
    params = state.get("search_params", {})
    children_count = state.get("missing_child_ages", 1)
    
    # Формируем контекст для пользователя
    context_parts = []
    if params.get("destination_country"):
        context_parts.append(params["destination_country"])
    if params.get("departure_city"):
        context_parts.append(f"из {params['departure_city']}")
    if params.get("adults"):
        context_parts.append(f"{params['adults']} взр")
    
    context = ", ".join(context_parts) if context_parts else "ваш запрос"
    
    # Формируем вопрос
    if children_count == 1:
        question = "Укажите, пожалуйста, возраст ребёнка (это важно для расчёта цены)."
    else:
        question = f"Укажите, пожалуйста, возраст всех {children_count} детей (это важно для расчёта цены)."
    
    # БЕЗ "Принято:" — сразу вопрос
    state["response"] = question
    state["last_question_type"] = "children_ages"
    
    return state


async def general_chat_handler(state: AgentState) -> AgentState:
    """Обработка общих вопросов."""
    if not state["messages"]:
        return state
    
    user_message = state["messages"][-1]["content"]
    params = state.get("search_params", {})
    
    if settings.YANDEX_GPT_ENABLED:
        from app.agent.llm import llm_client
        
        try:
            response = await llm_client.generate_conversational_response(
                user_message=user_message,
                search_params=params,
                conversation_history=state["messages"]
            )
            if response:
                state["response"] = response
                return state
        except Exception as e:
            print(f"General chat LLM error: {e}")
    
    state["response"] = generate_fallback_response(user_message, params)
    return state


def generate_fallback_response(user_message: str, params: dict) -> str:
    """Генерирует ответ без LLM."""
    text_lower = user_message.lower()
    
    country = None
    for key in DESTINATIONS_KNOWLEDGE.keys():
        if key in text_lower:
            country = key
            break
    
    if any(word in text_lower for word in ["погода", "температур", "климат"]):
        if country and country in DESTINATIONS_KNOWLEDGE:
            info = DESTINATIONS_KNOWLEDGE[country]
            return f"В {country.title()} сезон: {info.get('сезон', 'уточняйте')}. Планируете поездку туда?"
        return "Погода зависит от страны. Турция — май-октябрь, Египет — круглый год, ОАЭ — октябрь-апрель. Куда присматриваетесь?"
    
    if any(word in text_lower for word in ["отель для дет", "с детьми", "семейн"]):
        return "Для семей с детьми рекомендую Турцию — Белек, Сиде. Короткий перелёт, всё включено, аквапарки. Рассматриваете это направление?"
    
    if any(word in text_lower for word in ["лучше", "или", "выбрать"]):
        return "Турция — короткий перелёт, всё включено. Египет — круглый год, дешевле. ОАЭ — роскошь, зимой. Что для Вас важнее?"
    
    return "С удовольствием помогу. В какую страну планируете поездку?"


async def quality_check_handler(state: AgentState) -> AgentState:
    """Вопрос о качестве (звёзды/питание)."""
    params = state.get("search_params", {})
    
    # БЕЗ "Принято:" — сразу вопрос
    # Если отель известен — пропускаем (VIP проход)
    if params.get("hotel_name"):
        state["skip_quality_check"] = True
        state["cascade_stage"] = 6
        return state
    
    state["response"] = "Какой уровень отеля — 5 звёзд всё включено или рассмотрим варианты?"
    state["quality_check_asked"] = True
    
    return state


async def tour_searcher(state: AgentState) -> AgentState:
    """Поиск туров."""
    params = state["search_params"]
    
    # ==================== STRICT QUALIFICATION GUARDRAILS ====================
    # КРИТИЧНО: НЕ ЗАПУСКАЕМ ПОИСК без обязательных параметров!
    
    # ==================== ГОРЯЩИЕ ТУРЫ: ТОЖЕ БЕЗ ДЕФОЛТОВ! ====================
    # Даже для горящих туров агент ОБЯЗАН спрашивать состав и длительность
    is_hot_tours = state.get("intent") == "hot_tours"
    
    # НЕТ ДЕФОЛТОВ! Даже для горящих туров проверяем ВСЕ параметры.
    if not is_hot_tours:
        # Для обычного поиска — СТРОГАЯ проверка
        
        # 1. Город вылета — ОБЯЗАТЕЛЬНО (кроме режима hotel_only!)
        search_mode = state.get("search_mode", "package")
        # Блокируем, только если это НЕ hotel_only и города нет
        if search_mode != "hotel_only" and not params.get("departure_city"):
            state["missing_info"] = ["departure_city"]
            return state
        
        # 2. Дата вылета — ОБЯЗАТЕЛЬНО
        if not params.get("date_from"):
            state["missing_info"] = ["date_from"]
            return state
        
        # 3. Состав (adults) — ОБЯЗАТЕЛЬНО и ЯВНО указан!
        # КРИТИЧНО: НЕ подставляем adults=1 молча! Агент ОБЯЗАН спросить!
        adults_explicit = params.get("adults_explicit", False)
        adults = params.get("adults")
        
        if not adults or not adults_explicit:
            # Агент ОБЯЗАН спросить: "Сколько человек полетит?"
            state["missing_info"] = ["adults"]
            state["intent"] = "ask_pax"  # Специальный intent для уточнения состава
            return state
        
        # 4. Длительность (nights) — ОБЯЗАТЕЛЬНО!
        if not params.get("nights"):
            state["missing_info"] = ["nights"]
            return state
        
        # 5. Страна назначения — ОБЯЗАТЕЛЬНО
        if not params.get("destination_country"):
            state["missing_info"] = ["destination_country"]
            return state
    
    if state["missing_info"]:
        return state
    
    try:
        
        destination = Destination(
            country=params.get("destination_country"),
            region=params.get("destination_region"),
            resort=params.get("destination_resort"),
            city=params.get("destination_city")
        )
        
        original_date_from = params.get("date_from")
        nights = params.get("nights", 7)
        
        # ==================== УМНЫЙ ДИАПАЗОН ДАТ ====================
        # КРИТИЧНО: Если указана ТОЧНАЯ дата — используем узкое окно!
        # Точная дата: "15 февраля" → ±0-1 день
        # Размытая дата: "в середине февраля" → ±2 дня
        # После согласия пользователя: ±5 дней
        
        is_exact_date = params.get("is_exact_date", False)
        
        if state.get("flex_search"):
            # Пользователь согласился расширить поиск
            flex_days = 5
        elif is_exact_date:
            # STRICT DATE SEARCH: Если дата ТОЧНАЯ — ищем СТРОГО в этот день!
            # Пользователь сказал "15 февраля" → ищем только 15 февраля
            flex_days = 0
            logger.info(f"   📅 STRICT DATE: точная дата {original_date_from.strftime('%d.%m')}, flex_days=0")
        else:
            # Размытая дата ("в феврале", "на следующей неделе") — стандартное окно
            flex_days = state.get("flex_days", 2)
        
        # ==================== КРИТИЧНО: РАЗДЕЛЕНИЕ ДАТ И НОЧЕЙ ====================
        # datefrom/dateto в Tourvisor API — это диапазон дат ВЫЛЕТА
        # nightsfrom/nightsto — это количество ночей (передаётся отдельно!)
        # 
        # БЫЛО (ОШИБКА): date_to = original_date_from + flex_days + nights
        # Это приводило к тому, что при flex_days=5 и nights=5 → date_to на 10 дней вперёд
        # И SearchRequest вычислял nights = 15 вместо 5!
        #
        # ПРАВИЛЬНО: расширяем только диапазон дат вылета, ночи передаём отдельно
        date_from = original_date_from - timedelta(days=flex_days)
        date_to = original_date_from + timedelta(days=flex_days)  # БЕЗ nights!
        
        # Сохраняем оригинальную дату для сообщения
        state["original_date_from"] = original_date_from
        
        # Логируем для отладки
        logger.info(f"   📅 Диапазон дат: {date_from} - {date_to}, ночей: {nights}")
        
        # КРИТИЧНО: adults уже проверен выше — дефолт НЕ используем!
        # ==================== ГОРОД ВЫЛЕТА: HOTEL_ONLY НЕ ТРЕБУЕТ ====================
        departure_city = params.get("departure_city")
        search_mode = state.get("search_mode", "package")
        
        # Для hotel_only режима город вылета НЕ требуется!
        if search_mode == "hotel_only":
            departure_city = None  # Будет departure=0 в API
            logger.info("   🏨 Режим HOTEL_ONLY: город вылета не требуется")
        elif not departure_city:
            # Для обычных туров город обязателен
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: departure_city не указан!")
            state["missing_info"] = ["departure_city"]
            return state
        else:
            logger.info(f"   ✈️ Город вылета: {departure_city}")
        
        search_request = SearchRequest(
            adults=params.get("adults"),  # Без дефолта! Проверено выше.
            children=params.get("children", []),
            destination=destination,
            hotel_name=params.get("hotel_name"),
            stars=params.get("stars"),
            date_from=date_from,
            date_to=date_to,
            nights=nights,  # КРИТИЧНО: передаём явно, не вычисляем из дат!
            food_type=params.get("food_type"),
            departure_city=departure_city,  # СТРОГО без дефолта!
            # === НОВЫЕ ПАРАМЕТРЫ (GAP Analysis) ===
            services=params.get("services"),  # ID услуг отелей
            hotel_types=params.get("hotel_types"),  # Типы отелей (family, beach...)
            tour_type=params.get("tour_type"),  # Тип тура (1=пляжный, 2=горнолыжный...)
        )
        
        # Загружаем справочники если ещё не загружены
        await tourvisor_service.load_countries()
        await tourvisor_service.load_departures()
        
        if state["intent"] == "hot_tours":
            # Горящие туры через hottours.php
            departure_id = tourvisor_service.get_departure_id(
                params.get("departure_city", "Москва")
            ) or 1
            country_id = tourvisor_service.get_country_id(destination.country)
            
            tours = await tourvisor_service.get_hot_tours(
                departure_id=departure_id,
                country_id=country_id,
                limit=5
            )
            state["tour_offers"] = tours
        else:
            # ==================== СТРОГИЙ ПОИСК ПО ОТЕЛЮ ====================
            # Если hotel_name указан — ОБЯЗАТЕЛЬНО ищем через find_hotel_by_name
            hotel_name = params.get("hotel_name")
            hotel_ids = None
            is_strict = False
            
            # Сохраняем информацию о найденном отеле для Smart Alternatives
            found_hotel_info = None
            
            if hotel_name:
                # Ищем ID отеля в справочнике
                country_for_hotel = params.get("destination_country")
                hotels_found = await tourvisor_service.find_hotel_by_name(
                    query=hotel_name,
                    country=country_for_hotel
                )
                
                if hotels_found:
                    hotel_ids = [h.hotel_id for h in hotels_found[:3]]
                    is_strict = True
                    # Сохраняем инфо о первом отеле для Smart Alternatives
                    found_hotel_info = hotels_found[0]
                    state["found_hotel_name"] = found_hotel_info.name
                    state["found_hotel_stars"] = found_hotel_info.stars
                    # HotelInfo использует region_name, не region
                    state["found_hotel_region"] = getattr(found_hotel_info, 'region_name', '') or getattr(found_hotel_info, 'resort_name', '')
                else:
                    # ==================== FAIL-FAST: ОТЕЛЬ НЕ НАЙДЕН В СПРАВОЧНИКЕ ====================
                    state["tour_offers"] = []
                    state["hotel_not_found"] = True
                    state["response"] = (
                        f"К сожалению, я не нашёл отель «{hotel_name}» в базе Tourvisor.\n\n"
                        f"Уточните название или давайте посмотрим другие варианты в {country_for_hotel}."
                    )
                    return state
            
            # Определяем, горящий ли это тур
            is_hot_tour_search = (
                state.get("intent") == "hot_tours" or 
                params.get("is_hot_tour", False)
            )
            
            # Обычный асинхронный поиск через search.php
            result = await tourvisor_service.search_tours(
                search_request,
                is_strict_hotel_search=is_strict,
                hotel_ids=hotel_ids,
                is_hot_tour=is_hot_tour_search  # Расширенное окно для горящих!
            )
            
            # ==================== SMART RETRY FOR ZERO RESULTS ====================
            # Если strict date search вернул 0 результатов — автоматически расширяем диапазон
            if is_exact_date and (not result.found or not result.offers) and not is_strict:
                logger.info("   🔄 SMART RETRY: strict date вернул 0, расширяем до ±2 дней...")
                
                # Расширяем диапазон дат
                expanded_date_from = original_date_from - timedelta(days=2)
                expanded_date_to = original_date_from + timedelta(days=2)
                
                # Создаём новый запрос с расширенными датами
                retry_request = SearchRequest(
                    adults=search_request.adults,
                    children=search_request.children,
                    destination=search_request.destination,
                    hotel_name=search_request.hotel_name,
                    stars=search_request.stars,
                    date_from=expanded_date_from,
                    date_to=expanded_date_to,
                    nights=search_request.nights,
                    food_type=search_request.food_type,
                    departure_city=search_request.departure_city,
                    services=search_request.services,
                    hotel_types=search_request.hotel_types,
                    tour_type=search_request.tour_type,
                )
                
                retry_result = await tourvisor_service.search_tours(
                    retry_request,
                    is_strict_hotel_search=is_strict,
                    hotel_ids=hotel_ids,
                    is_hot_tour=is_hot_tour_search
                )
                
                if retry_result.found and retry_result.offers:
                    result = retry_result
                    state["date_warning"] = True  # Флаг для предупреждения в ответе
                    logger.info(f"   ✅ SMART RETRY успешен: найдено {len(result.offers)} туров с ±2 дней")
            
            # ⛔ ОБРАБОТКА: Отель не найден в базе туроператоров
            if result.reason == "hotel_not_found_in_db":
                hotel_name = params.get("hotel_name", "указанный отель")
                country = params.get("destination_country", "этом регионе")
                state["tour_offers"] = []
                state["hotel_not_found"] = True
                state["response"] = (
                    f"К сожалению, я не нашёл отель «{hotel_name}» в базе туроператоров в {country}.\n\n"
                    f"Возможные причины:\n"
                    f"• Отель не работает с туроператорами\n"
                    f"• Отель закрыт на эти даты\n"
                    f"• Название введено с ошибкой\n\n"
                    f"Попробуйте уточнить название или посмотреть другие отели в {country}."
                )
                return state
            
            # === СОХРАНЯЕМ ДАННЫЕ ДЛЯ ПАГИНАЦИИ (GAP Analysis) ===
            if result.search_id:
                state["last_search_id"] = result.search_id
                state["last_country_id"] = tourvisor_service.get_country_id(destination.country)
                state["current_page"] = 1
                state["has_more_results"] = result.total_found > 5  # Есть ли ещё туры
            
            # ==================== SMART ALTERNATIVES ====================
            # Если отель найден в справочнике, но туров нет — ищем альтернативы!
            if is_strict and found_hotel_info and (not result.found or not result.offers):
                # Туров в конкретный отель нет — ищем альтернативы
                hotel_stars = found_hotel_info.stars or 5
                # HotelInfo использует region_name, не region
                hotel_region = getattr(found_hotel_info, 'region_name', '') or getattr(found_hotel_info, 'resort_name', '')
                hotel_display_name = found_hotel_info.name
                
                # Создаём запрос для поиска альтернатив (по региону и звёздности)
                alt_search_request = SearchRequest(
                    adults=params.get("adults"),  # Без дефолта!
                    children=params.get("children", []),
                    destination=Destination(
                        country=params.get("destination_country"),
                        region=hotel_region  # Тот же регион
                    ),
                    stars=hotel_stars,  # Те же звёзды
                    date_from=date_from,
                    date_to=date_to,
                    food_type=params.get("food_type"),
                    departure_city=params.get("departure_city", "Москва")
                )
                
                # Поиск альтернатив (БЕЗ строгого фильтра по отелю)
                alt_result = await tourvisor_service.search_tours(
                    alt_search_request,
                    is_strict_hotel_search=False,
                    hotel_ids=None
                )
                
                if alt_result.found and alt_result.offers:
                    # Исключаем исходный отель из альтернатив
                    filtered_offers = [
                        offer for offer in alt_result.offers
                        if offer.hotel_name.lower() != hotel_display_name.lower()
                    ][:5]
                    
                    if filtered_offers:
                        state["tour_offers"] = filtered_offers
                        state["smart_alternatives"] = True
                        state["original_hotel_name"] = hotel_display_name
                        state["original_hotel_stars"] = hotel_stars
                        state["original_hotel_region"] = hotel_region or country_for_hotel
                    else:
                        # Альтернатив тоже нет
                        state["tour_offers"] = []
                        state["no_alternatives"] = True
                else:
                    # Альтернатив нет
                    state["tour_offers"] = []
                    state["no_alternatives"] = True
                    state["search_reason"] = result.reason
                    state["search_suggestion"] = result.suggestion
            else:
                state["tour_offers"] = result.offers if result.found else []
                
                if not result.found:
                    state["search_reason"] = result.reason
                    state["search_suggestion"] = result.suggestion
        
    except Exception as e:
        state["error"] = f"Ошибка поиска: {str(e)}"
        state["tour_offers"] = []
    
    return state


def generate_no_results_explanation(params: PartialSearchParams, state: AgentState = None) -> tuple[str, bool, str]:
    """
    Генерирует умное объяснение, почему нет результатов.
    Учитывает количество попыток для предотвращения зацикливания.
    
    GAP Analysis: Добавлен Smart Fallback по типу питания (AI -> HB).
    
    Returns:
        tuple: (текст ответа, нужно ли ждать согласия, тип предложенного действия)
    """
    country = params.get("destination_country", "")
    date_from = params.get("date_from")
    departure_city = params.get("departure_city", "")
    food_type = params.get("food_type")
    stars = params.get("stars")
    
    # Получаем счётчик попыток и диапазон дат из state
    search_attempts = state.get("search_attempts", 0) if state else 0
    flex_days = state.get("flex_days", 2) if state else 2
    flex_search_done = state.get("flex_search", False) if state else False
    offered_alt_departure = state.get("offered_alt_departure", False) if state else False
    offered_alt_food = state.get("offered_alt_food", False) if state else False
    offered_lower_stars = state.get("offered_lower_stars", False) if state else False
    
    if date_from:
        date_str = date_from.strftime("%d.%m")
        
        # Первая попытка — предлагаем расширить диапазон дат
        if not flex_search_done and search_attempts <= 1:
            response = f"На {date_str} вылетов из {departure_city} нет. Посмотреть соседние даты?"
            return (response, True, "flex_dates")
        
        # === SMART FALLBACK: ПО ТИПУ ПИТАНИЯ (GAP Analysis) ===
        # Если было указано AI/UAI — предлагаем HB или FB
        if food_type and food_type.value in ("AI", "UAI") and not offered_alt_food:
            food_name = "Всё включено" if food_type.value == "AI" else "Ультра Всё включено"
            response = (
                f"С питанием «{food_name}» вариантов нет.\n"
                f"Посмотреть отели с «Полупансион» (HB: завтрак + ужин)?"
            )
            return (response, True, "alt_food")
        
        # === SMART FALLBACK: ПО ЗВЁЗДНОСТИ ===
        # Если было указано 5* — предлагаем 4*
        if stars and stars >= 5 and not offered_lower_stars:
            response = (
                f"Отелей {stars}⭐ на эти даты нет.\n"
                f"Посмотреть 4⭐ отели?"
            )
            return (response, True, "lower_stars")
        
        # Вторая попытка (после расширения дат) — если город не Москва, предлагаем Москву
        if flex_search_done and departure_city.lower() != "москва" and not offered_alt_departure:
            # Рассчитываем диапазон, который проверили
            from_date = (date_from - timedelta(days=flex_days)).strftime("%d.%m")
            to_date = (date_from + timedelta(days=flex_days)).strftime("%d.%m")
            response = (
                f"Я проверил даты с {from_date} по {to_date}, но рейсов из {departure_city} нет.\n"
                f"Попробовать вылет из Москвы?"
            )
            return (response, True, "alt_departure")
        
        # Финальное сообщение — не задаём вопрос, предотвращаем цикл
        from_date = (date_from - timedelta(days=flex_days)).strftime("%d.%m")
        to_date = (date_from + timedelta(days=flex_days)).strftime("%d.%m")
        response = (
            f"Я проверил все варианты с {from_date} по {to_date}.\n"
            f"К сожалению, рейсов нет. Попробуйте сдвинуть отпуск на неделю или выбрать другое направление."
        )
        return (response, False, None)  # НЕ ждём согласия — предотвращаем цикл
    
    # Дефолтный ответ без зацикливания
    return (
        "По запросу туров не найдено. Попробуйте изменить даты или направление.",
        False,
        None
    )


async def responder(state: AgentState) -> AgentState:
    """
    Формирование ответа.
    
    Ключевые правила:
    - Приветствие только один раз
    - Каскад вопросов в правильном порядке
    - Умное объяснение "нет результатов"
    """
    # КРИТИЧНО: Если ответ уже был установлен (например, hotel_not_found) — не перезаписываем
    if state.get("hotel_not_found") and state.get("response"):
        return state
    
    # Ошибка
    if state.get("error"):
        state["response"] = f"Произошла ошибка: {state['error']}. Попробуйте ещё раз."
        return state
    
    params = state["search_params"]
    cascade_stage = get_cascade_stage(params, state.get("search_mode", "package"))
    is_first = state.get("is_first_message", False) and not state.get("greeted", False)
    
    # Найденные туры — новый формат с подтверждением
    if state["tour_offers"]:
        offers = state["tour_offers"]
        country = params.get("destination_country", "")
        hotel_name = params.get("hotel_name", "")
        date_from = params.get("date_from")
        
        # Формируем краткий контекст для заголовка
        date_str = date_from.strftime("%d.%m") if date_from else ""
        
        # ==================== SMART ALTERNATIVES RESPONSE ====================
        if state.get("smart_alternatives"):
            # Это альтернативы, а не исходный отель!
            original_hotel = state.get("original_hotel_name", hotel_name)
            original_stars = state.get("original_hotel_stars", 5)
            original_region = state.get("original_hotel_region", country)
            
            header = (
                f"К сожалению, в {original_hotel} на эти даты туров нет (места закончились).\n\n"
                f"Но я подобрал похожие варианты {original_stars}★ в регионе {original_region}:"
            )
        else:
            # Обычная выдача
            if hotel_name:
                header = f"Вот туры в {hotel_name}"
            else:
                header = f"Вот варианты в {country}"
            
            if date_str:
                header += f" на {date_str}"
            header += ":"
        
        # ==================== DATE WARNING (Smart Retry) ====================
        # Если strict date search вернул 0 и мы расширили диапазон — предупреждаем пользователя
        date_warning = ""
        if state.get("date_warning"):
            original_date = state.get("original_date_from")
            if original_date:
                date_warning = f"\n⚠️ На точную дату {original_date.strftime('%d.%m')} рейсов не найдено, показываю ближайшие варианты (±2 дня).\n"
            else:
                date_warning = "\n⚠️ На указанную точную дату рейсов не найдено, показываю ближайшие варианты (±2 дня).\n"
            # Сбрасываем флаг
            state["date_warning"] = False
        
        # Добавляем предупреждение о сезоне (мягкое, одной фразой)
        season_warning = ""
        if date_from and country and not state.get("smart_alternatives"):
            month = date_from.month
            off_season, _ = is_off_season(country, month)
            if off_season and country == "Турция":
                season_warning = "\n(Обратите внимание: в этот период море прохладное для купания.)"
        
        state["response"] = header + date_warning + season_warning
        # Сбрасываем флаги ожидания
        state["awaiting_agreement"] = False
        state["pending_action"] = None
        return state
    
    # КАСКАД ВОПРОСОВ (строгий порядок)
    
    # ==================== ФОРМИРОВАНИЕ КОНТЕКСТА ====================
    # Собираем что УЖЕ знаем для подтверждения в ответе
    hotel_name = params.get("hotel_name", "")
    country = params.get("destination_country", "")
    departure = params.get("departure_city", "")
    date_from = params.get("date_from")
    date_str = date_from.strftime("%d.%m") if date_from else ""
    adults = params.get("adults", 0)
    
    # Формируем подтверждение понятого
    confirmation_parts = []
    if hotel_name:
        confirmation_parts.append(f"отель {hotel_name}")
    if country and not hotel_name:
        confirmation_parts.append(country)
    if date_str:
        confirmation_parts.append(f"на {date_str}")
    if adults:
        confirmation_parts.append(f"на {adults} чел.")
    
    confirmation = ", ".join(confirmation_parts) if confirmation_parts else ""
    
    # Этап 1: нужна страна
    if cascade_stage == 1:
        # ==================== АНТИ-ПОВТОРНОЕ ПРИВЕТСТВИЕ ====================
        # КРИТИЧНО: Если в истории > 2 сообщений — НЕ используем стартовое приветствие!
        messages_count = len(state.get("messages", []))
        already_greeted = state.get("greeted", False)
        
        if is_first and not already_greeted and messages_count <= 2:
            # Первое сообщение — сразу к делу, без "Здравствуйте"
            state["response"] = "В какую страну планируете поездку?"
            state["greeted"] = True
        else:
            # В середине диалога — кратко и по делу
            state["response"] = "В какую страну планируете поездку?"
        return state
    
    # Этап 2: нужен город вылета — кратко и по делу
    if cascade_stage == 2:
        state["response"] = "Из какого города вылет?"
        return state
    
    # Этап 3: нужны даты — кратко и по делу
    if cascade_stage == 3:
        state["response"] = "Когда планируете вылет?"
        return state
    
    # --- ЭТАП 4: HARD VALIDATION (Критические параметры) ---
    # Без этих данных поиск технически невозможен или даст неверную цену.
    # Это "Жесткий барьер" — флаги типа clarification_asked здесь НЕ работают!
    if cascade_stage == 4:
        adults_explicit = params.get("adults_explicit", False)
        has_adults = params.get("adults") and adults_explicit
        has_nights = params.get("nights")
        
        # ==================== 1. ПРОВЕРКА НАПРАВЛЕНИЯ (RIXOS FIX) ====================
        # Если отель указан → ПРОПУСКАЕМ вопрос о стране (страну подтянем из поиска)
        if not params.get("destination_country") and not params.get("hotel_name"):
            state["response"] = "В какую страну или город вы планируете поездку?"
            state["last_question_type"] = "destination"
            return state
        
        # ==================== 2. ПРОВЕРКА ДАТ ====================
        if not params.get("date_from"):
            # Если есть отель — VIP формулировка
            if hotel_name:
                state["response"] = f"На какие даты смотрим {hotel_name}?"
            else:
                state["response"] = "На какие даты планируете вылет?"
            state["last_question_type"] = "dates"
            return state
        
        # ==================== 3. ПРОВЕРКА НОЧЕЙ ====================
        if not has_nights:
            state["response"] = "На сколько ночей планируете поездку?"
            state["last_question_type"] = "nights"
            return state
        
        # ==================== 4. ПРОВЕРКА СОСТАВА (CHILDREN FIX) ====================
        # КРИТИЧНО: Нельзя искать, не зная ПОЛНЫЙ состав!
        children_ages = params.get("children", [])  # Список возрастов
        children_mentioned = params.get("children_mentioned")  # None = мы не знаем, есть ли дети
        children_count_mentioned = params.get("children_count_mentioned", 0)
        
        # Вариант A: adults не указан явно → спрашиваем полный состав
        if not has_adults:
            state["response"] = "Сколько человек поедет? Укажите взрослых и детей (если есть — с возрастом)."
            state["last_question_type"] = "adults"
            return state
        
        # Вариант B: adults указан, но мы НЕ ЗНАЕМ про детей (children_mentioned is None)
        # И пользователь не сказал явно "один" или "без детей"
        no_children_phrases = params.get("no_children_explicit", False)  # "без детей", "только взрослые"
        if not no_children_phrases and children_mentioned is None and not children_ages:
            adults = params.get("adults", 0)
            if adults == 1:
                # "я один" — вероятно без детей, пропускаем вопрос
                pass
            else:
                # 2+ взрослых — возможно семья с детьми
                state["response"] = "Поедут ли с вами дети? Если да — укажите их возраст."
                state["last_question_type"] = "children_check"
                return state
        
        # ==================== 5. ПРОВЕРКА ДЕТЕЙ БЕЗ ВОЗРАСТА (КРИТИЧНО ПО ТЗ!) ====================
        # Если бот понял, что есть дети, но не знает возраст — СТОП.
        if children_mentioned and not children_ages:
            if children_count_mentioned == 1:
                state["response"] = "Укажите, пожалуйста, возраст ребёнка (это важно для расчёта цены)."
            elif children_count_mentioned > 1:
                state["response"] = f"Укажите, пожалуйста, возраст всех {children_count_mentioned} детей (это важно для расчёта цены)."
            else:
                state["response"] = "Укажите, пожалуйста, возраст детей (это важно для расчёта цены)."
            state["last_question_type"] = "children_ages"
            return state
        
        # Если количество возрастов меньше чем упомянуто детей
        if children_count_mentioned > len(children_ages):
            missing = children_count_mentioned - len(children_ages)
            state["response"] = f"Вы упомянули {children_count_mentioned} детей, но указали возраст только для {len(children_ages)}. Укажите возраст остальных."
            state["last_question_type"] = "children_ages"
            return state
        
        # ==================== ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ====================
        # Переход к Soft Clarification (Stage 5)
        logger.info("   ✅ Hard Validation passed. Moving to Stage 5.")
        state["cascade_stage"] = 5
        # НЕ возвращаем — код продолжит выполнение и попадёт в блок cascade_stage == 5
    
    # Этап 5: нужны детали (SOFT CLARIFICATION)
    # ЛОГИКА:
    # - Если отель известен → пропускаем (ищем)
    # - Если clarification_asked == False → спрашиваем про звёзды/питание
    # - Если clarification_asked == True → клиенту всё равно, ищем как есть
    if cascade_stage == 5:
        # Если отель уже известен — НЕ спрашиваем звёздность!
        if hotel_name:
            state["cascade_stage"] = 6
            # Не возвращаемся — продолжаем к поиску
        
        # Если уже спрашивали и клиент не ответил конкретно — значит всё равно
        elif state.get("clarification_asked", False):
            logger.info("   ✅ Soft Clarification: клиенту всё равно, ищем без фильтров")
            state["cascade_stage"] = 6
            state["skip_quality_check"] = True
            # Не возвращаемся — продолжаем к поиску
        
        # Первый раз спрашиваем про качество — БЕЗ "Принято:"
        else:
            state["response"] = "Какой уровень отеля и питание? (например: 5 звёзд, всё включено)"
            state["clarification_asked"] = True
            state["quality_check_asked"] = True
            state["last_question_type"] = "stars"
            return state
    
    # Этап 6 (cascade_stage == 6): всё собрано, но туров нет
    # Это значит поиск был выполнен, но вернул 0 результатов
    
    # Увеличиваем счётчик попыток
    state["search_attempts"] = state.get("search_attempts", 0) + 1
    
    # ==================== ЧЕСТНЫЙ ОТВЕТ: НЕТ ТУРОВ С ФИЛЬТРАМИ ====================
    # Если поиск вернул reason="no_tours_with_filters" — предлагаем альтернативы
    search_reason = state.get("search_reason")
    
    if search_reason == "no_tours_with_filters":
        stars = params.get("stars")
        food = params.get("food_type")
        country = params.get("destination_country", "")
        
        # Формируем ЧЕСТНОЕ сообщение с предложением
        if stars:
            alt_stars = stars - 1 if stars > 3 else None
            if alt_stars:
                state["response"] = (
                    f"К сожалению, отелей {stars}★ на эти даты в {country} не найдено.\n\n"
                    f"Посмотреть варианты {alt_stars}★ или изменить даты?"
                )
                state["awaiting_agreement"] = True
                state["pending_action"] = "lower_stars"
                state["alt_stars"] = alt_stars
            else:
                state["response"] = (
                    f"К сожалению, туров на эти даты в {country} не найдено.\n"
                    f"Попробуйте изменить даты или город вылета."
                )
        else:
            state["response"] = (
                f"К сожалению, туров в {country} на указанные даты не найдено.\n"
                f"Попробуйте изменить даты или город вылета."
            )
        return state
    
    response_text, awaiting, action = generate_no_results_explanation(params, state)
    state["response"] = response_text
    state["awaiting_agreement"] = awaiting
    state["pending_action"] = action
    
    # Помечаем какой тип альтернативы предложили
    if action == "alt_departure":
        state["offered_alt_departure"] = True
    elif action == "alt_food":
        state["offered_alt_food"] = True
    elif action == "lower_stars":
        state["offered_lower_stars"] = True
    
    return state


async def booking_handler(state: AgentState) -> AgentState:
    """Обработка бронирования."""
    intent = state.get("intent", "")
    user_text = state["messages"][-1]["content"] if state["messages"] else ""
    
    if intent == "phone_provided":
        phone = detect_phone_number(user_text)
        if phone:
            state["customer_phone"] = phone
            state["awaiting_phone"] = False
            
            from app.services.crm import save_lead
            
            params = state.get("search_params", {})
            description = format_context(params)
            
            # Добавляем пометку для групповых заявок
            if state.get("is_group_request"):
                group_size = state.get("group_size", 0)
                description = f"[GROUP REQUEST > 6 PAX ({group_size} чел.)] " + description
            
            try:
                await save_lead(
                    name=state.get("customer_name") or "Не указано",
                    phone=phone,
                    search_params=description,
                    tour_offer_id=state.get("selected_tour_id")
                )
                
                if state.get("is_group_request"):
                    state["response"] = (
                        f"Спасибо! Групповая заявка принята.\n\n"
                        f"Телефон: {phone}\n"
                        f"Группа: {state.get('group_size', 0)} человек\n"
                        f"Направление: {format_context(params)}\n\n"
                        f"Менеджер группового бронирования свяжется с Вами в ближайшее время "
                        f"для расчёта специальных условий."
                    )
                else:
                    state["response"] = (
                        f"Спасибо! Заявка принята.\n\n"
                        f"Телефон: {phone}\n"
                        f"Направление: {description}\n\n"
                        f"Менеджер свяжется с Вами в ближайшее время."
                    )
            except Exception as e:
                state["response"] = f"Ошибка: {str(e)}. Позвоните нам напрямую."
            
            return state
    
    # ==================== ГРУППОВАЯ ЗАЯВКА (>6 человек) ====================
    if intent == "group_booking":
        group_size = state.get("group_size", 7)
        params = state.get("search_params", {})
        context = format_context(params) if params else ""
        
        state["awaiting_phone"] = True
        state["response"] = (
            f"Для групп более 6 человек ({group_size} чел.) у нас действуют специальные условия и скидки.\n\n"
            f"Чтобы я мог рассчитать точную стоимость, давайте я передам заявку менеджеру группового бронирования.\n\n"
            f"Напишите Ваш номер телефона, и мы свяжемся с Вами."
        )
        return state
    
    if intent == "booking":
        state["awaiting_phone"] = True
        
        if state.get("tour_offers"):
            state["response"] = "Отлично! Для оформления заявки напишите Ваш номер телефона."
        else:
            state["response"] = "Хорошо. Напишите Ваш номер телефона, и менеджер свяжется с Вами."
        
        return state
    
    return state


async def continue_search_handler(state: AgentState) -> AgentState:
    """
    Обработчик углублённого поиска: continue для получения большего количества туров.
    
    GAP Analysis: Реализация continue для углублённого поиска.
    """
    search_id = state.get("last_search_id")
    country_id = state.get("last_country_id")
    
    # Проверяем, есть ли данные для продолжения поиска
    if not search_id:
        state["response"] = (
            "Сначала нужно выполнить поиск туров. "
            "Куда бы вы хотели поехать?"
        )
        return state
    
    try:
        offers, has_more = await tourvisor_service.continue_search(
            request_id=search_id,
            country_id=country_id or 1
        )
        
        if offers:
            state["tour_offers"] = offers
            state["has_more_results"] = has_more
            
            # Формируем ответ
            response_lines = [f"🔄 **Углублённый поиск** — найдено ещё {len(offers)} вариантов:\n"]
            
            for i, offer in enumerate(offers, 1):
                price_info = f"{offer.price_value:,} ₽".replace(",", " ") if offer.price_value else offer.price
                response_lines.append(
                    f"**{i}. {offer.hotel_name}** ({offer.stars}⭐)\n"
                    f"   📍 {offer.location}\n"
                    f"   🍽️ {offer.food_type_display}\n"
                    f"   📅 {offer.date_start} — {offer.nights} ночей\n"
                    f"   💰 **{price_info}**\n"
                )
            
            if has_more:
                response_lines.append("\n💡 Скажите «искать ещё» для продолжения поиска.")
            
            state["response"] = "\n".join(response_lines)
        else:
            state["has_more_results"] = False
            state["response"] = (
                "Все доступные туроператоры уже опрошены, новых предложений нет.\n\n"
                "Хотите изменить параметры поиска?"
            )
    except Exception as e:
        logger.error(f"Ошибка continue search: {e}")
        state["response"] = (
            "Не удалось продолжить поиск. "
            "Попробуйте ещё раз или скорректируйте параметры."
        )
    
    return state


async def more_tours_handler(state: AgentState) -> AgentState:
    """
    Обработчик пагинации: загрузка следующей страницы результатов.
    
    GAP Analysis: Реализация кнопки "Ещё туры" (page=2, page=3...)
    """
    search_id = state.get("last_search_id")
    country_id = state.get("last_country_id")
    current_page = state.get("current_page", 1)
    
    # Проверяем, есть ли данные для пагинации
    if not search_id:
        state["response"] = (
            "К сожалению, данные предыдущего поиска устарели. "
            "Давайте повторим поиск — какое направление вас интересует?"
        )
        return state
    
    # Загружаем следующую страницу
    next_page = current_page + 1
    
    try:
        offers = await tourvisor_service.fetch_more_results(
            request_id=search_id,
            country_id=country_id or 1,
            page=next_page,
            onpage=5
        )
        
        if offers:
            state["tour_offers"] = offers
            state["current_page"] = next_page
            state["has_more_results"] = len(offers) >= 5
            
            # Формируем ответ
            response_lines = [f"📄 **Страница {next_page}** — ещё {len(offers)} вариантов:\n"]
            
            for i, offer in enumerate(offers, 1):
                price_info = f"{offer.price_value:,} ₽".replace(",", " ") if offer.price_value else offer.price
                response_lines.append(
                    f"**{i}. {offer.hotel_name}** ({offer.stars}⭐)\n"
                    f"   📍 {offer.location}\n"
                    f"   🍽️ {offer.food_type_display}\n"
                    f"   📅 {offer.date_start} — {offer.nights} ночей\n"
                    f"   💰 **{price_info}**\n"
                )
            
            if state.get("has_more_results"):
                response_lines.append("\n💡 Скажите «ещё туры» для загрузки следующей страницы.")
            
            state["response"] = "\n".join(response_lines)
        else:
            state["has_more_results"] = False
            state["response"] = (
                "Это были все доступные туры по вашему запросу.\n\n"
                "Хотите изменить параметры поиска или посмотреть другие направления?"
            )
    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}")
        state["response"] = (
            "Не удалось загрузить дополнительные туры. "
            "Попробуйте ещё раз или скорректируйте параметры поиска."
        )
    
    return state


async def child_ages_handler(state: AgentState) -> AgentState:
    """
    Обработчик запроса возраста детей.
    КРИТИЧНО: Поиск невозможен без возраста каждого ребёнка.
    """
    missing_count = state.get("missing_child_ages", 1)
    params = state.get("search_params", {})
    
    # Формируем вопрос в зависимости от количества детей
    if missing_count == 1:
        question = "Сколько лет ребёнку? Это важно для точного расчёта цены."
    else:
        question = f"Укажите возраст каждого ребёнка ({missing_count} чел.). Это важно для расчёта цены."
    
    # Если есть контекст — добавляем
    country = params.get("destination_country")
    if country:
        question = f"{country} — отличный выбор для семейного отдыха! " + question
    
    state["response"] = question
    return state


def should_search(state: AgentState) -> str:
    """Определение следующего узла."""
    intent = state.get("intent", "search_tour")
    params = state.get("search_params", {})
    
    # ==================== КРИТИЧЕСКАЯ ПРОВЕРКА: ДЕТИ БЕЗ ВОЗРАСТА ====================
    if intent == "ask_child_ages":
        return "ask_child_ages"
    
    # ==================== ПАГИНАЦИЯ: ЕЩЁ ТУРЫ (GAP Analysis) ====================
    if intent == "more_tours":
        return "more_tours"
    
    # ==================== УГЛУБЛЁННЫЙ ПОИСК (GAP Analysis) ====================
    if intent == "continue_search":
        return "continue_search"
    
    # ==================== ГРУППОВАЯ ЗАЯВКА ====================
    if intent == "group_booking":
        return "booking"
    
    # ==================== НЕВАЛИДНАЯ СТРАНА ====================
    if intent == "invalid_country":
        return "invalid_country"
    
    if intent in ("booking", "phone_provided"):
        return "booking"
    
    if intent.startswith("faq_") or intent == "greeting":
        return "faq"
    
    if intent == "general_chat":
        return "general_chat"
    
    # Если intent явно "search_tour" и cascade_stage == 6 (установлено в input_analyzer)
    # Сразу переходим к поиску
    if intent == "search_tour" and state.get("cascade_stage") == 6:
        return "search"
    
    # Каскад (пересчитываем только если не было явного указания)
    cascade_stage = state.get("cascade_stage") or get_cascade_stage(params, state.get("search_mode", "package"))
    
    # Если не все базовые параметры (включая город вылета!) — спрашиваем
    if cascade_stage <= 4:
        return "ask"
    
    # Если нужны детали — quality_check (SOFT CLARIFICATION)
    # НО: Если отель известен, skip_quality_check или clarification_asked — пропускаем!
    if cascade_stage == 5:
        # Пропускаем если отель известен
        if params.get("hotel_name") or params.get("skip_quality_check"):
            return "search"
        
        # Если уже спрашивали — клиенту всё равно, ищем
        if state.get("clarification_asked"):
            return "search"
        
        # Если ещё не спрашивали — спрашиваем
        if not state.get("quality_check_asked"):
            return "quality_check"
    
    # Иначе — поиск
    return "search"

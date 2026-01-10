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
}

# Список валидных стран для проверки
VALID_COUNTRIES = set(COUNTRIES_MAP.values())

# Популярные альтернативы для предложения
POPULAR_ALTERNATIVES = ["Турция", "Египет", "ОАЭ", "Таиланд", "Мальдивы"]

# ==================== ИЗВЕСТНЫЕ ОТЕЛИ (для извлечения) ====================
# Формат: "основа": ("Название отеля", "Страна")
# Используем основу слова для поиска (для обработки русских падежей)

KNOWN_HOTELS_WITH_COUNTRY = {
    # Турция - Белек
    "rixos": ("Rixos", "Турция"), "риксос": ("Rixos", "Турция"),
    "rixos premium": ("Rixos Premium Belek", "Турция"), "риксос премиум": ("Rixos Premium Belek", "Турция"),
    "rixos sungate": ("Rixos Sungate", "Турция"), "риксос сангейт": ("Rixos Sungate", "Турция"),
    # Calista - добавляем разные падежи
    "calista": ("Calista Luxury Resort", "Турция"), 
    "калист": ("Calista Luxury Resort", "Турция"),  # основа для калиста/калисту/калисте
    "regnum": ("Regnum Carya", "Турция"), "регнум": ("Regnum Carya", "Турция"),
    "titanic": ("Titanic Mardan Palace", "Турция"), "титаник": ("Titanic Mardan Palace", "Турция"),
    "gloria serenity": ("Gloria Serenity Resort", "Турция"),
    "maxx royal": ("Maxx Royal Belek", "Турция"), "макс роял": ("Maxx Royal Belek", "Турция"),
    
    # Турция - другие курорты
    "orange county": ("Orange County Resort", "Турция"), "оранж каунти": ("Orange County Resort", "Турция"),
    "voyage belek": ("Voyage Belek", "Турция"), "вояж белек": ("Voyage Belek", "Турция"),
    "delphin": ("Delphin Hotel", "Турция"), "дельфин": ("Delphin Hotel", "Турция"),
    "barut": ("Barut Hotels", "Турция"), "барут": ("Barut Hotels", "Турция"),
    
    # Египет
    "steigenberger": ("Steigenberger", "Египет"), "штайгенбергер": ("Steigenberger", "Египет"),
    "rixos sharm": ("Rixos Sharm El Sheikh", "Египет"),
    "sunrise": ("Sunrise Hotels", "Египет"), "санрайз": ("Sunrise Hotels", "Египет"),
    "jaz": ("Jaz Hotels", "Египет"), "джаз": ("Jaz Hotels", "Египет"),
    
    # ОАЭ
    "atlantis": ("Atlantis The Palm", "ОАЭ"), "атлантис": ("Atlantis The Palm", "ОАЭ"),
    "jumeirah": ("Jumeirah Hotels", "ОАЭ"), "джумейр": ("Jumeirah Hotels", "ОАЭ"),  # основа
    "burj al arab": ("Burj Al Arab", "ОАЭ"), "бурдж аль араб": ("Burj Al Arab", "ОАЭ"),
}

# Простой маппинг для обратной совместимости
KNOWN_HOTELS = {k: v[0] for k, v in KNOWN_HOTELS_WITH_COUNTRY.items()}

RESORTS_MAP = {
    "белек": ("Турция", "Белек"), "кемер": ("Турция", "Кемер"),
    "анталья": ("Турция", "Анталья"), "анталия": ("Турция", "Анталья"),
    "сиде": ("Турция", "Сиде"), "алания": ("Турция", "Алания"),
    "бодрум": ("Турция", "Бодрум"), "мармарис": ("Турция", "Мармарис"),
    "шарм": ("Египет", "Шарм-эль-Шейх"), "шарм-эль-шейх": ("Египет", "Шарм-эль-Шейх"),
    "хургада": ("Египет", "Хургада"),
}

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
        entities["date_from"] = dates_found[0]
        # Помечаем, что дата ТОЧНАЯ (указан конкретный день)
        # Это влияет на ширину окна поиска
        entities["is_exact_date"] = True
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
    
    # 10. Название отеля (поиск по известным) + автоопределение страны
    for key, (hotel_name, hotel_country) in KNOWN_HOTELS_WITH_COUNTRY.items():
        if key in text_lower:
            entities["hotel_name"] = hotel_name
            # Автоматически определяем страну по отелю (если ещё не указана)
            if "destination_country" not in entities:
                entities["destination_country"] = hotel_country
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
                            llm_entities["date_from"] = date.fromisoformat(val)
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
                    else:
                        # КРИТИЧНО: если LLM нашёл adults — это явное указание!
                        llm_entities["adults_explicit"] = True
            
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
            cascade_stage = get_cascade_stage(current_params)
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
            cascade_stage = get_cascade_stage(current_params)
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
            
            missing = get_missing_required_params(current_params)
            cascade_stage = get_cascade_stage(current_params)
            state["missing_info"] = missing
            state["intent"] = "search_tour"
            state["cascade_stage"] = cascade_stage
            return state
    
    result = await extract_entities_with_llm(user_text, awaiting_phone)
    intent = result.get("intent", "search_tour")
    entities = result.get("entities", {})
    
    current_params = state["search_params"].copy() if state["search_params"] else {}
    
    # ==================== ПРИОРИТЕТ НОВЫХ ДАННЫХ ====================
    # Новые данные от пользователя ВСЕГДА перезаписывают старые
    date_changed = False
    for key, value in entities.items():
        if value is not None:
            # Особая обработка дат — новые даты ВСЕГДА заменяют старые
            if key in ("date_from", "date_to", "nights"):
                old_value = current_params.get(key)
                if old_value != value:
                    date_changed = True
                current_params[key] = value
            else:
                current_params[key] = value
    
    # ==================== СБРОС ФЛАГОВ ПРИ СМЕНЕ ДАТЫ ====================
    # Если пользователь сменил дату — сбрасываем флаги и начинаем новый поиск
    if date_changed:
        state["awaiting_agreement"] = False
        state["pending_action"] = None
        state["error"] = None
        state["flex_search"] = False
        state["flex_days"] = 2  # Базовый диапазон ±2 дня для новой даты
        state["search_attempts"] = 0
        state["offered_alt_departure"] = False
    
    # ==================== КРИТИЧЕСКАЯ ПРОВЕРКА: ДЕТИ БЕЗ ВОЗРАСТА ====================
    # Если упомянуты дети, но возраст НЕ указан — БЛОКИРУЕМ поиск и спрашиваем
    children_mentioned = entities.get("children_mentioned") or current_params.get("children_mentioned")
    children_count_mentioned = entities.get("children_count_mentioned") or current_params.get("children_count_mentioned", 0)
    existing_children_ages = current_params.get("children", [])
    
    if children_mentioned and not existing_children_ages:
        state["search_params"] = current_params
        state["intent"] = "ask_child_ages"
        state["missing_child_ages"] = children_count_mentioned or 1
        # Не продолжаем — нужен возраст детей
        return state
    
    # Если новые возрасты извлечены — сбрасываем флаг
    if entities.get("children") and len(entities["children"]) > 0:
        current_params["children_mentioned"] = False
        current_params["children_count_mentioned"] = 0
    
    # ==================== ПРОВЕРКА ГРУППЫ > 6 ЧЕЛОВЕК ====================
    total_people = current_params.get("adults", 0) + len(current_params.get("children", []))
    if total_people > 6:
        # Групповая заявка — эскалация на менеджера
        state["search_params"] = current_params
        state["intent"] = "group_booking"
        state["is_group_request"] = True
        state["group_size"] = total_people
        state["is_first_message"] = len(state["messages"]) <= 1 and not state.get("greeted", False)
        return state
    
    # ==================== ВАЛИДАЦИЯ СТРАНЫ (Anti-Hallucination) ====================
    # Проверяем только если пользователь явно указал страну, которой нет в справочнике
    country = current_params.get("destination_country")
    if country:
        # Проверяем, есть ли страна в валидном списке
        if country not in VALID_COUNTRIES:
            # Страна не в нашем справочнике — не ищем
            state["search_params"] = current_params
            state["intent"] = "invalid_country"
            state["invalid_country"] = country
            state["is_first_message"] = len(state["messages"]) <= 1 and not state.get("greeted", False)
            return state
    
    # ==================== ЕСЛИ УКАЗАН ОТЕЛЬ — ПРОПУСКАЕМ ЗВЁЗДНОСТЬ ====================
    if current_params.get("hotel_name"):
        # Не нужно спрашивать звёздность — отель конкретный
        current_params["skip_quality_check"] = True
    
    # ==================== АНТИ-ЗАЦИКЛИВАНИЕ: Если stars/food_type обновлены — пропускаем ====================
    # КРИТИЧНО: Если пользователь ответил на вопрос о звёздах/питании — НЕ спрашиваем повторно!
    stars_updated = entities.get("stars_updated", False)
    food_type_updated = entities.get("food_type_updated", False)
    
    if stars_updated or food_type_updated:
        # Пользователь уже ответил — пропускаем quality_check
        current_params["skip_quality_check"] = True
        state["quality_check_asked"] = True  # Помечаем что уже спрашивали
    
    # Проверка "мне всё равно" — может быть в любом сообщении
    # ВАЖНО: Не устанавливаем дефолтные stars/food_type при "мне всё равно"
    # Это позволит найти все доступные варианты
    if check_skip_quality_phrase(user_text):
        current_params["skip_quality_check"] = True
        # НЕ устанавливаем stars и food_type — пусть поиск вернёт все варианты
    
    # Автоматический расчёт ночей
    if "date_from" in current_params and "date_to" in current_params:
        d_from = current_params["date_from"]
        d_to = current_params["date_to"]
        if isinstance(d_from, date) and isinstance(d_to, date):
            nights = (d_to - d_from).days
            if nights > 0:
                current_params["nights"] = nights
    
    if "date_from" in current_params and "nights" in current_params and "date_to" not in current_params:
        d_from = current_params["date_from"]
        if isinstance(d_from, date):
            current_params["date_to"] = d_from + timedelta(days=current_params["nights"])
    
    # Обновляем состояние
    missing = get_missing_required_params(current_params)
    cascade_stage = get_cascade_stage(current_params)
    
    # Определяем, первое ли это сообщение (для приветствия)
    is_first = len(state["messages"]) <= 1 and not state.get("greeted", False)
    
    # ==================== ВАЖНО: ЕСЛИ ВСЕ ПАРАМЕТРЫ СОБРАНЫ — ИЩЕМ ====================
    # Если cascade_stage == 6, значит все параметры собраны, принудительно переходим к поиску
    # Это гарантирует, что бот не будет "болтать" вместо поиска
    if cascade_stage == 6 and intent not in ("booking", "phone_provided", "group_booking", "invalid_country"):
        intent = "search_tour"
    
    state["search_params"] = current_params
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
            # Первое приветствие
            state["response"] = "Здравствуйте! Я консультант турагентства МГП. Чем могу помочь?"
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
    context = format_context(params)
    
    response = f"Принято: {context}.\n\nКакой уровень отеля предпочитаете — 5 звёзд всё включено или рассмотрим варианты?"
    
    state["response"] = response
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
        
        # 1. Город вылета — ОБЯЗАТЕЛЬНО
        if not params.get("departure_city"):
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
            # КРИТИЧНО: Точная дата — БЕЗ разброса! (±0 дней)
            # Если пользователь сказал "15 февраля", ищем ТОЛЬКО 15 февраля
            flex_days = 0
        else:
            # Размытая дата — стандартное окно
            flex_days = state.get("flex_days", 2)
        
        # Для точных дат: ищем именно указанную дату + длительность
        # Для размытых: добавляем flex_days в обе стороны
        date_from = original_date_from - timedelta(days=flex_days)
        date_to = original_date_from + timedelta(days=flex_days + nights)
        
        # Сохраняем оригинальную дату для сообщения
        state["original_date_from"] = original_date_from
        
        # КРИТИЧНО: adults уже проверен выше — дефолт НЕ используем!
        # ==================== КРИТИЧНО: ГОРОД ВЫЛЕТА БЕЗ ДЕФОЛТА ====================
        # Город вылета СТРОГО из параметров, НЕ Москва по умолчанию!
        departure_city = params.get("departure_city")
        
        if not departure_city:
            # Это не должно произойти — проверка выше
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: departure_city не указан!")
            state["missing_info"] = ["departure_city"]
            return state
        
        # Логируем для отладки
        logger.info(f"   ✈️ Город вылета: {departure_city}")
        
        search_request = SearchRequest(
            adults=params.get("adults"),  # Без дефолта! Проверено выше.
            children=params.get("children", []),
            destination=destination,
            hotel_name=params.get("hotel_name"),
            stars=params.get("stars"),
            date_from=date_from,
            date_to=date_to,
            food_type=params.get("food_type"),
            departure_city=departure_city  # СТРОГО без дефолта!
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
    
    Returns:
        tuple: (текст ответа, нужно ли ждать согласия, тип предложенного действия)
    """
    country = params.get("destination_country", "")
    date_from = params.get("date_from")
    departure_city = params.get("departure_city", "")
    
    # Получаем счётчик попыток и диапазон дат из state
    search_attempts = state.get("search_attempts", 0) if state else 0
    flex_days = state.get("flex_days", 2) if state else 2
    flex_search_done = state.get("flex_search", False) if state else False
    offered_alt_departure = state.get("offered_alt_departure", False) if state else False
    
    if date_from:
        date_str = date_from.strftime("%d.%m")
        
        # Первая попытка — предлагаем расширить диапазон дат
        if not flex_search_done and search_attempts <= 1:
            response = f"На {date_str} вылетов из {departure_city} нет. Посмотреть соседние даты?"
            return (response, True, "flex_dates")
        
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
        
        # Третья попытка — финальное сообщение, не задаём вопрос
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
    cascade_stage = get_cascade_stage(params)
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
        
        # Добавляем предупреждение о сезоне (мягкое, одной фразой)
        season_warning = ""
        if date_from and country and not state.get("smart_alternatives"):
            month = date_from.month
            off_season, _ = is_off_season(country, month)
            if off_season and country == "Турция":
                season_warning = "\n(Обратите внимание: в этот период море прохладное для купания.)"
        
        state["response"] = header + season_warning
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
            state["response"] = "Здравствуйте! Я консультант турагентства МГП. В какую страну планируете поездку?"
            state["greeted"] = True
        else:
            # В середине диалога — кратко и по делу
            state["response"] = "В какую страну планируете поездку?"
        return state
    
    # Этап 2: нужен город вылета (ОБЯЗАТЕЛЬНО!)
    if cascade_stage == 2:
        # ВАЖНО: Подтверждаем отель если он упомянут!
        if hotel_name:
            state["response"] = f"Отличный выбор! Ищу туры именно в {hotel_name} ({country}). Из какого города планируете вылет?"
        else:
            state["response"] = f"{country} — отличный выбор. Из какого города планируете вылет?"
        return state
    
    # Этап 3: нужны даты
    if cascade_stage == 3:
        if hotel_name:
            state["response"] = f"Понял, {hotel_name}, вылет из {departure}. Когда планируете отпуск?"
        else:
            state["response"] = f"Понял, вылет из {departure}. Когда планируете отпуск?"
        return state
    
    # Этап 4: нужен состав (adults) И длительность (nights)
    # КРИТИЧНО: Агент ОБЯЗАН спросить состав, не подставляя дефолт!
    if cascade_stage == 4:
        adults_explicit = params.get("adults_explicit", False)
        has_adults = params.get("adults") and adults_explicit
        has_nights = params.get("nights")
        
        # ==================== КРИТИЧНО: СПРАШИВАЕМ СОСТАВ ====================
        # Если adults не указан — ОБЯЗАТЕЛЬНО спрашиваем!
        if not has_adults and not has_nights:
            # Оба параметра отсутствуют — спрашиваем ночи первыми
            question = "На сколько ночей планируете поездку?"
            state["last_question_type"] = "nights"  # Контекст для ответа "5"
        elif not has_adults:
            # КРИТИЧНО: Нет состава — агент ОБЯЗАН спросить!
            question = "Сколько человек полетит? Укажите количество взрослых и детей (с возрастом)."
            state["last_question_type"] = "adults"  # Контекст для ответа "2"
        elif not has_nights:
            question = "На сколько ночей планируете поездку?"
            state["last_question_type"] = "nights"  # Контекст для ответа "7"
        else:
            # Всё есть — переходим к следующему этапу (не должно сюда попасть)
            question = "Сколько человек и на сколько ночей?"
            state["last_question_type"] = "nights"
        
        if confirmation:
            state["response"] = f"Принято: {confirmation}. {question}"
        else:
            state["response"] = question
        return state
    
    # Этап 5: нужны детали (пропускаем если отель известен!)
    if cascade_stage == 5:
        # Если отель уже известен — НЕ спрашиваем звёздность!
        if hotel_name:
            # Принудительно переходим к поиску
            state["cascade_stage"] = 6
            # Не возвращаемся — продолжаем к поиску
        else:
            context = format_context(params)
            state["response"] = f"Понял: {context}.\n\nКакой уровень отеля — 5 звёзд всё включено или рассмотрим варианты?"
            state["quality_check_asked"] = True
            state["last_question_type"] = "stars"  # Контекст для ответа "5"
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
    
    # Если предлагаем альтернативный город — помечаем
    if action == "alt_departure":
        state["offered_alt_departure"] = True
    
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
    cascade_stage = state.get("cascade_stage") or get_cascade_stage(params)
    
    # Если не все базовые параметры (включая город вылета!) — спрашиваем
    if cascade_stage <= 4:
        return "ask"
    
    # Если нужны детали — quality_check
    # НО: Если отель уже известен или skip_quality_check — пропускаем!
    if cascade_stage == 5 and not state.get("quality_check_asked"):
        # Пропускаем quality_check если отель известен или явно указано skip
        if params.get("hotel_name") or params.get("skip_quality_check"):
            return "search"
        return "quality_check"
    
    # Иначе — поиск
    return "search"

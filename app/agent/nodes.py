"""
Узлы графа LangGraph для ИИ-ассистента МГП.

Реализует бизнес-логику из .cursorrules:
- Не спрашивать повторно известную информацию
- Автоматически вычислять ночи из дат
- Если указан отель — не спрашивать звёздность
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from app.agent.state import (
    AgentState,
    PartialSearchParams,
    Message,
    get_missing_required_params,
    CLARIFICATION_QUESTIONS,
    PARAM_NAMES_RU
)
from app.models.domain import (
    SearchRequest,
    Destination,
    TourOffer,
    FoodType
)
from app.services.tourvisor import tourvisor_service
from app.core.config import settings


# ==================== ENTITY EXTRACTION ====================

# Словарь стран и их вариантов написания (для fallback)
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

# Курорты по странам
RESORTS_MAP = {
    "белек": ("Турция", "Белек"), "кемер": ("Турция", "Кемер"),
    "анталья": ("Турция", "Анталья"), "анталия": ("Турция", "Анталья"),
    "сиде": ("Турция", "Сиде"), "алания": ("Турция", "Алания"),
    "бодрум": ("Турция", "Бодрум"), "мармарис": ("Турция", "Мармарис"),
    "шарм": ("Египет", "Шарм-эль-Шейх"), "шарм-эль-шейх": ("Египет", "Шарм-эль-Шейх"),
    "хургада": ("Египет", "Хургада"), "марса-алам": ("Египет", "Марса-Алам"),
    "джумейра": ("ОАЭ", "Джумейра"), "пальма": ("ОАЭ", "Пальма Джумейра"),
    "карон": ("Таиланд", "Карон"), "ката": ("Таиланд", "Ката"), "патонг": ("Таиланд", "Патонг"),
}

# Типы питания
FOOD_TYPE_MAP = {
    "всё включено": FoodType.AI, "все включено": FoodType.AI, "all inclusive": FoodType.AI, "ai": FoodType.AI,
    "ультра": FoodType.UAI, "ultra": FoodType.UAI, "uai": FoodType.UAI,
    "завтрак": FoodType.BB, "bb": FoodType.BB,
    "полупансион": FoodType.HB, "hb": FoodType.HB,
    "полный пансион": FoodType.FB, "fb": FoodType.FB,
    "без питания": FoodType.RO, "ro": FoodType.RO,
}

# Города вылета
DEPARTURE_CITIES = {
    "москва": "Москва", "москвы": "Москва",
    "питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "петербург": "Санкт-Петербург",
    "казань": "Казань", "екатеринбург": "Екатеринбург", "новосибирск": "Новосибирск",
    "краснодар": "Краснодар", "сочи": "Сочи", "ростов": "Ростов-на-Дону",
    "уфа": "Уфа", "самара": "Самара", "нижний": "Нижний Новгород",
}


def extract_entities_regex(text: str) -> dict:
    """
    Извлечение сущностей из текста с помощью regex (fallback).
    
    Args:
        text: Сообщение пользователя
        
    Returns:
        Словарь извлечённых сущностей
    """
    text_lower = text.lower()
    entities = {}
    
    # 1. Страна
    for key, country in COUNTRIES_MAP.items():
        if key in text_lower:
            entities["destination_country"] = country
            break
    
    # 2. Курорт
    for key, (country, resort) in RESORTS_MAP.items():
        if key in text_lower:
            entities["destination_country"] = country
            entities["destination_resort"] = resort
            break
    
    # 3. Даты
    months_map = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    
    dates_found = []
    
    # dd.mm.yyyy или dd.mm
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
    
    # Месяц без конкретной даты: "в июне", "на май", "в марте"
    if not dates_found:
        month_only_patterns = [
            (r'(?:в|на|к)\s*январ[еья]?', 1),
            (r'(?:в|на|к)\s*феврал[еья]?', 2),
            (r'(?:в|на|к)\s*март[еа]?', 3),
            (r'(?:в|на|к)\s*апрел[еья]?', 4),
            (r'(?:в|на|к)\s*ма[йюея]', 5),
            (r'(?:в|на|к)\s*июн[еья]?', 6),
            (r'(?:в|на|к)\s*июл[еья]?', 7),
            (r'(?:в|на|к)\s*август[еа]?', 8),
            (r'(?:в|на|к)\s*сентябр[еья]?', 9),
            (r'(?:в|на|к)\s*октябр[еья]?', 10),
            (r'(?:в|на|к)\s*ноябр[еья]?', 11),
            (r'(?:в|на|к)\s*декабр[еья]?', 12),
        ]
        
        for pattern, month_num in month_only_patterns:
            if re.search(pattern, text_lower):
                year = date.today().year
                # Используем 1-е число месяца как начальную дату
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
        if len(dates_found) > 1:
            entities["date_to"] = dates_found[-1]
            entities["nights"] = (dates_found[-1] - dates_found[0]).days
    
    # 4. Количество ночей
    nights_match = re.search(r'(\d+)\s*(?:ноч|ночей|ночи|nights?)', text_lower)
    if nights_match:
        nights = int(nights_match.group(1))
        if 1 <= nights <= 30:
            entities["nights"] = nights
            if "date_from" in entities and "date_to" not in entities:
                entities["date_to"] = entities["date_from"] + timedelta(days=nights)
    
    # 5. Количество взрослых
    if re.search(r'вдво[её]м|двое|нас двое|на двоих|мы вдвоём|мы вдвоем|для двоих', text_lower):
        entities["adults"] = 2
    elif re.search(r'втро[её]м|трое|нас трое|на троих|для троих|семь[её]й из 3', text_lower):
        entities["adults"] = 3
    elif re.search(r'вчетвером|четверо|нас четверо|на четверых|для четверых|семь[её]й из 4', text_lower):
        entities["adults"] = 4
    elif re.search(r'впятером|пятеро|нас пятеро|на пятерых|для пятерых', text_lower):
        entities["adults"] = 5
    elif re.search(r'один|одного|одному|сам\b|одна\b', text_lower):
        entities["adults"] = 1
    else:
        adults_match = re.search(r'(\d+)\s*(?:взросл|человек|чел\.|персон)', text_lower)
        if adults_match:
            adults = int(adults_match.group(1))
            if 1 <= adults <= 6:
                entities["adults"] = adults
    
    # По умолчанию 2 взрослых если говорит о туре и не нашли явное указание
    if "adults" not in entities and any(word in text_lower for word in ["тур", "отдых", "поехать", "слетать", "отпуск", "хочу в", "хотим в"]):
        entities["adults"] = 2
    
    # 6. Дети - улучшенное распознавание
    children_ages = []
    
    # Паттерн: "ребенок 5 лет", "дочь 7 лет", "сын 3 года"
    patterns = [
        r'(?:реб[её]н(?:о?к)?|дит[яе]|дочь?|дочк[ау]|сын(?:а|ок)?|малыш(?:а|у)?)\s*(?:,?\s*)?(\d{1,2})\s*(?:год|лет|года)',
        r'(\d{1,2})\s*(?:-?\s*)?(?:летн(?:ий|яя|ее)|годовал)',
        r'с\s+реб[её]нком\s+(\d{1,2})\s*(?:год|лет|года)?',
        r'(?:реб[её]нк[ауе]?|дет[ией]?)\s*[-:]?\s*(\d{1,2})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            age = int(m)
            if 0 <= age <= 15 and age not in children_ages:
                children_ages.append(age)
    
    # Если просто "с ребенком" без возраста - предполагаем 5 лет
    if not children_ages and re.search(r'с\s+реб[её]нком|с\s+дет(?:ьми|ей)', text_lower):
        children_ages.append(5)
    
    if children_ages:
        entities["children"] = children_ages
    
    # 7. Тип питания
    for key, food_type in FOOD_TYPE_MAP.items():
        if key in text_lower:
            entities["food_type"] = food_type
            break
    
    # 8. Звёздность
    stars_match = re.search(r'(\d)\s*(?:\*|звезд)', text_lower)
    if stars_match:
        stars = int(stars_match.group(1))
        if 1 <= stars <= 5:
            entities["stars"] = stars
    
    # 9. Отель
    hotel_patterns = [
        r'(?:rixos|calista|titanic|hilton|marriott|sheraton|radisson)\s*[\w\s]*',
    ]
    for pattern in hotel_patterns:
        match = re.search(pattern, text_lower)
        if match:
            hotel_name = match.group(0).strip()
            if len(hotel_name) > 3:
                entities["hotel_name"] = hotel_name.title()
                entities.pop("stars", None)  # Не требуем звёздность
            break
    
    # 10. Город вылета
    for key, city in DEPARTURE_CITIES.items():
        if key in text_lower:
            entities["departure_city"] = city
            break
    
    return entities


def detect_phone_number(text: str) -> Optional[str]:
    """Извлекает номер телефона из текста."""
    # Паттерны для российских номеров
    patterns = [
        r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        r'(?:\+7|8)\d{10}',
        r'\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    
    return None


def detect_intent_regex(text: str, awaiting_phone: bool = False) -> str:
    """Определение намерения пользователя с помощью regex (fallback)."""
    text_lower = text.lower()
    
    # Если ждём телефон и видим номер — это phone_provided
    if awaiting_phone and detect_phone_number(text):
        return "phone_provided"
    
    # Запрос на бронирование
    if any(word in text_lower for word in [
        "заброниров", "забронируй", "бронирую", "брониров",
        "оставь заявк", "оставить заявк", "оставьте заявк",
        "хочу заказ", "закажу", "заказать",
        "хочу этот", "беру", "возьму"
    ]):
        return "booking"
    
    if any(word in text_lower for word in ["горящ", "горячие", "скидк", "акци", "дёшев", "дешев"]):
        return "hot_tours"
    elif any(word in text_lower for word in ["виза", "документ", "паспорт", "въезд"]):
        return "faq_visa"
    elif any(word in text_lower for word in ["оплат", "карт", "рассрочк", "стоимость", "цена"]):
        return "faq_payment"
    elif any(word in text_lower for word in ["возврат", "отмен", "аннуляц", "отказ"]):
        return "faq_cancel"
    elif any(word in text_lower for word in ["страхов", "медицин", "полис"]):
        return "faq_insurance"
    elif any(word in text_lower for word in ["документ", "справк", "свидетельств"]):
        return "faq_documents"
    elif any(word in text_lower for word in ["привет", "здравствуй", "добрый день", "добрый вечер"]):
        return "greeting"
    else:
        return "search_tour"


async def extract_entities_with_llm(text: str, awaiting_phone: bool = False) -> dict:
    """
    Извлечение сущностей с использованием YandexGPT.
    
    При ошибке или отключённом LLM использует regex fallback.
    """
    # Импортируем здесь для избежания циклических импортов
    from app.agent.llm import llm_client
    
    llm_entities = {}
    llm_intent = None
    
    if settings.YANDEX_GPT_ENABLED:
        try:
            result = await llm_client.extract_entities(text)
            
            # Преобразуем строковые даты в объекты date
            llm_entities = result.get("entities", {})
            llm_intent = result.get("intent")
            
            if "date_from" in llm_entities and isinstance(llm_entities["date_from"], str):
                try:
                    llm_entities["date_from"] = date.fromisoformat(llm_entities["date_from"])
                except ValueError:
                    del llm_entities["date_from"]
            
            if "date_to" in llm_entities and isinstance(llm_entities["date_to"], str):
                try:
                    llm_entities["date_to"] = date.fromisoformat(llm_entities["date_to"])
                except ValueError:
                    del llm_entities["date_to"]
            
            # Преобразуем food_type в enum
            if "food_type" in llm_entities and isinstance(llm_entities["food_type"], str):
                try:
                    llm_entities["food_type"] = FoodType(llm_entities["food_type"])
                except ValueError:
                    del llm_entities["food_type"]
            
        except Exception as e:
            print(f"LLM extraction failed: {e}")
    
    # ВСЕГДА дополняем regex fallback для надёжности
    regex_entities = extract_entities_regex(text)
    regex_intent = detect_intent_regex(text, awaiting_phone)
    
    # Объединяем: regex как база, LLM как дополнение
    # Это гарантирует что даже при ошибке LLM мы получим данные из regex
    final_entities = regex_entities.copy()
    for key, value in llm_entities.items():
        if value is not None:
            final_entities[key] = value
    
    # Определяем итоговый intent
    intent = llm_intent if llm_intent else regex_intent
    
    # Проверяем на booking или phone_provided отдельно
    if awaiting_phone and detect_phone_number(text):
        intent = "phone_provided"
    elif detect_intent_regex(text, awaiting_phone) == "booking":
        intent = "booking"
    
    return {"intent": intent, "entities": final_entities}


# ==================== FAQ KNOWLEDGE BASE ====================

FAQ_RESPONSES = {
    "faq_visa": """📋 **Информация о визах:**

**Безвизовые страны для граждан РФ:**
• **Турция** — до 60 дней
• **Египет** — виза по прилёту ($25) или без визы в Шарм-эль-Шейх (до 15 дней)
• **ОАЭ** — до 90 дней
• **Таиланд** — до 30 дней
• **Мальдивы** — до 30 дней
• **Индонезия (Бали)** — до 30 дней
• **Доминикана, Куба** — до 30 дней

**Требуется виза:**
• **Шенген** (Греция, Испания, Италия) — шенгенская виза
• **Кипр** — бесплатная провиза онлайн

**Загранпаспорт:** срок действия минимум 6 месяцев после возвращения.

Хотите подобрать тур? 🌴""",

    "faq_payment": """💳 **Способы оплаты:**

• Банковские карты (Visa, MasterCard, МИР)
• Наличные в офисе
• Банковский перевод
• СБП (Система быстрых платежей)

**Рассрочка:**
• 0% на 4-6 месяцев от банков-партнёров
• Первый взнос от 10%

**Бронирование:**
• Предоплата от 30%
• Полная оплата за 14 дней до вылета
• Горящие туры — полная оплата сразу

Могу помочь с подбором тура? ✈️""",

    "faq_cancel": """↩️ **Отмена и возврат:**

**Условия отмены:**
• Более 30 дней до вылета — возврат 90-100%
• 15-30 дней — удержание до 25%
• 7-14 дней — удержание до 50%
• 3-7 дней — удержание до 75%
• Менее 3 дней — возврат не гарантирован

**Страховка от невыезда:**
Покрывает отмену по болезни, отказу в визе, вызову в суд.
Стоимость: 3-5% от стоимости тура.

Рекомендуем оформлять при раннем бронировании! 🛡️""",

    "faq_insurance": """🏥 **Страхование:**

**Обязательная мед. страховка:**
• Включена в большинство пакетных туров
• Покрытие: 30 000 — 50 000 USD
• Покрывает: экстренную помощь, госпитализацию, эвакуацию

**Дополнительные страховки:**
• **От невыезда** — отмена по уважительным причинам
• **Багажа** — потеря, повреждение
• **Несчастных случаев** — травмы на отдыхе
• **Активного отдыха** — дайвинг, серфинг, лыжи

Нужна помощь с подбором тура? 🌊""",

    "faq_documents": """📄 **Документы для поездки:**

**Взрослые:**
• Загранпаспорт (срок 6+ месяцев)
• Авиабилеты и ваучер отеля
• Страховой полис
• Копия внутреннего паспорта

**Дети:**
• Загранпаспорт ребёнка
• Свидетельство о рождении (копия)
• Согласие второго родителя (если едет с одним)

**Для отдельных стран:**
• Обратные билеты
• Бронирование отеля
• Подтверждение финансов

Помочь с подбором тура? ✈️""",

    "greeting": """👋 Здравствуйте! Я — ИИ-ассистент туристического агентства МГП.

Я помогу вам:
• 🔍 Подобрать тур по вашим параметрам
• 🔥 Найти горящие предложения
• ❓ Ответить на вопросы о визах, оплате, документах

**Куда бы вы хотели поехать?**

Можете написать, например:
_«Хочу в Турцию на 7 ночей вдвоём с 15 февраля»_"""
}


# ==================== GRAPH NODES ====================

async def input_analyzer(state: AgentState) -> AgentState:
    """
    Узел анализа ввода пользователя.
    
    - Извлекает сущности из сообщения (через LLM или regex)
    - Обновляет search_params
    - Определяет missing_info
    - Реализует бизнес-логику из .cursorrules
    """
    if not state["messages"]:
        return state
    
    # Получаем последнее сообщение пользователя
    last_message = state["messages"][-1]
    if last_message["role"] != "user":
        return state
    
    user_text = last_message["content"]
    
    # Проверяем, ждём ли телефон
    awaiting_phone = state.get("awaiting_phone", False)
    
    # Извлекаем сущности (через LLM или regex fallback)
    extraction_result = await extract_entities_with_llm(user_text, awaiting_phone)
    
    intent = extraction_result.get("intent", "search_tour")
    entities = extraction_result.get("entities", {})
    
    # Обновляем search_params новыми данными
    current_params = state["search_params"].copy() if state["search_params"] else {}
    
    for key, value in entities.items():
        if value is not None:
            current_params[key] = value
    
    # Бизнес-логика: автоматический расчёт ночей из дат
    if "date_from" in current_params and "date_to" in current_params:
        d_from = current_params["date_from"]
        d_to = current_params["date_to"]
        if isinstance(d_from, date) and isinstance(d_to, date):
            nights = (d_to - d_from).days
            if nights > 0:
                current_params["nights"] = nights
    
    # Бизнес-логика: если есть ночи и date_from, вычисляем date_to
    if "date_from" in current_params and "nights" in current_params and "date_to" not in current_params:
        d_from = current_params["date_from"]
        if isinstance(d_from, date):
            current_params["date_to"] = d_from + timedelta(days=current_params["nights"])
    
    # Определяем недостающие параметры
    missing = get_missing_required_params(current_params)
    
    # Обновляем состояние
    state["search_params"] = current_params
    state["missing_info"] = missing
    state["intent"] = intent
    
    return state


async def faq_handler(state: AgentState) -> AgentState:
    """
    Узел обработки FAQ вопросов.
    
    Отвечает на вопросы о визах, оплате, документах и т.д.
    используя базу знаний или YandexGPT.
    """
    intent = state.get("intent", "")
    
    # Получаем готовый ответ из базы
    if intent in FAQ_RESPONSES:
        state["response"] = FAQ_RESPONSES[intent]
        return state
    
    # Если LLM включён и это FAQ вопрос, можно использовать его
    if settings.YANDEX_GPT_ENABLED and intent.startswith("faq_"):
        from app.agent.llm import llm_client
        
        last_message = state["messages"][-1]["content"] if state["messages"] else ""
        try:
            llm_response = await llm_client.answer_faq(last_message)
            if llm_response:
                state["response"] = llm_response
                return state
        except Exception as e:
            print(f"FAQ LLM error: {e}")
    
    # Fallback
    state["response"] = "К сожалению, я не нашёл ответ на ваш вопрос. Свяжитесь с нашим менеджером для уточнения."
    return state


async def tour_searcher(state: AgentState) -> AgentState:
    """
    Узел поиска туров.
    
    Вызывает TourvisorService.search_tours() если все параметры собраны.
    """
    params = state["search_params"]
    
    # Проверяем, что все обязательные параметры есть
    if state["missing_info"]:
        return state
    
    try:
        # Формируем Destination
        destination = Destination(
            country=params.get("destination_country", "Турция"),
            region=params.get("destination_region"),
            resort=params.get("destination_resort"),
            city=params.get("destination_city")
        )
        
        # Определяем даты
        date_from = params.get("date_from", date.today() + timedelta(days=14))
        nights = params.get("nights", 7)
        date_to = params.get("date_to", date_from + timedelta(days=nights))
        
        # Формируем SearchRequest
        search_request = SearchRequest(
            adults=params.get("adults", 2),
            children=params.get("children", []),
            destination=destination,
            hotel_name=params.get("hotel_name"),
            stars=params.get("stars"),
            date_from=date_from,
            date_to=date_to,
            food_type=params.get("food_type"),
            departure_city=params.get("departure_city", "Москва")
        )
        
        # Выполняем поиск
        if state["intent"] == "hot_tours":
            result = await tourvisor_service.get_hot_tours(
                adults=search_request.adults,
                country=destination.country
            )
        else:
            result = await tourvisor_service.search_tours(search_request)
        
        state["tour_offers"] = result.offers
        
    except Exception as e:
        state["error"] = f"Ошибка поиска: {str(e)}"
        state["tour_offers"] = []
    
    return state


async def responder(state: AgentState) -> AgentState:
    """
    Узел формирования ответа пользователю.
    
    - Если есть tour_offers — показываем карточки
    - Если есть missing_info — задаём уточняющий вопрос
    """
    # Если есть ошибка
    if state.get("error"):
        state["response"] = f"😔 Произошла ошибка: {state['error']}\n\nПопробуйте ещё раз или уточните параметры."
        return state
    
    # Если есть найденные туры
    if state["tour_offers"]:
        offers = state["tour_offers"]
        response_parts = [f"🎉 Нашёл {len(offers)} подходящих предложений:\n"]
        
        for i, offer in enumerate(offers[:5], 1):
            card = (
                f"\n**{i}. {offer.hotel_name}** {'⭐' * offer.hotel_stars}\n"
                f"📍 {offer.country}"
            )
            if offer.resort:
                card += f", {offer.resort}"
            card += (
                f"\n📅 {offer.dates_formatted} ({offer.duration_formatted})\n"
                f"🍽 {offer.food_type.value}\n"
                f"💰 **{offer.price_formatted}**"
            )
            if offer.price_per_person:
                card += f" ({offer.price_per_person:,} ₽/чел)".replace(",", " ")
            card += f"\n🏢 {offer.operator}"
            
            response_parts.append(card)
        
        response_parts.append("\n\n✈️ Хотите узнать подробнее о каком-то варианте или изменить параметры поиска?")
        state["response"] = "\n".join(response_parts)
        return state
    
    # Если есть недостающие параметры — задаём вопрос
    if state["missing_info"]:
        missing = state["missing_info"]
        
        # Приоритет вопросов
        priority_order = ["destination_country", "date_from", "adults"]
        
        # Выбираем первый недостающий по приоритету
        for param in priority_order:
            if param in missing:
                question = CLARIFICATION_QUESTIONS.get(param, f"Уточните {PARAM_NAMES_RU.get(param, param)}")
                
                # Добавляем контекст
                params = state["search_params"]
                context_parts = []
                
                if params.get("destination_country"):
                    context_parts.append(f"страна: {params['destination_country']}")
                if params.get("destination_resort"):
                    context_parts.append(f"курорт: {params['destination_resort']}")
                if params.get("date_from"):
                    d = params["date_from"]
                    if isinstance(d, date):
                        context_parts.append(f"даты: с {d.strftime('%d.%m')}")
                if params.get("adults"):
                    context_parts.append(f"туристов: {params['adults']}")
                
                if context_parts:
                    context = "✅ Уже знаю: " + ", ".join(context_parts) + "\n\n"
                else:
                    context = ""
                
                state["response"] = f"{context}❓ {question}"
                return state
        
        # Если остались другие параметры
        question = CLARIFICATION_QUESTIONS.get(missing[0], "Уточните детали поиска")
        state["response"] = f"❓ {question}"
        return state
    
    # Если параметры собраны, но туров нет
    state["response"] = (
        "🔍 К сожалению, по вашему запросу туров не найдено.\n\n"
        "Попробуйте:\n"
        "• Изменить даты поездки\n"
        "• Выбрать другой курорт\n"
        "• Расширить диапазон звёздности отелей\n\n"
        "Чем ещё могу помочь?"
    )
    return state


async def booking_handler(state: AgentState) -> AgentState:
    """
    Узел обработки бронирования.
    
    - Если телефон уже есть — сохраняем заявку через CRM
    - Если телефона нет — запрашиваем его
    """
    intent = state.get("intent", "")
    user_text = state["messages"][-1]["content"] if state["messages"] else ""
    
    # Если пользователь предоставил телефон
    if intent == "phone_provided":
        phone = detect_phone_number(user_text)
        if phone:
            state["customer_phone"] = phone
            state["awaiting_phone"] = False
            
            # Сохраняем заявку через CRM
            from app.services.crm import save_lead
            
            # Формируем описание параметров
            params = state.get("search_params", {})
            search_description = format_search_params_for_crm(params)
            
            # Извлекаем имя из сообщения (если есть)
            name = state.get("customer_name") or "Не указано"
            
            # Сохраняем заявку
            try:
                await save_lead(
                    name=name,
                    phone=phone,
                    search_params=search_description,
                    tour_offer_id=state.get("selected_tour_id")
                )
                
                state["response"] = (
                    "✅ **Спасибо! Ваша заявка принята.**\n\n"
                    f"📞 Телефон: {phone}\n"
                    f"🌍 Направление: {search_description}\n\n"
                    "👨‍💼 Менеджер МГП свяжется с вами в ближайшее время для уточнения деталей и бронирования.\n\n"
                    "Хотите пока посмотреть ещё варианты туров?"
                )
            except Exception as e:
                state["response"] = (
                    f"😔 Произошла ошибка при сохранении заявки: {str(e)}\n"
                    "Пожалуйста, позвоните нам по телефону +7-XXX-XXX-XX-XX"
                )
            
            return state
    
    # Если запрос на бронирование — просим телефон
    if intent == "booking":
        state["awaiting_phone"] = True
        
        # Проверяем, есть ли найденные туры
        if state.get("tour_offers"):
            state["response"] = (
                "🎉 Отличный выбор! Для оформления заявки мне нужен ваш номер телефона.\n\n"
                "📱 Пожалуйста, напишите ваш номер в формате:\n"
                "+7 (XXX) XXX-XX-XX или 8XXXXXXXXXX"
            )
        else:
            state["response"] = (
                "📝 Хорошо, оставим заявку!\n\n"
                "📱 Пожалуйста, напишите ваш номер телефона, и менеджер свяжется с вами для подбора тура.\n\n"
                "Формат: +7 (XXX) XXX-XX-XX"
            )
        
        return state
    
    return state


def format_search_params_for_crm(params: dict) -> str:
    """Форматирует параметры поиска для записи в CRM."""
    parts = []
    
    if params.get("destination_country"):
        parts.append(params["destination_country"])
    if params.get("destination_resort"):
        parts.append(params["destination_resort"])
    if params.get("nights"):
        parts.append(f"{params['nights']} ночей")
    if params.get("date_from"):
        d = params["date_from"]
        if isinstance(d, date):
            parts.append(f"с {d.strftime('%d.%m.%Y')}")
    if params.get("adults"):
        parts.append(f"{params['adults']} взр")
    if params.get("children"):
        kids = params["children"]
        parts.append(f"{len(kids)} дет ({', '.join(str(a) for a in kids)} лет)")
    
    return ", ".join(parts) if parts else "Параметры не указаны"


def should_search(state: AgentState) -> str:
    """
    Условная функция для определения следующего узла.
    
    Returns:
        "search" — искать туры
        "faq" — обработка FAQ
        "booking" — обработка бронирования
        "ask" — задать уточняющий вопрос
    """
    intent = state.get("intent", "search_tour")
    
    # Бронирование и получение телефона
    if intent in ("booking", "phone_provided"):
        return "booking"
    
    # FAQ обрабатываем отдельно
    if intent.startswith("faq_") or intent == "greeting":
        return "faq"
    
    # Если нет недостающих параметров — идём в поиск
    if not state["missing_info"]:
        return "search"
    
    return "ask"

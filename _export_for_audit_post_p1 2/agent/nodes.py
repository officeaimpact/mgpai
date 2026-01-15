"""Узлы графа LangGraph для обработки диалога."""

from typing import Literal
from agent.state import DialogState
from services.tourvisor import TourvisorService
from services.yandexgpt import YandexGPTService
from models.schemas import ChatMessage


# Системный промпт для ИИ-ассистента МГП
SYSTEM_PROMPT = """Ты — ИИ-ассистент туристического агентства МГП. 
Твоя задача — помочь пользователю подобрать тур.

Правила:
1. Не спрашивай повторно то, что уже понятно из фразы пользователя.
2. Если указаны даты, автоматически вычисляй количество ночей.
3. Если указан конкретный отель, не запрашивай его звёздность.
4. Поддерживай группы от 1 до 6 взрослых и детей (0-2 года, 2-15 лет).
5. Будь вежливым и профессиональным.
6. Отвечай кратко и по делу."""


async def intent_node(state: DialogState) -> DialogState:
    """
    Узел определения намерения пользователя.
    
    Анализирует последнее сообщение и определяет:
    - Поиск тура
    - FAQ вопрос (визы, оплата, возвраты)
    - Горящие туры
    - Уточнение параметров
    """
    # TODO: Реализовать определение намерения через YandexGPT
    last_message = state["messages"][-1] if state["messages"] else None
    
    if last_message:
        content = last_message.content.lower()
        
        if any(word in content for word in ["виза", "документ", "паспорт"]):
            state["intent"] = "faq_visa"
        elif any(word in content for word in ["оплат", "цена", "стоимость"]):
            state["intent"] = "faq_payment"
        elif any(word in content for word in ["горящ", "горячие", "скидк"]):
            state["intent"] = "hot_tours"
        else:
            state["intent"] = "search_tour"
    
    return state


async def extract_params_node(state: DialogState) -> DialogState:
    """
    Узел извлечения параметров поиска из сообщений.
    
    Извлекает: страну, регион, даты, количество туристов,
    предпочтения по отелю и питанию.
    """
    # TODO: Реализовать извлечение параметров через YandexGPT
    # с учётом контекста всего диалога
    
    # Определяем недостающие обязательные параметры
    missing = []
    
    if not state.get("search_params"):
        missing.extend(["destination_country", "date_from", "adults"])
    else:
        params = state["search_params"]
        if not params.destination_country:
            missing.append("destination_country")
        if not params.date_from:
            missing.append("date_from")
        if not params.adults:
            missing.append("adults")
    
    state["missing_params"] = missing
    return state


async def search_node(state: DialogState) -> DialogState:
    """
    Узел поиска туров через Tourvisor API.
    
    Выполняется когда все обязательные параметры собраны.
    Возвращает 3-5 карточек предложений.
    """
    if state["missing_params"]:
        return state
    
    tourvisor = TourvisorService()
    try:
        offers = await tourvisor.search_tours(
            state["search_params"],
            state.get("filters")
        )
        # Ограничиваем до 5 предложений
        state["tour_offers"] = offers[:5]
    finally:
        await tourvisor.close()
    
    return state


async def response_node(state: DialogState) -> DialogState:
    """
    Узел генерации ответа пользователю.
    
    Формирует ответ на основе текущего состояния:
    - Уточняющие вопросы для недостающих параметров
    - Презентация найденных туров
    - Ответы на FAQ
    """
    yandex_gpt = YandexGPTService()
    
    try:
        if state["intent"] == "faq_visa":
            response_text = "Для большинства направлений требуется загранпаспорт. " \
                           "Информацию о визах уточните у нашего менеджера."
        elif state["intent"] == "faq_payment":
            response_text = "Мы принимаем оплату картами и наличными. " \
                           "Возможна рассрочка. Подробности у менеджера."
        elif state["missing_params"]:
            # Генерируем уточняющий вопрос
            param_questions = {
                "destination_country": "Куда бы вы хотели поехать?",
                "date_from": "На какие даты планируете поездку?",
                "adults": "Сколько взрослых поедет?"
            }
            questions = [param_questions.get(p, p) for p in state["missing_params"][:2]]
            response_text = " ".join(questions)
        elif state["tour_offers"]:
            response_text = f"Нашёл {len(state['tour_offers'])} подходящих предложений!"
        else:
            response_text = "К сожалению, по вашему запросу туров не найдено. " \
                           "Попробуйте изменить параметры поиска."
        
        # Добавляем ответ ассистента в историю
        state["messages"].append(ChatMessage(
            role="assistant",
            content=response_text
        ))
        
    finally:
        await yandex_gpt.close()
    
    return state


def should_search(state: DialogState) -> Literal["search", "response"]:
    """
    Условный переход: искать туры или генерировать ответ.
    """
    if state["intent"] in ["search_tour", "hot_tours"] and not state["missing_params"]:
        return "search"
    return "response"

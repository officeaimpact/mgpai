"""
LangGraph граф диалога для ИИ-ассистента МГП.

Session Persistence:
    - MemorySaver для thread-based persistence
    - Каждый пользователь имеет уникальный thread_id
    - Состояние сохраняется между HTTP-запросами

Архитектура воронки:
    START -> input_analyzer -> [условие] -> 
                                   |
                                   +-- (base) ask -----------> responder -----> END
                                   +-- (details) quality_check --------------> END
                                   +-- (search) tour_searcher -> responder --> END
                                   +-- booking_handler ----------------------> END
                                   +-- faq_handler --------------------------> END
                                   +-- general_chat_handler -----------------> END
                                   
Воронка сбора данных:
    1. БАЗА: страна, даты, состав
    2. ДЕТАЛИ: звёзды, питание, бюджет (для массовых направлений)
    3. ПОИСК: все параметры собраны
"""
from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState, create_initial_state, Message
from app.agent.nodes import (
    input_analyzer,
    tour_searcher,
    responder,
    faq_handler,
    booking_handler,
    general_chat_handler,
    quality_check_handler,
    invalid_country_handler,
    child_ages_handler,  # Критическая проверка: дети без возраста
    more_tours_handler,  # GAP Analysis: пагинация
    continue_search_handler,  # GAP Analysis: углублённый поиск
    should_search,
    clean_response_text  # GREETING CLEANER
)
from app.core.session import session_manager, apply_window_buffer, MAX_MESSAGES_HISTORY

# Настройка логгера
logger = logging.getLogger(__name__)


def create_agent_graph() -> StateGraph:
    """
    Создание графа диалога для ИИ-ассистента МГП.
    
    Воронка сбора данных:
    1. input_analyzer — анализ ввода и извлечение сущностей
    2. Условный переход (воронка):
       - БАЗА не собрана -> responder (спрашиваем страну/даты/состав)
       - ДЕТАЛИ нужны -> quality_check_handler (спрашиваем звёзды/питание)
       - ВСЕ параметры -> tour_searcher (ищем туры)
       - FAQ вопрос -> faq_handler
       - Бронирование -> booking_handler
       - Общий вопрос -> general_chat_handler
    3. tour_searcher -> responder
    4. Все остальные -> END
    
    Returns:
        Скомпилированный граф LangGraph
    """
    # Создаём граф с типизированным состоянием
    workflow = StateGraph(AgentState)
    
    # Добавляем узлы
    workflow.add_node("input_analyzer", input_analyzer)
    workflow.add_node("tour_searcher", tour_searcher)
    workflow.add_node("faq_handler", faq_handler)
    workflow.add_node("booking_handler", booking_handler)
    workflow.add_node("general_chat_handler", general_chat_handler)
    workflow.add_node("quality_check_handler", quality_check_handler)
    workflow.add_node("invalid_country_handler", invalid_country_handler)
    workflow.add_node("child_ages_handler", child_ages_handler)  # КРИТИЧНО: дети без возраста
    workflow.add_node("more_tours_handler", more_tours_handler)  # GAP Analysis: пагинация
    workflow.add_node("continue_search_handler", continue_search_handler)  # GAP Analysis: углублённый поиск
    workflow.add_node("responder", responder)
    
    # Устанавливаем точку входа
    workflow.set_entry_point("input_analyzer")
    
    # Условное ребро после анализа ввода (воронка)
    workflow.add_conditional_edges(
        "input_analyzer",
        should_search,
        {
            "search": "tour_searcher",                     # Все параметры есть — ищем туры
            "quality_check": "quality_check_handler",      # Спросить о качестве
            "faq": "faq_handler",                          # FAQ вопрос — отвечаем из базы знаний
            "booking": "booking_handler",                  # Бронирование — обрабатываем заявку (включая группы >6)
            "general_chat": "general_chat_handler",        # Общий вопрос — отвечаем + мягко собираем
            "invalid_country": "invalid_country_handler",  # Невалидная страна
            "ask_child_ages": "child_ages_handler",        # КРИТИЧНО: дети без возраста
            "more_tours": "more_tours_handler",            # GAP Analysis: пагинация
            "continue_search": "continue_search_handler",  # GAP Analysis: углублённый поиск
            "ask": "responder"                             # Нужны базовые уточнения — спрашиваем
        }
    )
    
    # После поиска всегда идём в responder
    workflow.add_edge("tour_searcher", "responder")
    
    # После FAQ — завершаем
    workflow.add_edge("faq_handler", END)
    
    # После бронирования — завершаем
    workflow.add_edge("booking_handler", END)
    
    # После general chat — завершаем
    workflow.add_edge("general_chat_handler", END)
    
    # После quality check — завершаем (ждём ответа пользователя)
    workflow.add_edge("quality_check_handler", END)
    
    # После invalid_country — завершаем (предлагаем альтернативы)
    workflow.add_edge("invalid_country_handler", END)
    
    # После child_ages_handler — завершаем (ждём возраст детей)
    workflow.add_edge("child_ages_handler", END)
    
    # После more_tours_handler — завершаем (пагинация)
    workflow.add_edge("more_tours_handler", END)
    
    # После continue_search_handler — завершаем (углублённый поиск)
    workflow.add_edge("continue_search_handler", END)
    
    # После ответа — завершаем
    workflow.add_edge("responder", END)
    
    # Компилируем граф с checkpointer для persistence
    # MemorySaver сохраняет состояние между вызовами по thread_id
    return workflow.compile(checkpointer=session_manager.get_checkpointer())


# Глобальный экземпляр графа с persistence
agent_graph = create_agent_graph()
logger.info("🔗 LangGraph агент инициализирован с MemorySaver checkpointer")


async def process_message(
    user_message: str,
    thread_id: str,
    state: Optional[AgentState] = None
) -> tuple[str, AgentState]:
    """
    Обработка сообщения пользователя через граф агента с persistence.
    
    Подход: Явное восстановление состояния из checkpointer.
    
    Args:
        user_message: Сообщение от пользователя
        thread_id: Уникальный идентификатор сессии/пользователя
        state: Начальное состояние (только для первого сообщения)
        
    Returns:
        Кортеж (ответ ассистента, обновлённое состояние)
    """
    # Получаем конфигурацию с thread_id
    config = session_manager.get_config(thread_id)
    
    logger.info(f"📨 Обработка сообщения для thread_id={thread_id}")
    
    # ==================== ВОССТАНОВЛЕНИЕ СОСТОЯНИЯ ====================
    # Если state не передан, восстанавливаем из checkpointer
    
    if state is None:
        # Пробуем восстановить состояние из checkpointer
        try:
            checkpointer = session_manager.get_checkpointer()
            checkpoint_tuple = checkpointer.get_tuple(config)
            
            if checkpoint_tuple and checkpoint_tuple.checkpoint:
                # Восстанавливаем состояние из channel_values
                channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                
                if channel_values and "messages" in channel_values:
                    logger.info(f"🔄 Восстановлено состояние для thread_id={thread_id}")
                    state = create_initial_state()
                    
                    # Копируем все сохранённые значения
                    for key, value in channel_values.items():
                        if key in state and value is not None:
                            state[key] = value
                else:
                    logger.info(f"📭 Пустой checkpoint для thread_id={thread_id}")
                    state = create_initial_state()
            else:
                logger.info(f"📭 Checkpoint не найден для thread_id={thread_id}")
                state = create_initial_state()
        except Exception as e:
            logger.warning(f"⚠️ Ошибка восстановления: {e}")
            state = create_initial_state()
    else:
        logger.info(f"🆕 Новая сессия: thread_id={thread_id}")
    
    # Гарантируем что messages это список
    if state.get("messages") is None:
        state["messages"] = []
    
    # Добавляем сообщение пользователя
    state["messages"].append(Message(role="user", content=user_message))
    
    # ==================== WINDOW BUFFER ====================
    state["messages"] = apply_window_buffer(
        state["messages"], 
        max_messages=MAX_MESSAGES_HISTORY
    )
    
    # Сбрасываем response перед запуском графа
    state["response"] = ""
    state["error"] = None
    
    # Запускаем граф
    result = await agent_graph.ainvoke(state, config=config)
    
    # Получаем ответ
    assistant_response = result.get("response", "")
    
    # ==================== GREETING CLEANER ====================
    # Определяем: это первое сообщение в сессии?
    is_first_message = len(result.get("messages", [])) <= 1
    
    # Очищаем ответ от приветствий (если не первое сообщение)
    assistant_response = clean_response_text(assistant_response, is_first_message=is_first_message)
    result["response"] = assistant_response  # Обновляем и в result
    
    # Добавляем ответ ассистента в историю
    if assistant_response:
        if "messages" not in result:
            result["messages"] = []
        result["messages"].append(Message(role="assistant", content=assistant_response))
    
    # Обновляем метаданные сессии
    session_manager.increment_message_count(thread_id)
    
    logger.info(f"✅ Ответ сформирован для thread_id={thread_id}")
    
    return assistant_response, result


async def process_message_legacy(
    user_message: str,
    state: Optional[AgentState] = None
) -> tuple[str, AgentState]:
    """
    Legacy-метод для обратной совместимости (без persistence).
    
    DEPRECATED: Используйте process_message с thread_id.
    """
    # Генерируем временный thread_id
    import uuid
    temp_thread_id = f"legacy_{uuid.uuid4().hex[:8]}"
    return await process_message(user_message, temp_thread_id, state)


async def chat(user_message: str, session_state: Optional[dict] = None) -> dict:
    """
    Упрощённый интерфейс для чата.
    
    Args:
        user_message: Сообщение пользователя
        session_state: Состояние сессии (для продолжения диалога)
        
    Returns:
        Словарь с ответом и состоянием
    """
    # Восстанавливаем состояние из сессии
    state = None
    if session_state:
        state = AgentState(
            messages=session_state.get("messages", []),
            search_params=session_state.get("search_params", {}),
            missing_info=session_state.get("missing_info", []),
            tour_offers=[],
            response="",
            intent=session_state.get("intent"),
            error=None,
            customer_name=session_state.get("customer_name"),
            customer_phone=session_state.get("customer_phone"),
            awaiting_phone=session_state.get("awaiting_phone", False),
            selected_tour_id=session_state.get("selected_tour_id"),
            cascade_stage=session_state.get("cascade_stage", 1),
            quality_check_asked=session_state.get("quality_check_asked", False),
            is_first_message=False,
            greeted=session_state.get("greeted", False),
            # Новые поля
            is_group_request=session_state.get("is_group_request", False),
            group_size=session_state.get("group_size", 0),
            invalid_country=session_state.get("invalid_country"),
            # Гибкий поиск и согласие
            flex_search=session_state.get("flex_search", False),
            flex_days=session_state.get("flex_days", 2),  # По умолчанию ±2 дня
            awaiting_agreement=session_state.get("awaiting_agreement", False),
            pending_action=session_state.get("pending_action"),
            search_attempts=session_state.get("search_attempts", 0),
            offered_alt_departure=session_state.get("offered_alt_departure", False),
            missing_child_ages=session_state.get("missing_child_ages", 0)
        )
    
    # Обрабатываем сообщение
    response, new_state = await process_message(user_message, state)
    
    # Формируем результат
    return {
        "response": response,
        "tour_offers": [offer.model_dump() for offer in new_state.get("tour_offers", [])],
        "session_state": {
            "messages": new_state["messages"],
            "search_params": new_state["search_params"],
            "missing_info": new_state["missing_info"],
            "intent": new_state.get("intent"),
            "customer_name": new_state.get("customer_name"),
            "customer_phone": new_state.get("customer_phone"),
            "awaiting_phone": new_state.get("awaiting_phone", False),
            "selected_tour_id": new_state.get("selected_tour_id"),
            "cascade_stage": new_state.get("cascade_stage", 1),
            "quality_check_asked": new_state.get("quality_check_asked", False),
            "greeted": new_state.get("greeted", False),
            # Новые поля
            "is_group_request": new_state.get("is_group_request", False),
            "group_size": new_state.get("group_size", 0),
            "invalid_country": new_state.get("invalid_country"),
            # Гибкий поиск и согласие
            "flex_search": new_state.get("flex_search", False),
            "flex_days": new_state.get("flex_days", 2),
            "awaiting_agreement": new_state.get("awaiting_agreement", False),
            "pending_action": new_state.get("pending_action"),
            "search_attempts": new_state.get("search_attempts", 0),
            "offered_alt_departure": new_state.get("offered_alt_departure", False),
            "missing_child_ages": new_state.get("missing_child_ages", 0)
        }
    }

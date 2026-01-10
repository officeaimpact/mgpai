"""
LangGraph граф диалога для ИИ-ассистента МГП.

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
    should_search
)


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
    
    # После ответа — завершаем
    workflow.add_edge("responder", END)
    
    # Компилируем граф
    return workflow.compile()


# Глобальный экземпляр графа
agent_graph = create_agent_graph()


async def process_message(
    user_message: str,
    state: Optional[AgentState] = None
) -> tuple[str, AgentState]:
    """
    Обработка сообщения пользователя через граф агента.
    
    Args:
        user_message: Сообщение от пользователя
        state: Текущее состояние диалога (None для нового диалога)
        
    Returns:
        Кортеж (ответ ассистента, обновлённое состояние)
    """
    # Инициализируем состояние если нужно
    if state is None:
        state = create_initial_state()
    
    # Добавляем сообщение пользователя
    state["messages"].append(Message(role="user", content=user_message))
    
    # Запускаем граф
    result = await agent_graph.ainvoke(state)
    
    # Добавляем ответ ассистента в историю
    assistant_response = result.get("response", "")
    if assistant_response:
        result["messages"].append(Message(role="assistant", content=assistant_response))
    
    return assistant_response, result


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

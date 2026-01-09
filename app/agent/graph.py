"""
LangGraph граф диалога для ИИ-ассистента МГП.

Архитектура:
    START -> input_analyzer -> [условие] -> tour_searcher -> responder -> END
                                   |                              ^
                                   +-- booking_handler -----------+
                                   +-- faq_handler ---------------+
                                   +------------------------------+
                                   (если missing_info не пусто)
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
    should_search
)


def create_agent_graph() -> StateGraph:
    """
    Создание графа диалога для ИИ-ассистента МГП.
    
    Граф реализует логику:
    1. input_analyzer — анализ ввода и извлечение сущностей
    2. Условный переход:
       - Все параметры собраны -> tour_searcher
       - FAQ вопрос -> faq_handler
       - Бронирование/телефон -> booking_handler
       - Нужны уточнения -> responder
    3. tour_searcher -> responder
    4. faq_handler -> END
    5. booking_handler -> END
    6. responder -> END
    
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
    workflow.add_node("responder", responder)
    
    # Устанавливаем точку входа
    workflow.set_entry_point("input_analyzer")
    
    # Условное ребро после анализа ввода
    workflow.add_conditional_edges(
        "input_analyzer",
        should_search,
        {
            "search": "tour_searcher",      # Все параметры есть — ищем туры
            "faq": "faq_handler",           # FAQ вопрос — отвечаем из базы знаний
            "booking": "booking_handler",   # Бронирование — обрабатываем заявку
            "ask": "responder"              # Нужны уточнения — спрашиваем
        }
    )
    
    # После поиска всегда идём в responder
    workflow.add_edge("tour_searcher", "responder")
    
    # После FAQ — завершаем
    workflow.add_edge("faq_handler", END)
    
    # После бронирования — завершаем
    workflow.add_edge("booking_handler", END)
    
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
            tour_offers=[],  # Туры не сохраняем между запросами
            response="",
            intent=session_state.get("intent"),
            error=None,
            customer_name=session_state.get("customer_name"),
            customer_phone=session_state.get("customer_phone"),
            awaiting_phone=session_state.get("awaiting_phone", False),
            selected_tour_id=session_state.get("selected_tour_id")
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
            "selected_tour_id": new_state.get("selected_tour_id")
        }
    }

"""Основной граф LangGraph для управления диалогом."""

from langgraph.graph import StateGraph, END
from agent.state import DialogState
from agent.nodes import (
    intent_node,
    extract_params_node,
    search_node,
    response_node,
    should_search
)


def create_dialog_graph() -> StateGraph:
    """
    Создание графа диалога для ИИ-ассистента МГП.
    
    Граф обрабатывает:
    1. Определение намерения пользователя
    2. Извлечение параметров поиска
    3. Поиск туров (при наличии всех параметров)
    4. Генерация ответа
    
    Returns:
        Скомпилированный граф LangGraph
    """
    # Создаём граф с типизированным состоянием
    workflow = StateGraph(DialogState)
    
    # Добавляем узлы
    workflow.add_node("intent", intent_node)
    workflow.add_node("extract_params", extract_params_node)
    workflow.add_node("search", search_node)
    workflow.add_node("response", response_node)
    
    # Определяем переходы
    workflow.set_entry_point("intent")
    
    # intent -> extract_params (всегда)
    workflow.add_edge("intent", "extract_params")
    
    # extract_params -> search или response (условно)
    workflow.add_conditional_edges(
        "extract_params",
        should_search,
        {
            "search": "search",
            "response": "response"
        }
    )
    
    # search -> response (всегда)
    workflow.add_edge("search", "response")
    
    # response -> END
    workflow.add_edge("response", END)
    
    # Компилируем граф
    return workflow.compile()


# Глобальный экземпляр графа
dialog_graph = create_dialog_graph()

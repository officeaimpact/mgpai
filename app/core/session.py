"""
Session Persistence для ИИ-ассистента МГП.

Реализует сохранение контекста диалога между HTTP-запросами.

Архитектура:
- MemorySaver (для тестов и разработки)
- PostgresSaver (для продакшена, TODO)

Thread-based persistence:
- Каждый пользователь имеет уникальный thread_id
- Состояние сохраняется в checkpointer между запросами
- Window Buffer ограничивает историю сообщений
"""
from __future__ import annotations

import logging
from typing import Optional, Any
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver

# Настройка логгера
logger = logging.getLogger(__name__)


# ==================== CHECKPOINTER CONFIG ====================

# Window Buffer: максимальное количество сообщений в истории
MAX_MESSAGES_HISTORY = 20

# Время жизни сессии (в секундах) - 24 часа
SESSION_TTL_SECONDS = 86400


# ==================== MEMORY SAVER (Development) ====================

class SessionManager:
    """
    Менеджер сессий для LangGraph агента.
    
    Использует MemorySaver для тестирования.
    Для продакшена заменить на PostgresSaver.
    """
    
    def __init__(self):
        # MemorySaver - хранит состояние в памяти
        # Для продакшена: заменить на PostgresSaver
        self.checkpointer = MemorySaver()
        
        # Метаданные сессий (время создания, последний запрос)
        self._session_metadata: dict[str, dict[str, Any]] = {}
        
        logger.info("🔒 SessionManager инициализирован (MemorySaver)")
    
    def get_config(self, thread_id: str) -> dict:
        """
        Создаёт конфигурацию для LangGraph с thread_id.
        
        Args:
            thread_id: Уникальный идентификатор сессии/пользователя
            
        Returns:
            Конфигурация для ainvoke: {"configurable": {"thread_id": "..."}}
        """
        # Обновляем метаданные
        if thread_id not in self._session_metadata:
            self._session_metadata[thread_id] = {
                "created_at": datetime.now(),
                "last_access": datetime.now(),
                "message_count": 0
            }
        else:
            self._session_metadata[thread_id]["last_access"] = datetime.now()
        
        return {
            "configurable": {
                "thread_id": thread_id
            }
        }
    
    def get_checkpointer(self) -> MemorySaver:
        """Возвращает checkpointer для компиляции графа."""
        return self.checkpointer
    
    def get_session_metadata(self, thread_id: str) -> Optional[dict]:
        """Получить метаданные сессии."""
        return self._session_metadata.get(thread_id)
    
    def increment_message_count(self, thread_id: str) -> None:
        """Увеличить счётчик сообщений."""
        if thread_id in self._session_metadata:
            self._session_metadata[thread_id]["message_count"] += 1
    
    def cleanup_old_sessions(self) -> int:
        """
        Очистка старых сессий (TTL).
        
        Returns:
            Количество удалённых сессий
        """
        now = datetime.now()
        to_delete = []
        
        for thread_id, meta in self._session_metadata.items():
            age_seconds = (now - meta["last_access"]).total_seconds()
            if age_seconds > SESSION_TTL_SECONDS:
                to_delete.append(thread_id)
        
        for thread_id in to_delete:
            del self._session_metadata[thread_id]
            # Примечание: MemorySaver не поддерживает удаление по thread_id
            # Для PostgresSaver добавить: self.checkpointer.delete(thread_id)
        
        if to_delete:
            logger.info(f"🧹 Очищено {len(to_delete)} старых сессий")
        
        return len(to_delete)
    
    def get_active_sessions_count(self) -> int:
        """Количество активных сессий."""
        return len(self._session_metadata)


def apply_window_buffer(messages: list, max_messages: int = MAX_MESSAGES_HISTORY) -> list:
    """
    Window Buffer: ограничивает историю сообщений.
    
    Сохраняет:
    - Последние N сообщений
    - Ключевые параметры (в state.search_params)
    
    Args:
        messages: Полная история сообщений
        max_messages: Максимальное количество сообщений
        
    Returns:
        Обрезанная история
    """
    if len(messages) <= max_messages:
        return messages
    
    # Берём последние N сообщений
    # При этом сохраняем первое сообщение (контекст приветствия)
    first_message = messages[0] if messages else None
    recent_messages = messages[-(max_messages - 1):]
    
    if first_message and first_message not in recent_messages:
        return [first_message] + recent_messages
    
    return recent_messages


# ==================== POSTGRES SAVER (Production Ready) ====================
# 
# Для продакшена использовать PostgresSaver:
#
# from langgraph.checkpoint.postgres import PostgresSaver
# import psycopg
#
# class ProductionSessionManager(SessionManager):
#     def __init__(self, connection_string: str):
#         self.conn = psycopg.connect(connection_string)
#         self.checkpointer = PostgresSaver(self.conn)
#         self.checkpointer.setup()  # Создаёт таблицы
#
# ==================== END POSTGRES STUB ====================


# Глобальный экземпляр менеджера сессий
session_manager = SessionManager()

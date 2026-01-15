"""
Тест Session Persistence для ИИ-ассистента МГП.

Проверяет, что:
1. Контекст сохраняется между сообщениями
2. thread_id разделяет разных пользователей
3. Window Buffer работает корректно
4. Параметры поиска сохраняются
"""
import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.graph import process_message
from app.agent.state import create_initial_state
from app.core.session import session_manager, apply_window_buffer


async def test_session_persistence():
    """Тест: контекст сохраняется между сообщениями."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 1: Session Persistence")
    print("=" * 60)
    
    thread_id = "test_persistence_001"
    state = create_initial_state()
    
    # Сообщение 1: Указываем страну
    print("\n📩 Сообщение 1: 'Хочу в Турцию'")
    response1, state = await process_message("Хочу в Турцию", thread_id, state)
    print(f"📤 Ответ: {response1[:100]}...")
    
    country1 = state.get("search_params", {}).get("destination_country")
    assert country1 == "Турция", f"❌ Страна не сохранена! Got: {country1}"
    print(f"✅ Страна сохранена: {country1}")
    
    # Сообщение 2: Указываем город вылета
    print("\n📩 Сообщение 2: 'Из Москвы'")
    response2, state = await process_message("Из Москвы", thread_id, state)
    print(f"📤 Ответ: {response2[:100]}...")
    
    # Проверяем, что страна ВСЁ ЕЩЁ сохранена
    country2 = state.get("search_params", {}).get("destination_country")
    departure2 = state.get("search_params", {}).get("departure_city")
    
    assert country2 == "Турция", f"❌ Страна потеряна! Got: {country2}"
    assert departure2 == "Москва", f"❌ Город вылета не сохранён! Got: {departure2}"
    print(f"✅ Страна сохранена: {country2}")
    print(f"✅ Город вылета: {departure2}")
    
    # Сообщение 3: Указываем дату
    print("\n📩 Сообщение 3: '15 февраля'")
    response3, state = await process_message("15 февраля", thread_id, state)
    print(f"📤 Ответ: {response3[:100]}...")
    
    # Проверяем, что ВСЕ параметры сохранены
    country3 = state.get("search_params", {}).get("destination_country")
    departure3 = state.get("search_params", {}).get("departure_city")
    date_from = state.get("search_params", {}).get("date_from")
    
    assert country3 == "Турция", f"❌ Страна потеряна! Got: {country3}"
    assert departure3 == "Москва", f"❌ Город вылета потерян! Got: {departure3}"
    assert date_from is not None, f"❌ Дата не сохранена! Got: {date_from}"
    
    print(f"✅ Страна: {country3}")
    print(f"✅ Город вылета: {departure3}")
    print(f"✅ Дата: {date_from}")
    
    print("\n✅ ТЕСТ 1 ПРОЙДЕН: Контекст сохраняется между сообщениями!")
    return True


async def test_thread_isolation():
    """Тест: разные thread_id имеют разные контексты."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 2: Thread Isolation")
    print("=" * 60)
    
    # Пользователь 1
    thread_id_1 = "user_alice_001"
    state1 = create_initial_state()
    print("\n👤 Пользователь Alice: 'Хочу в Турцию'")
    _, state1 = await process_message("Хочу в Турцию", thread_id_1, state1)
    
    # Пользователь 2
    thread_id_2 = "user_bob_002"
    state2 = create_initial_state()
    print("👤 Пользователь Bob: 'Хочу в Египет'")
    _, state2 = await process_message("Хочу в Египет", thread_id_2, state2)
    
    # Проверяем изоляцию
    country1 = state1.get("search_params", {}).get("destination_country")
    country2 = state2.get("search_params", {}).get("destination_country")
    
    assert country1 == "Турция", f"❌ Alice: ожидали Турцию, получили {country1}"
    assert country2 == "Египет", f"❌ Bob: ожидали Египет, получили {country2}"
    
    print(f"✅ Alice: {country1}")
    print(f"✅ Bob: {country2}")
    print("\n✅ ТЕСТ 2 ПРОЙДЕН: Контексты пользователей изолированы!")
    return True


async def test_window_buffer():
    """Тест: Window Buffer ограничивает историю."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 3: Window Buffer")
    print("=" * 60)
    
    # Создаём длинную историю
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(30)]
    
    print(f"📜 Исходная история: {len(messages)} сообщений")
    
    # Применяем Window Buffer
    trimmed = apply_window_buffer(messages, max_messages=20)
    
    print(f"📜 После Window Buffer: {len(trimmed)} сообщений")
    
    assert len(trimmed) == 20, f"❌ Ожидали 20, получили {len(trimmed)}"
    
    # Проверяем, что первое сообщение сохранено
    first_content = trimmed[0].get("content")
    assert first_content == "Message 0", f"❌ Первое сообщение потеряно! Got: {first_content}"
    
    print(f"✅ Первое сообщение сохранено: {first_content}")
    print(f"✅ Последнее сообщение: {trimmed[-1].get('content')}")
    
    print("\n✅ ТЕСТ 3 ПРОЙДЕН: Window Buffer работает корректно!")
    return True


async def test_session_manager():
    """Тест: SessionManager отслеживает метаданные."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 4: Session Manager")
    print("=" * 60)
    
    thread_id = "test_session_manager_001"
    
    # Получаем конфиг (создаёт сессию)
    config = session_manager.get_config(thread_id)
    
    print(f"📋 Config: {config}")
    
    assert "configurable" in config
    assert config["configurable"]["thread_id"] == thread_id
    
    # Проверяем метаданные
    meta = session_manager.get_session_metadata(thread_id)
    assert meta is not None, "❌ Метаданные не созданы!"
    
    print(f"✅ created_at: {meta.get('created_at')}")
    print(f"✅ last_access: {meta.get('last_access')}")
    print(f"✅ message_count: {meta.get('message_count')}")
    
    # Инкрементируем счётчик
    session_manager.increment_message_count(thread_id)
    meta2 = session_manager.get_session_metadata(thread_id)
    assert meta2["message_count"] == 1, "❌ Счётчик не увеличился!"
    
    print(f"✅ message_count после increment: {meta2['message_count']}")
    
    # Проверяем статистику
    active = session_manager.get_active_sessions_count()
    print(f"✅ Активных сессий: {active}")
    
    print("\n✅ ТЕСТ 4 ПРОЙДЕН: Session Manager работает корректно!")
    return True


async def main():
    """Запуск всех тестов."""
    print("\n" + "=" * 60)
    print("🔒 SESSION PERSISTENCE TESTS")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(await test_session_persistence())
        results.append(await test_thread_isolation())
        results.append(await test_window_buffer())
        results.append(await test_session_manager())
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"📊 ИТОГ: {passed}/{total} тестов пройдено")
    print("=" * 60)
    
    if passed == total:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print("❌ ЕСТЬ ОШИБКИ!")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

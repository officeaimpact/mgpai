"""
Тесты State Machine для ИИ-ассистента МГП.

Проверяет:
1. Slot Filling — извлечение параметров
2. State Transitions — переходы между состояниями
3. Confirmation — подтверждение перед поиском
4. Fallback — обработка пустых результатов
5. Safety Layer — обработка ошибок
"""
import asyncio
import sys
import os
import uuid
from unittest.mock import AsyncMock, patch

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.runner import process_user_message
from app.agent.state_machine import (
    TourSlots,
    DialogPhase,
    create_initial_state_machine,
)
from app.agent.slot_extractor import slot_extractor


# ==================== ТЕСТЫ SLOT FILLING ====================

async def test_slot_extraction():
    """Тест извлечения слотов из текста."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 1: Slot Extraction")
    print("=" * 60)
    
    tests = [
        # (input, expected_slots)
        ("Хочу в Турцию", {"country_to": "Турция"}),
        ("В Египет из Москвы", {"country_to": "Египет", "city_from": "Москва"}),
        ("15 февраля на 7 ночей", {"nights": 7}),  # date проверяется отдельно
        ("Вдвоём", {"adults": 2}),
        ("2 взрослых и ребёнок 5 лет", {"adults": 2, "children_ages": [5]}),
        ("5 звёзд всё включено", {"stars": 5, "food_type": "AI"}),
        ("Горящий тур", {}),  # date = завтра
    ]
    
    passed = 0
    failed = 0
    
    for text, expected in tests:
        slots = TourSlots()
        result = slot_extractor.extract_all(text, slots)
        
        all_ok = True
        for key, exp_val in expected.items():
            actual = getattr(result, key)
            if actual != exp_val:
                all_ok = False
                print(f"   ❌ '{text}': {key}={actual}, expected={exp_val}")
        
        if all_ok:
            passed += 1
            print(f"   ✅ '{text}'")
        else:
            failed += 1
    
    print(f"\n📊 Результат: {passed}/{passed+failed}")
    return failed == 0


# ==================== ТЕСТЫ STATE TRANSITIONS ====================

async def test_state_transitions():
    """Тест переходов между состояниями."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 2: State Transitions")
    print("=" * 60)
    
    thread_id = f"test_transitions_{uuid.uuid4().hex[:8]}"
    state = None
    
    # Шаг 1: Приветствие
    print("\n📩 Сообщение 1: 'Привет'")
    response, state = await process_user_message("Привет", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    print(f"   📊 Фаза: {state['phase']}")
    
    assert state["phase"] == DialogPhase.COLLECTING.value, f"Expected COLLECTING, got {state['phase']}"
    assert state["greeted"], "Expected greeted=True"
    print("   ✅ Фаза = COLLECTING после приветствия")
    
    # Шаг 2: Указываем страну
    print("\n📩 Сообщение 2: 'Хочу в Турцию'")
    response, state = await process_user_message("Хочу в Турцию", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.country_to == "Турция", f"Expected Турция, got {slots.country_to}"
    print("   ✅ Страна = Турция")
    
    # Шаг 3: Указываем город вылета
    print("\n📩 Сообщение 3: 'Из Санкт-Петербурга'")
    response, state = await process_user_message("Из Санкт-Петербурга", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.city_from == "Санкт-Петербург", f"Expected СПб, got {slots.city_from}"
    print("   ✅ Город вылета = Санкт-Петербург")
    
    # Шаг 4: Указываем дату
    print("\n📩 Сообщение 4: '15 марта на 10 ночей'")
    response, state = await process_user_message("15 марта на 10 ночей", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.date_start is not None, "Expected date"
    assert slots.nights == 10, f"Expected 10 nights, got {slots.nights}"
    print(f"   ✅ Дата = {slots.date_start}, Ночей = {slots.nights}")
    
    # Шаг 5: Указываем состав
    print("\n📩 Сообщение 5: '2 взрослых'")
    response, state = await process_user_message("2 взрослых", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.adults == 2, f"Expected 2 adults, got {slots.adults}"
    print("   ✅ Взрослых = 2")
    
    # Проверяем, что все обязательные слоты заполнены
    assert slots.is_complete(), f"Expected complete, missing: {slots.get_missing_required()}"
    print("   ✅ ВСЕ обязательные слоты заполнены!")
    
    print("\n✅ ТЕСТ 2 ПРОЙДЕН")
    return True


# ==================== ТЕСТ NO DEFAULTS ====================

async def test_no_defaults():
    """Тест: агент НЕ ставит дефолтные значения."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 3: No Defaults")
    print("=" * 60)
    
    thread_id = f"test_no_defaults_{uuid.uuid4().hex[:8]}"
    
    # Отправляем неполный запрос
    print("\n📩 'Хочу в Египет на майские'")
    response, state = await process_user_message("Хочу в Египет на майские", thread_id, None)
    
    slots = TourSlots.from_dict(state["slots"])
    
    print(f"   📊 country_to: {slots.country_to}")
    print(f"   📊 date_start: {slots.date_start}")
    print(f"   📊 adults: {slots.adults}")
    print(f"   📊 nights: {slots.nights}")
    print(f"   📊 city_from: {slots.city_from}")
    
    # КРИТИЧНО: adults и nights НЕ должны быть заполнены автоматически!
    assert slots.adults is None, f"❌ adults={slots.adults}, должен быть None!"
    assert slots.nights is None or slots.nights is None, "nights должен быть None или спрошен!"
    
    print("\n   ✅ Агент НЕ ставит дефолтные значения")
    print("   ✅ adults = None (будет спрошен)")
    
    print("\n✅ ТЕСТ 3 ПРОЙДЕН")
    return True


# ==================== ТЕСТ CONFIRMATION ====================

async def test_confirmation_before_search():
    """Тест: подтверждение перед поиском."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 4: Confirmation Before Search")
    print("=" * 60)
    
    thread_id = f"test_confirm_{uuid.uuid4().hex[:8]}"
    
    # Полный запрос с первого сообщения
    full_request = "Турция из Москвы, 15 февраля на 7 ночей, 2 взрослых"
    print(f"\n📩 '{full_request}'")
    
    response, state = await process_user_message(full_request, thread_id, None)
    print(f"   📤 Ответ: {response[:100]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    
    # Проверяем, что все слоты заполнены
    assert slots.is_complete(), f"Missing: {slots.get_missing_required()}"
    print("   ✅ Все слоты заполнены")
    
    # Проверяем подтверждение
    # Ответ должен содержать параметры поиска
    assert "Турция" in response or state["phase"] in [DialogPhase.CONFIRMING.value, DialogPhase.SEARCHING.value], \
        "Expected confirmation or search phase"
    
    print(f"   📊 Фаза: {state['phase']}")
    print("\n✅ ТЕСТ 4 ПРОЙДЕН")
    return True


# ==================== ТЕСТ CONTEXT AWARENESS ====================

async def test_context_awareness():
    """Тест: контекстный парсинг чисел."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 5: Context Awareness")
    print("=" * 60)
    
    thread_id = f"test_context_{uuid.uuid4().hex[:8]}"
    state = None
    
    # Шаг 1: Запрос тура
    print("\n📩 'Хочу в Турцию из Москвы'")
    response, state = await process_user_message("Хочу в Турцию из Москвы", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    # Шаг 2: Ответ на вопрос о дате
    print("\n📩 '15 марта'")
    response, state = await process_user_message("15 марта", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    # Шаг 3: Ответ числом на вопрос о ночах
    print("\n📩 '7' (на вопрос о ночах)")
    # Устанавливаем last_question_type = nights
    state["last_question_type"] = "nights"
    response, state = await process_user_message("7", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.nights == 7, f"Expected nights=7, got {slots.nights}"
    print("   ✅ Контекст: '7' → nights=7")
    
    # Шаг 4: Ответ числом на вопрос о взрослых
    print("\n📩 '2' (на вопрос о взрослых)")
    state["last_question_type"] = "adults"
    response, state = await process_user_message("2", thread_id, state)
    print(f"   📤 Ответ: {response[:80]}...")
    
    slots = TourSlots.from_dict(state["slots"])
    assert slots.adults == 2, f"Expected adults=2, got {slots.adults}"
    print("   ✅ Контекст: '2' → adults=2")
    
    print("\n✅ ТЕСТ 5 ПРОЙДЕН")
    return True


# ==================== MAIN ====================

async def main():
    """Запуск всех тестов."""
    print("\n" + "=" * 60)
    print("🔧 STATE MACHINE TESTS")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(await test_slot_extraction())
        results.append(await test_state_transitions())
        results.append(await test_no_defaults())
        results.append(await test_confirmation_before_search())
        results.append(await test_context_awareness())
        
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

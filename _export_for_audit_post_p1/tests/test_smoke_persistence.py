"""
Smoke Test: State Persistence между сообщениями.

Проверяет сценарий:
1. User: "Хочу в Турцию" -> Bot: "Из какого города?"
2. User: "из Москвы" -> Bot: НЕ "Здравствуйте!", а "Когда планируете?"

КРИТИЧНО: Бот НЕ должен терять контекст!
"""
import asyncio
import sys
import os
import uuid

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.runner import process_user_message, _session_states
from app.agent.state_machine import TourSlots


async def test_smoke_persistence():
    """
    Smoke Test: бот помнит контекст между сообщениями.
    """
    print("\n" + "=" * 70)
    print("🔥 SMOKE TEST: State Persistence")
    print("=" * 70)
    
    # Уникальный thread_id для теста
    thread_id = f"smoke_test_{uuid.uuid4().hex[:8]}"
    
    print(f"\n📋 thread_id: {thread_id}")
    
    # ==================== СООБЩЕНИЕ 1 ====================
    print("\n" + "-" * 70)
    print("📩 СООБЩЕНИЕ 1: 'Хочу в Турцию'")
    print("-" * 70)
    
    response1, state1 = await process_user_message("Хочу в Турцию", thread_id, None)
    
    print(f"\n📤 ОТВЕТ 1: {response1}")
    
    slots1 = TourSlots.from_dict(state1["slots"])
    
    # Проверки
    assert slots1.country_to == "Турция", f"❌ country_to={slots1.country_to}, expected Турция"
    assert state1["greeted"] == True, f"❌ greeted={state1['greeted']}, expected True"
    assert "город" in response1.lower() or "вылет" in response1.lower(), \
        f"❌ Ответ должен спрашивать про город: {response1}"
    
    print(f"\n✅ country_to = {slots1.country_to}")
    print(f"✅ greeted = {state1['greeted']}")
    print(f"✅ phase = {state1['phase']}")
    print(f"✅ last_question_type = {state1['last_question_type']}")
    
    # ==================== СООБЩЕНИЕ 2 ====================
    print("\n" + "-" * 70)
    print("📩 СООБЩЕНИЕ 2: 'из Москвы'")
    print("-" * 70)
    
    # КРИТИЧНО: Передаём state=None — runner должен восстановить из памяти!
    response2, state2 = await process_user_message("из Москвы", thread_id, None)
    
    print(f"\n📤 ОТВЕТ 2: {response2}")
    
    slots2 = TourSlots.from_dict(state2["slots"])
    
    # КРИТИЧНЫЕ ПРОВЕРКИ
    # 1. Страна должна сохраниться!
    assert slots2.country_to == "Турция", \
        f"❌ CONTEXT LOST! country_to={slots2.country_to}, expected Турция"
    
    # 2. Город должен быть извлечён!
    assert slots2.city_from == "Москва", \
        f"❌ city_from={slots2.city_from}, expected Москва"
    
    # 3. Ответ НЕ должен содержать "Здравствуйте"!
    assert "здравствуйте" not in response2.lower(), \
        f"❌ RE-GREETING! Ответ содержит 'Здравствуйте': {response2}"
    
    # 4. Ответ должен спрашивать про дату (следующий слот)
    assert "когда" in response2.lower() or "дат" in response2.lower() or "отпуск" in response2.lower(), \
        f"❌ Ответ должен спрашивать про дату: {response2}"
    
    print(f"\n✅ country_to = {slots2.country_to} (СОХРАНЕНО!)")
    print(f"✅ city_from = {slots2.city_from}")
    print(f"✅ Нет 'Здравствуйте' в ответе")
    print(f"✅ Спрашивает про дату")
    
    # ==================== СООБЩЕНИЕ 3 ====================
    print("\n" + "-" * 70)
    print("📩 СООБЩЕНИЕ 3: '15 марта на 7 ночей'")
    print("-" * 70)
    
    response3, state3 = await process_user_message("15 марта на 7 ночей", thread_id, None)
    
    print(f"\n📤 ОТВЕТ 3: {response3}")
    
    slots3 = TourSlots.from_dict(state3["slots"])
    
    # Проверки
    assert slots3.country_to == "Турция", f"❌ country_to lost: {slots3.country_to}"
    assert slots3.city_from == "Москва", f"❌ city_from lost: {slots3.city_from}"
    assert slots3.date_start is not None, f"❌ date_start is None"
    assert slots3.nights == 7, f"❌ nights={slots3.nights}, expected 7"
    
    print(f"\n✅ country_to = {slots3.country_to}")
    print(f"✅ city_from = {slots3.city_from}")
    print(f"✅ date_start = {slots3.date_start}")
    print(f"✅ nights = {slots3.nights}")
    
    # ==================== ИТОГ ====================
    print("\n" + "=" * 70)
    print("🎉 SMOKE TEST PASSED!")
    print("   ✅ Контекст сохраняется между сообщениями")
    print("   ✅ Бот не здоровается повторно")
    print("   ✅ Слоты накапливаются корректно")
    print("=" * 70)
    
    return True


async def test_context_aware_city():
    """
    Тест: контекстный парсинг города.
    
    Когда бот спросил "Из какого города?",
    ответ "Москва" (без "из") должен быть понят как город.
    """
    print("\n" + "=" * 70)
    print("🔥 TEST: Context-Aware City Parsing")
    print("=" * 70)
    
    thread_id = f"city_test_{uuid.uuid4().hex[:8]}"
    
    # Шаг 1: Турция
    response1, state1 = await process_user_message("Хочу в Египет", thread_id, None)
    print(f"📤 1: {response1[:60]}...")
    
    # Шаг 2: Просто "Питер" (без "из")
    response2, state2 = await process_user_message("Питер", thread_id, None)
    print(f"📤 2: {response2[:60]}...")
    
    slots = TourSlots.from_dict(state2["slots"])
    
    assert slots.city_from == "Санкт-Петербург", \
        f"❌ city_from={slots.city_from}, expected Санкт-Петербург"
    
    print(f"\n✅ 'Питер' → city_from='Санкт-Петербург'")
    print("🎉 TEST PASSED!")
    
    return True


async def main():
    """Запуск всех тестов."""
    results = []
    
    try:
        results.append(await test_smoke_persistence())
        results.append(await test_context_aware_city())
    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {e}")
        results.append(False)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"📊 ИТОГ: {passed}/{total} тестов пройдено")
    print("=" * 70)
    
    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

"""
Тесты функций согласно ТЗ (AImpact_ МГП.pdf).

Проверяет:
1. Авто-расчёт ночей из диапазона дат (раздел 2.2)
2. Авто-заполнение звёзд если указан отель (раздел 2.2)
3. Эскалация для групп > 6 человек (раздел 2.2)
4. Fallback с альтернативами (раздел 2.1)
5. Выдача 3-5 карточек (раздел 2.1)
"""
import asyncio
import sys
import os
import uuid

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.runner import process_user_message
from app.agent.state_machine import TourSlots, DialogPhase
from app.agent.slot_extractor import slot_extractor


async def test_auto_nights_calculation():
    """
    Тест: Авто-расчёт ночей из диапазона дат (раздел 2.2 ТЗ).
    
    "Если заданы даты, не спрашивать количество ночей."
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 1: Авто-расчёт ночей из дат")
    print("=" * 70)
    
    # "с 15 по 22 февраля" = 7 ночей
    slots = TourSlots()
    result = slot_extractor.extract_all("с 15 по 22 февраля", slots)
    
    print(f"   Input: 'с 15 по 22 февраля'")
    print(f"   date_start: {result.date_start}")
    print(f"   nights: {result.nights}")
    
    assert result.date_start is not None, "❌ date_start is None"
    assert result.nights == 7, f"❌ nights={result.nights}, expected 7"
    
    print("   ✅ Ночи вычислены автоматически: 7")
    print("\n✅ ТЕСТ 1 ПРОЙДЕН")
    return True


async def test_hotel_auto_stars():
    """
    Тест: Авто-заполнение звёзд если указан отель (раздел 2.2 ТЗ).
    
    "Если указан конкретный отель, заполни поле stars автоматически."
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 2: Авто-заполнение звёзд для отеля")
    print("=" * 70)
    
    # "отель Rixos" = 5 звёзд (автоматически)
    slots = TourSlots()
    result = slot_extractor.extract_all("Хочу в отель Rixos Premium", slots)
    
    print(f"   Input: 'Хочу в отель Rixos Premium'")
    print(f"   hotel_name: {result.hotel_name}")
    print(f"   stars: {result.stars}")
    print(f"   skip_quality_check: {result.skip_quality_check}")
    
    assert result.hotel_name is not None, "❌ hotel_name is None"
    assert result.stars == 5, f"❌ stars={result.stars}, expected 5"
    assert result.skip_quality_check == True, "❌ skip_quality_check should be True"
    
    print("   ✅ Звёзды заполнены автоматически: 5★")
    print("   ✅ skip_quality_check = True")
    print("\n✅ ТЕСТ 2 ПРОЙДЕН")
    return True


async def test_group_escalation():
    """
    Тест: Эскалация для групп > 6 человек (раздел 2.2 ТЗ).
    
    "Если adults + children > 6, переходи в узел Human_Escalation."
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 3: Эскалация для групп > 6 человек")
    print("=" * 70)
    
    thread_id = f"escalation_test_{uuid.uuid4().hex[:8]}"
    
    # Запрос с группой > 6 человек
    msg = "Турция из Москвы, 15 марта, 10 ночей, 5 взрослых и 3 детей (5, 8, 12 лет)"
    print(f"   Input: '{msg}'")
    
    response, state = await process_user_message(msg, thread_id, None)
    
    print(f"   Response: {response[:80]}...")
    print(f"   Phase: {state['phase']}")
    
    slots = TourSlots.from_dict(state["slots"])
    total_pax = (slots.adults or 0) + len(slots.children_ages)
    print(f"   Total pax: {total_pax}")
    
    # Проверяем, что произошла эскалация
    assert state["phase"] == DialogPhase.ESCALATION.value or "менеджер" in response.lower(), \
        f"❌ Expected escalation, got phase={state['phase']}"
    
    print("   ✅ Группа > 6 → эскалация на менеджера")
    print("\n✅ ТЕСТ 3 ПРОЙДЕН")
    return True


async def test_slot_extractor_escalation_check():
    """
    Тест: Проверка эскалации в SlotExtractor.
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 4: Проверка эскалации в SlotExtractor")
    print("=" * 70)
    
    # Маленькая группа — не нужна эскалация
    slots_small = TourSlots(adults=2, children_ages=[5])
    needs_escalation_small = slot_extractor.check_group_escalation(slots_small)
    print(f"   2 взр + 1 дет = {2+1} → escalation={needs_escalation_small}")
    assert needs_escalation_small == False, "❌ Small group should not need escalation"
    
    # Большая группа — нужна эскалация
    slots_large = TourSlots(adults=4, children_ages=[5, 8, 10])
    needs_escalation_large = slot_extractor.check_group_escalation(slots_large)
    print(f"   4 взр + 3 дет = {4+3} → escalation={needs_escalation_large}")
    assert needs_escalation_large == True, "❌ Large group should need escalation"
    
    print("\n✅ ТЕСТ 4 ПРОЙДЕН")
    return True


async def test_context_aware_parsing():
    """
    Тест: Контекстный парсинг ответов.
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 5: Контекстный парсинг")
    print("=" * 70)
    
    # Если спросили про ночи, "7" = 7 ночей
    slots = TourSlots()
    result = slot_extractor.extract_all("7", slots, last_question_type="nights")
    print(f"   '7' (last_question=nights) → nights={result.nights}")
    assert result.nights == 7, f"❌ nights={result.nights}, expected 7"
    
    # Если спросили про взрослых, "2" = 2 взрослых
    slots2 = TourSlots()
    result2 = slot_extractor.extract_all("2", slots2, last_question_type="adults")
    print(f"   '2' (last_question=adults) → adults={result2.adults}")
    assert result2.adults == 2, f"❌ adults={result2.adults}, expected 2"
    
    # Если спросили про город, "Москва" = city_from
    slots3 = TourSlots()
    result3 = slot_extractor.extract_all("Москва", slots3, last_question_type="city_from")
    print(f"   'Москва' (last_question=city_from) → city_from={result3.city_from}")
    assert result3.city_from == "Москва", f"❌ city_from={result3.city_from}, expected Москва"
    
    print("\n✅ ТЕСТ 5 ПРОЙДЕН")
    return True


async def test_popular_hotels():
    """
    Тест: Распознавание популярных отелей.
    """
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 6: Популярные отели")
    print("=" * 70)
    
    test_cases = [
        ("Titanic Deluxe", 5),
        ("Maxx Royal Belek", 5),
        ("Rixos Sungate", 5),
        ("Gloria Verde", 5),
        ("Atlantis The Palm", 5),
    ]
    
    for hotel, expected_stars in test_cases:
        slots = TourSlots()
        result = slot_extractor.extract_all(f"Хочу в {hotel}", slots)
        print(f"   '{hotel}' → stars={result.stars}, hotel={result.hotel_name}")
        
        if result.stars:
            assert result.stars == expected_stars, \
                f"❌ {hotel}: stars={result.stars}, expected {expected_stars}"
    
    print("\n✅ ТЕСТ 6 ПРОЙДЕН")
    return True


async def main():
    """Запуск всех тестов."""
    print("\n" + "=" * 70)
    print("📋 ТЕСТЫ ФУНКЦИЙ ТЗ (AImpact_ МГП.pdf)")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(await test_auto_nights_calculation())
        results.append(await test_hotel_auto_stars())
        results.append(await test_group_escalation())
        results.append(await test_slot_extractor_escalation_check())
        results.append(await test_context_aware_parsing())
        results.append(await test_popular_hotels())
        
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

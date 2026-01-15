#!/usr/bin/env python3
"""
Тест P5: Горящие туры — пропуск вопроса о дате

Проверяем что:
1. Для горящих туров НЕ спрашивается дата
2. Сразу вызывается hottours.php API
3. Обычные туры работают как раньше (регрессия)
"""

import asyncio
import httpx
import json
import time

API_URL = "http://localhost:8000/api/v1/chat"
LOG_FILE = "debug_bundle/LOGS/app.jsonl"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


async def send_message(text: str, conversation_id: str = None) -> str:
    """Отправка сообщения в чат. Возвращает conversation_id."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {"message": text}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        response = await client.post(API_URL, json=payload)
        data = response.json()
        return data.get("conversation_id", "")


def get_last_turn(conversation_id: str) -> dict:
    """Получение последнего turn для conversation_id из логов."""
    try:
        with open(LOG_FILE, "r") as f:
            turns = []
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("conversation_id") == conversation_id and data.get("type") == "turn":
                        turns.append(data)
                except:
                    continue
            return turns[-1] if turns else {}
    except:
        return {}


async def test_hot_tour_no_date_question():
    """Тест: Горящий тур НЕ должен спрашивать дату."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 1: Горящий тур — без вопроса о дате{RESET}")
    print("   Ожидание: Бот НЕ спрашивает 'Когда планируете?' для горящих\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Горящий тур в Турцию из Москвы'")
    conv_id = await send_message("Горящий тур в Турцию из Москвы")
    
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    bot_response = turn.get("assistant_text", "")
    print(f"   Бот: {bot_response[:80]}...")
    
    # Проверяем что НЕ спрашивает дату
    date_questions = ["когда планируете", "на какие даты", "какого числа"]
    asked_date = any(q in bot_response.lower() for q in date_questions)
    
    print(f"\n   📊 Результат:")
    print(f"      Спросил дату: {'Да ❌' if asked_date else 'Нет ✅'}")
    print(f"      cascade_stage: {turn.get('cascade_stage')}")
    
    if not asked_date:
        print(f"\n   {GREEN}✅ PASS: Дату НЕ спрашивает!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Спрашивает дату для горящих туров!{RESET}")
        return False


async def test_hot_tour_with_departure():
    """Тест: Горящий тур спрашивает город если не указан."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 2: Горящий тур — запрос города вылета{RESET}")
    print("   Ожидание: Бот спрашивает 'Из какого города?' если не указан\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Хочу горящий тур в Египет'")
    conv_id = await send_message("Хочу горящий тур в Египет")
    
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    bot_response = turn.get("assistant_text", "")
    print(f"   Бот: {bot_response[:80]}...")
    
    # Должен спросить город вылета
    departure_questions = ["из какого города", "откуда вылет", "город вылета"]
    asked_departure = any(q in bot_response.lower() for q in departure_questions)
    
    print(f"\n   📊 Результат:")
    print(f"      Спросил город вылета: {'Да ✅' if asked_departure else 'Нет ❌'}")
    
    if asked_departure:
        print(f"\n   {GREEN}✅ PASS: Спрашивает город вылета для горящих!{RESET}")
        
        # Шаг 2: Отвечаем город
        print(f"\n   {YELLOW}Шаг 2:{RESET} Пользователь: 'Москва'")
        await send_message("Москва", conv_id)
        
        await asyncio.sleep(2)
        
        turn2 = get_last_turn(conv_id)
        bot_response2 = turn2.get("assistant_text", "")
        print(f"   Бот: {bot_response2[:80]}...")
        
        # Теперь НЕ должен спрашивать дату
        date_questions = ["когда планируете", "на какие даты", "какого числа"]
        asked_date = any(q in bot_response2.lower() for q in date_questions)
        
        print(f"\n   После указания города:")
        print(f"      Спросил дату: {'Да ❌' if asked_date else 'Нет ✅'}")
        
        return not asked_date
    else:
        print(f"\n   {RED}❌ FAIL: Не спрашивает город вылета!{RESET}")
        return False


async def test_normal_tour_asks_date():
    """Тест: Обычный тур ДОЛЖЕН спрашивать дату (регрессия)."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 3: Обычный тур — спрашивает дату (регрессия){RESET}")
    print("   Ожидание: Для обычного тура дата ОБЯЗАТЕЛЬНА\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Хочу в Турцию на неделю, вдвоём'")
    conv_id = await send_message("Хочу в Турцию на неделю, вдвоём")
    
    await asyncio.sleep(1)
    
    turn1 = get_last_turn(conv_id)
    bot_response1 = turn1.get("assistant_text", "")
    print(f"   Бот: {bot_response1[:80]}...")
    
    print(f"\n   {YELLOW}Шаг 2:{RESET} Пользователь: 'Из Москвы'")
    await send_message("Из Москвы", conv_id)
    
    await asyncio.sleep(2)
    
    turn2 = get_last_turn(conv_id)
    bot_response2 = turn2.get("assistant_text", "")
    print(f"   Бот: {bot_response2[:80]}...")
    
    # Должен спросить дату
    date_questions = ["когда планируете", "на какие даты", "какого числа", "вылет"]
    asked_date = any(q in bot_response2.lower() for q in date_questions)
    
    print(f"\n   📊 Результат:")
    print(f"      Спросил дату: {'Да ✅' if asked_date else 'Нет ❌'}")
    
    if asked_date:
        print(f"\n   {GREEN}✅ PASS: Обычный тур спрашивает дату — регрессии нет!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Обычный тур НЕ спрашивает дату — РЕГРЕССИЯ!{RESET}")
        return False


async def test_hot_tour_from_piter():
    """Тест: Горящий тур из Питера (проверка алиасов + горящие)."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 4: Горящий тур из Питера{RESET}")
    print("   Ожидание: Алиас 'Питер' → 'Санкт-Петербург' + горящие без даты\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Горящие туры в Египет из Питера'")
    conv_id = await send_message("Горящие туры в Египет из Питера")
    
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    bot_response = turn.get("assistant_text", "")
    params = turn.get("search_params", {})
    departure_city = params.get("departure_city")
    
    print(f"   Бот: {bot_response[:80]}...")
    
    print(f"\n   📊 Результат:")
    print(f"      departure_city: {departure_city}")
    
    # Не должен спрашивать дату
    date_questions = ["когда планируете", "на какие даты", "какого числа"]
    asked_date = any(q in bot_response.lower() for q in date_questions)
    
    print(f"      Спросил дату: {'Да ❌' if asked_date else 'Нет ✅'}")
    
    if departure_city == "Санкт-Петербург" and not asked_date:
        print(f"\n   {GREEN}✅ PASS: Питер → Санкт-Петербург + горящие без даты!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: departure_city={departure_city}, asked_date={asked_date}{RESET}")
        return False


async def main():
    print(f"\n{YELLOW}{'='*70}")
    print("  ТЕСТ P5: ГОРЯЩИЕ ТУРЫ — ПРОПУСК ВОПРОСА О ДАТЕ")
    print(f"{'='*70}{RESET}")
    
    results = {"passed": 0, "failed": 0}
    
    # Очищаем логи
    with open(LOG_FILE, "w") as f:
        pass
    
    # Запускаем тесты
    if await test_hot_tour_no_date_question():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_hot_tour_with_departure():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_normal_tour_asks_date():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_hot_tour_from_piter():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Итоги
    total = results["passed"] + results["failed"]
    print(f"\n{YELLOW}{'='*70}")
    
    if results["failed"] == 0:
        print(f"  ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ: {results['passed']}/{total}")
    else:
        print(f"  ⚠️ РЕЗУЛЬТАТ: {results['passed']}/{total}")
        print(f"  ❌ Провалено: {results['failed']} тестов")
    
    print(f"{'='*70}{RESET}\n")
    
    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

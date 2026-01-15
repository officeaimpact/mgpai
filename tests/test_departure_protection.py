#!/usr/bin/env python3
"""
Тест P4: Защита destination_country от перезаписи при вопросе о городе вылета

Проблема: Когда бот спрашивает "Из какого города вылет?", а пользователь отвечает 
"Сочи" (или другой город, который является и городом вылета, и курортом),
destination_country НЕ должна перезаписываться.

Сценарий:
1. Пользователь: "Хочу в Турцию" → destination_country = "Турция"
2. Бот: "Из какого города вылет?"
3. Пользователь: "Сочи"
4. ПРАВИЛЬНО: departure_city = "Сочи", destination_country = "Турция" (без изменений)
5. БЫЛО (баг): departure_city = "Сочи", destination_country = "Россия" ← ПЕРЕЗАПИСЬ!
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


async def send_message(text: str, conversation_id: str = None) -> dict:
    """Отправка сообщения в чат."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {"message": text}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        response = await client.post(API_URL, json=payload)
        return response.json()


def get_logs_for_conversation(conversation_id: str) -> list:
    """Получение всех логов для conversation_id."""
    logs = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("conversation_id") == conversation_id:
                        logs.append(data)
                except:
                    continue
    except:
        pass
    return logs


async def test_sochi_scenario():
    """Тест: Сочи как город вылета не должен менять страну."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 1: Турция из Сочи{RESET}")
    print("   Ожидание: destination_country='Турция' сохраняется при ответе 'Сочи'\n")
    
    # Шаг 1: Начинаем диалог
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Хочу в Турцию на 7 ночей, вдвоём'")
    response1 = await send_message("Хочу в Турцию на 7 ночей, вдвоём")
    conv_id = response1.get("conversation_id")
    print(f"   Бот: {response1.get('response', '')[:60]}...")
    
    await asyncio.sleep(1)
    
    # Шаг 2: Отвечаем "Сочи"
    print(f"   {YELLOW}Шаг 2:{RESET} Пользователь: 'Сочи'")
    response2 = await send_message("Сочи", conv_id)
    print(f"   Бот: {response2.get('response', '')[:60]}...")
    
    await asyncio.sleep(2)
    
    # Проверяем логи
    logs = get_logs_for_conversation(conv_id)
    
    # Находим последний turn
    last_turn = None
    for log in reversed(logs):
        if log.get("type") == "turn":
            last_turn = log
            break
    
    if not last_turn:
        print(f"   {RED}❌ FAIL: Логи не найдены{RESET}")
        return False
    
    params = last_turn.get("search_params", {})
    destination = params.get("destination_country")
    departure = params.get("departure_city")
    
    print(f"\n   📊 Результат:")
    print(f"      destination_country: {destination}")
    print(f"      departure_city: {departure}")
    
    # Проверка
    if destination == "Турция" and departure == "Сочи":
        print(f"\n   {GREEN}✅ PASS: Страна защищена от перезаписи!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Страна перезаписана на '{destination}'!{RESET}")
        return False


async def test_anapa_scenario():
    """Тест: Анапа как город вылета не должен менять страну."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 2: Египет из Анапы{RESET}")
    print("   Ожидание: destination_country='Египет' сохраняется при ответе 'Анапа'\n")
    
    # Шаг 1: Начинаем диалог
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'В Египет на неделю, 2 взрослых'")
    response1 = await send_message("В Египет на неделю, 2 взрослых")
    conv_id = response1.get("conversation_id")
    print(f"   Бот: {response1.get('response', '')[:60]}...")
    
    await asyncio.sleep(1)
    
    # Шаг 2: Отвечаем "Анапа"
    print(f"   {YELLOW}Шаг 2:{RESET} Пользователь: 'Анапа'")
    response2 = await send_message("Анапа", conv_id)
    print(f"   Бот: {response2.get('response', '')[:60]}...")
    
    await asyncio.sleep(2)
    
    # Проверяем логи
    logs = get_logs_for_conversation(conv_id)
    last_turn = None
    for log in reversed(logs):
        if log.get("type") == "turn":
            last_turn = log
            break
    
    if not last_turn:
        print(f"   {RED}❌ FAIL: Логи не найдены{RESET}")
        return False
    
    params = last_turn.get("search_params", {})
    destination = params.get("destination_country")
    departure = params.get("departure_city")
    
    print(f"\n   📊 Результат:")
    print(f"      destination_country: {destination}")
    print(f"      departure_city: {departure}")
    
    if destination == "Египет" and departure == "Анапа":
        print(f"\n   {GREEN}✅ PASS: Страна защищена от перезаписи!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Страна перезаписана на '{destination}'!{RESET}")
        return False


async def test_simferopol_scenario():
    """Тест: Симферополь как город вылета не должен менять страну."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 3: ОАЭ из Симферополя{RESET}")
    print("   Ожидание: destination_country='ОАЭ' сохраняется\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Хочу в ОАЭ на 10 ночей, вдвоём'")
    response1 = await send_message("Хочу в ОАЭ на 10 ночей, вдвоём")
    conv_id = response1.get("conversation_id")
    print(f"   Бот: {response1.get('response', '')[:60]}...")
    
    await asyncio.sleep(1)
    
    print(f"   {YELLOW}Шаг 2:{RESET} Пользователь: 'Симферополь'")
    response2 = await send_message("Симферополь", conv_id)
    print(f"   Бот: {response2.get('response', '')[:60]}...")
    
    await asyncio.sleep(2)
    
    logs = get_logs_for_conversation(conv_id)
    last_turn = None
    for log in reversed(logs):
        if log.get("type") == "turn":
            last_turn = log
            break
    
    if not last_turn:
        print(f"   {RED}❌ FAIL: Логи не найдены{RESET}")
        return False
    
    params = last_turn.get("search_params", {})
    destination = params.get("destination_country")
    departure = params.get("departure_city")
    
    print(f"\n   📊 Результат:")
    print(f"      destination_country: {destination}")
    print(f"      departure_city: {departure}")
    
    if destination == "ОАЭ" and departure == "Симферополь":
        print(f"\n   {GREEN}✅ PASS: Страна защищена от перезаписи!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Страна перезаписана на '{destination}'!{RESET}")
        return False


async def test_normal_scenario():
    """Тест: Нормальный город вылета (Москва) — регрессия."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 4: Регрессия — Москва (нормальный город){RESET}")
    print("   Ожидание: Всё работает как раньше\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Турция на неделю, вдвоём'")
    response1 = await send_message("Турция на неделю, вдвоём")
    conv_id = response1.get("conversation_id")
    print(f"   Бот: {response1.get('response', '')[:60]}...")
    
    await asyncio.sleep(1)
    
    print(f"   {YELLOW}Шаг 2:{RESET} Пользователь: 'Из Москвы'")
    response2 = await send_message("Из Москвы", conv_id)
    print(f"   Бот: {response2.get('response', '')[:60]}...")
    
    await asyncio.sleep(2)
    
    logs = get_logs_for_conversation(conv_id)
    last_turn = None
    for log in reversed(logs):
        if log.get("type") == "turn":
            last_turn = log
            break
    
    if not last_turn:
        print(f"   {RED}❌ FAIL: Логи не найдены{RESET}")
        return False
    
    params = last_turn.get("search_params", {})
    destination = params.get("destination_country")
    departure = params.get("departure_city")
    
    print(f"\n   📊 Результат:")
    print(f"      destination_country: {destination}")
    print(f"      departure_city: {departure}")
    
    if destination == "Турция" and departure == "Москва":
        print(f"\n   {GREEN}✅ PASS: Регрессия — работает как раньше!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: Что-то сломалось!{RESET}")
        return False


async def test_first_message_sochi():
    """Тест: Сочи в первом сообщении КАК НАПРАВЛЕНИЕ — должен работать."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 5: Сочи как НАПРАВЛЕНИЕ (в первом сообщении){RESET}")
    print("   Ожидание: destination='Россия', resort='Сочи' — защита НЕ срабатывает\n")
    
    print(f"   {YELLOW}Шаг 1:{RESET} Пользователь: 'Хочу в Сочи на неделю'")
    response1 = await send_message("Хочу в Сочи на неделю, вдвоём, из Москвы, 15 июня")
    conv_id = response1.get("conversation_id")
    print(f"   Бот: {response1.get('response', '')[:60]}...")
    
    await asyncio.sleep(2)
    
    logs = get_logs_for_conversation(conv_id)
    last_turn = None
    for log in reversed(logs):
        if log.get("type") == "turn":
            last_turn = log
            break
    
    if not last_turn:
        print(f"   {RED}❌ FAIL: Логи не найдены{RESET}")
        return False
    
    params = last_turn.get("search_params", {})
    destination = params.get("destination_country")
    resort = params.get("destination_resort")
    
    print(f"\n   📊 Результат:")
    print(f"      destination_country: {destination}")
    print(f"      destination_resort: {resort}")
    
    # В первом сообщении защита не должна срабатывать
    if destination == "Россия" and resort == "Сочи":
        print(f"\n   {GREEN}✅ PASS: Сочи как направление работает!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: destination={destination}, resort={resort}{RESET}")
        return False


async def main():
    print(f"\n{YELLOW}{'='*70}")
    print("  ТЕСТ P4: ЗАЩИТА DESTINATION ОТ ПЕРЕЗАПИСИ")
    print(f"{'='*70}{RESET}")
    
    results = {"passed": 0, "failed": 0}
    
    # Очищаем логи
    with open(LOG_FILE, "w") as f:
        pass
    
    # Запускаем тесты
    if await test_sochi_scenario():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_anapa_scenario():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_simferopol_scenario():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_normal_scenario():
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if await test_first_message_sochi():
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

#!/usr/bin/env python3
"""
Тест исправления P2: hotel_name="null" фильтрация

Проверяем что:
1. hotel_name="null" от LLM игнорируется
2. Реальные названия отелей работают
3. Поиск без hotel_name проходит успешно
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
        
        for attempt in range(3):
            try:
                response = await client.post(API_URL, json=payload)
                return response.json()
            except Exception as e:
                if attempt < 2:
                    print(f"   Retry {attempt + 1}...")
                    await asyncio.sleep(2)
                else:
                    raise


def get_last_turn_log() -> dict:
    """Получение последнего turn из логов."""
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        
        for line in reversed(lines):
            try:
                data = json.loads(line)
                if data.get("type") == "turn":
                    return data
            except:
                continue
    except:
        pass
    return {}


async def run_test(name: str, message: str, check_fn) -> bool:
    """Запуск теста."""
    print(f"\n{BLUE}▶ {name}{RESET}")
    print(f"  Запрос: \"{message}\"")
    
    try:
        await send_message(message)
        await asyncio.sleep(2)  # Ждём записи в лог
        
        turn = get_last_turn_log()
        search_params = turn.get("search_params", {})
        assistant_text = turn.get("assistant_text", "")
        
        result = check_fn(search_params, assistant_text)
        
        if result["passed"]:
            print(f"  {GREEN}✅ PASS: {result['message']}{RESET}")
            return True
        else:
            print(f"  {RED}❌ FAIL: {result['message']}{RESET}")
            return False
            
    except Exception as e:
        print(f"  {RED}❌ ERROR: {e}{RESET}")
        return False


async def main():
    print(f"\n{YELLOW}{'='*60}")
    print("  ТЕСТ P2: hotel_name='null' ФИЛЬТРАЦИЯ")
    print(f"{'='*60}{RESET}\n")
    
    results = {"passed": 0, "failed": 0}
    
    # Тест 1: Белек без отеля — hotel_name должен быть None/отсутствовать
    if await run_test(
        "T1: Белек без отеля (hotel_name='null' должен игнорироваться)",
        "Белек, июнь, 2 взрослых, из Москвы на неделю, 5 звёзд AI",
        lambda params, text: {
            "passed": params.get("hotel_name") in (None, ""),
            "message": f"hotel_name={params.get('hotel_name')} (ожидалось None или отсутствие)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест 2: Турция со звёздами — hotel_name не должен быть "null"
    if await run_test(
        "T2: Турция 5 звёзд (без явного отеля)",
        "Турция из Москвы на 10 ночей с 1 июля, вдвоём, 5 звёзд",
        lambda params, text: {
            "passed": params.get("hotel_name") != "null",
            "message": f"hotel_name={params.get('hotel_name')} (не должен быть 'null')"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест 3: Реальный отель — должен сохраняться
    if await run_test(
        "T3: Реальный отель Rixos (должен сохраниться)",
        "Rixos Premium Belek из Москвы, июль, вдвоём",
        lambda params, text: {
            "passed": "rixos" in str(params.get("hotel_name", "")).lower(),
            "message": f"hotel_name={params.get('hotel_name')} (ожидался Rixos)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест 4: Проверяем что поиск проходит (нет ошибки)
    if await run_test(
        "T4: Поиск выполняется (нет 'Не удалось выполнить')",
        "Египет из Москвы на 7 ночей, 15 февраля, вдвоём, 4 звезды",
        lambda params, text: {
            "passed": "Не удалось выполнить поиск" not in text and "ошибка" not in text.lower(),
            "message": f"Ответ: {text[:80]}..."
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Итоги
    print(f"\n{YELLOW}{'='*60}")
    print(f"  ИТОГИ: {results['passed']}/{results['passed'] + results['failed']} тестов пройдено")
    print(f"{'='*60}{RESET}\n")
    
    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

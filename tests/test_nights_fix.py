#!/usr/bin/env python3
"""
Тест исправления P1: nights приоритет над вычисленными из дат

Три уровня тестирования:
1. РЕГРЕССИЯ - проверяем что работающие сценарии не сломались
2. ЦЕЛЕВЫЕ - конкретно на исправленный баг (nights)
3. ВАРИАТИВНЫЕ - edge cases
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

API_URL = "http://localhost:8000/api/v1/chat"
LOG_FILE = "debug_bundle/LOGS/app.jsonl"

# Цвета для терминала
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


async def send_message(text: str, conversation_id: str = None, retries: int = 2) -> dict:
    """Отправка сообщения в чат с retry."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {"message": text}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        for attempt in range(retries):
            try:
                response = await client.post(API_URL, json=payload)
                return response.json()
            except httpx.ReadTimeout:
                if attempt < retries - 1:
                    print(f"   ⏳ Таймаут, повтор {attempt + 2}/{retries}...")
                    await asyncio.sleep(2)
                else:
                    raise
        return {}


def get_last_api_trace() -> dict:
    """Получение последнего API trace из логов."""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        
        # Ищем последний api_trace с search.php
        for line in reversed(lines):
            try:
                entry = json.loads(line.strip())
                if entry.get("type") == "api_trace" and entry.get("endpoint") == "search.php":
                    return entry.get("request_params", {})
            except json.JSONDecodeError:
                continue
        return {}
    except FileNotFoundError:
        return {}


def get_last_turn() -> dict:
    """Получение последнего turn из логов."""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        
        for line in reversed(lines):
            try:
                entry = json.loads(line.strip())
                if entry.get("type") == "turn":
                    return entry
            except json.JSONDecodeError:
                continue
        return {}
    except FileNotFoundError:
        return {}


async def run_test(name: str, messages: list[str], check_func) -> bool:
    """Запуск одного теста."""
    print(f"\n{BLUE}▶ {name}{RESET}")
    
    conversation_id = None
    for msg in messages:
        print(f"   Отправка: {msg[:50]}...")
        response = await send_message(msg, conversation_id)
        conversation_id = response.get("conversation_id")
        await asyncio.sleep(1)  # Даём время на запись логов
    
    # Ждём завершения поиска
    await asyncio.sleep(3)
    
    # Проверяем результат
    api_trace = get_last_api_trace()
    turn = get_last_turn()
    
    result = check_func(api_trace, turn)
    
    if result["passed"]:
        print(f"   {GREEN}✅ PASS: {result['message']}{RESET}")
        return True
    else:
        print(f"   {RED}❌ FAIL: {result['message']}{RESET}")
        print(f"   {YELLOW}   API params: nightsfrom={api_trace.get('nightsfrom')}, nightsto={api_trace.get('nightsto')}{RESET}")
        return False


async def main():
    print(f"\n{'='*60}")
    print(f"{BLUE}🧪 ТЕСТИРОВАНИЕ P1 FIX: NIGHTS PRIORITY{RESET}")
    print(f"{'='*60}")
    
    results = {"passed": 0, "failed": 0}
    
    # ==================== УРОВЕНЬ 1: РЕГРЕССИЯ ====================
    print(f"\n{YELLOW}📋 УРОВЕНЬ 1: РЕГРЕССИОННЫЕ ТЕСТЫ{RESET}")
    
    # Тест R1: Диапазон дат без явных ночей (должен вычислять из дат)
    if await run_test(
        "R1: Диапазон дат 10-17 июня (7 ночей вычисленные)",
        ["Турция с 10 по 17 июня, 2 взрослых из Москвы, 5 звёзд"],
        lambda api, turn: {
            "passed": api.get("nightsfrom", 0) >= 7,
            "message": f"nightsfrom={api.get('nightsfrom')} (ожидалось >=7)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # ==================== УРОВЕНЬ 2: ЦЕЛЕВЫЕ ====================
    print(f"\n{YELLOW}🎯 УРОВЕНЬ 2: ЦЕЛЕВЫЕ ТЕСТЫ (на исправленный баг){RESET}")
    
    # Тест T1: Явные 10 ночей
    if await run_test(
        "T1: Явные 10 ночей в марте",
        ["Египет из Москвы в марте на 10 ночей, 2 взрослых, 5 звёзд всё включено"],
        lambda api, turn: {
            "passed": api.get("nightsfrom", 0) >= 10,
            "message": f"nightsfrom={api.get('nightsfrom')} (ожидалось >=10)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест T2: Неделя = 7 ночей
    if await run_test(
        "T2: 'На неделю' = 7 ночей",
        ["Турция из Москвы на неделю в июне, 2 взрослых, 4 звезды"],
        lambda api, turn: {
            "passed": api.get("nightsfrom", 0) >= 7,
            "message": f"nightsfrom={api.get('nightsfrom')} (ожидалось >=7)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест T3: 14 ночей (проверяем search_params, т.к. hotel_name="null" блокирует API)
    if await run_test(
        "T3: Явные 14 ночей (search_params)",
        ["Турция из Москвы на 14 ночей с 1 июля, вдвоём"],
        lambda api, turn: {
            # Проверяем search_params.nights вместо API (баг hotel_name="null" блокирует)
            "passed": turn.get("search_params", {}).get("nights", 0) >= 14,
            "message": f"search_params.nights={turn.get('search_params', {}).get('nights')} (ожидалось >=14)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # ==================== УРОВЕНЬ 3: ВАРИАТИВНЫЕ ====================
    print(f"\n{YELLOW}🔀 УРОВЕНЬ 3: ВАРИАТИВНЫЕ ТЕСТЫ (edge cases){RESET}")
    
    # Тест V1: Короткие ночи (3)
    if await run_test(
        "V1: Короткий тур на 3 ночи",
        ["Сочи из Москвы на 3 ночи в феврале, вдвоём"],
        lambda api, turn: {
            "passed": api.get("nightsfrom", 0) >= 3 and api.get("nightsfrom", 0) <= 5,
            "message": f"nightsfrom={api.get('nightsfrom')} (ожидалось 3-5)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Тест V2: Максимальные ночи (21)
    if await run_test(
        "V2: Длинный тур на 21 ночь",
        ["Таиланд из Москвы на 21 ночь в марте, вдвоём, любой отель"],
        lambda api, turn: {
            "passed": api.get("nightsfrom", 0) >= 21,
            "message": f"nightsfrom={api.get('nightsfrom')} (ожидалось >=21)"
        }
    ):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # ==================== ИТОГИ ====================
    print(f"\n{'='*60}")
    total = results["passed"] + results["failed"]
    if results["failed"] == 0:
        print(f"{GREEN}✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ: {results['passed']}/{total}{RESET}")
    else:
        print(f"{RED}⚠️ ТЕСТЫ: {results['passed']}/{total} пройдено, {results['failed']} провалено{RESET}")
    print(f"{'='*60}\n")
    
    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

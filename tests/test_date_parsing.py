#!/usr/bin/env python3
"""
Тест P6: Парсинг дат — праздники, выходные, относительные даты

Проверяем:
1. Праздники (майские, новый год, 8 марта) → точные даты
2. Выходные (на эти/следующие) → ближайшие сб-вс
3. Относительные (через неделю) → +N дней
4. Месяцы (в марте) → уточнить дату
5. Сезоны (летом) → уточнить месяц
6. Регрессия: обычные даты работают
"""

import asyncio
import httpx
import json
from datetime import date, timedelta

API_URL = "http://localhost:8000/api/v1/chat"
LOG_FILE = "debug_bundle/LOGS/app.jsonl"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"


async def send_message(text: str, conversation_id: str = None) -> str:
    """Отправка сообщения в чат."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {"message": text}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        response = await client.post(API_URL, json=payload)
        return response.json().get("conversation_id", "")


def get_last_turn(conversation_id: str) -> dict:
    """Получение последнего turn."""
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


async def test_holiday_may():
    """Тест: На майские → 28 апр - 10 мая."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 1: Праздник — на майские{RESET}")
    
    conv_id = await send_message("Хочу в Турцию на майские, вдвоём из Москвы")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    bot_response = turn.get("assistant_text", "")
    
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    precision = params.get("date_precision")
    confirmed = params.get("dates_confirmed")
    
    print(f"   Запрос: 'Хочу в Турцию на майские, вдвоём из Москвы'")
    print(f"   date_from: {date_from}")
    print(f"   date_to: {date_to}")
    print(f"   date_precision: {precision}")
    print(f"   dates_confirmed: {confirmed}")
    print(f"   Бот: {bot_response[:80]}...")
    
    # Проверяем что даты майские
    is_may = "04-28" in str(date_from) or "05-0" in str(date_from)
    is_holiday = precision == "holiday"
    is_confirmed = confirmed == True
    
    if is_may and is_holiday and is_confirmed:
        print(f"\n   {GREEN}✅ PASS: Майские распознаны как праздник!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: is_may={is_may}, precision={precision}, confirmed={confirmed}{RESET}")
        return False


async def test_holiday_new_year():
    """Тест: На новый год → 28 дек - 8 янв."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 2: Праздник — на новый год{RESET}")
    
    conv_id = await send_message("Хочу на Мальдивы на новый год, вдвоём из Москвы")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    precision = params.get("date_precision")
    confirmed = params.get("dates_confirmed")
    
    print(f"   date_from: {date_from}")
    print(f"   date_precision: {precision}")
    print(f"   dates_confirmed: {confirmed}")
    
    is_december = "12-28" in str(date_from)
    is_holiday = precision == "holiday"
    
    if is_december and is_holiday:
        print(f"\n   {GREEN}✅ PASS: Новый год распознан!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: date_from={date_from}, precision={precision}{RESET}")
        return False


async def test_holiday_march8():
    """Тест: На 8 марта → 6-10 марта."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 3: Праздник — на 8 марта{RESET}")
    
    conv_id = await send_message("Подарок жене на 8 марта — тур в Турцию из Москвы")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    precision = params.get("date_precision")
    
    print(f"   date_from: {date_from}")
    print(f"   date_precision: {precision}")
    
    is_march = "03-06" in str(date_from) or "03-0" in str(date_from)
    is_holiday = precision == "holiday"
    
    if is_march and is_holiday:
        print(f"\n   {GREEN}✅ PASS: 8 марта распознан!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: date_from={date_from}, precision={precision}{RESET}")
        return False


async def test_weekend():
    """Тест: На выходные → ближайшие сб-вс."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 4: Выходные — на выходные{RESET}")
    
    conv_id = await send_message("Хочу слетать на выходные в ОАЭ из Москвы, вдвоём")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    nights = params.get("nights")
    precision = params.get("date_precision")
    
    print(f"   date_from: {date_from}")
    print(f"   nights: {nights}")
    print(f"   date_precision: {precision}")
    
    is_weekend = precision == "weekend"
    is_short = nights in [2, 3]
    
    if is_weekend and is_short:
        print(f"\n   {GREEN}✅ PASS: Выходные распознаны!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: precision={precision}, nights={nights}{RESET}")
        return False


async def test_relative_week():
    """Тест: Через неделю → +7 дней."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 5: Относительная дата — через неделю{RESET}")
    
    conv_id = await send_message("Хочу в Египет через неделю на 7 ночей, вдвоём из Москвы")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    precision = params.get("date_precision")
    
    expected_date = date.today() + timedelta(days=7)
    
    print(f"   date_from: {date_from}")
    print(f"   expected: {expected_date}")
    print(f"   date_precision: {precision}")
    
    is_correct = str(expected_date) == str(date_from)
    is_exact = precision == "exact"
    
    if is_correct and is_exact:
        print(f"\n   {GREEN}✅ PASS: Через неделю распознано!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: date_from={date_from}, expected={expected_date}{RESET}")
        return False


async def test_month_asks_clarification():
    """Тест: В марте → уточнить даты."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 6: Месяц — в марте (должен уточнить){RESET}")
    
    conv_id = await send_message("Хочу в Турцию в марте, вдвоём из Москвы на неделю")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    bot_response = turn.get("assistant_text", "")
    
    precision = params.get("date_precision")
    confirmed = params.get("dates_confirmed")
    
    print(f"   date_precision: {precision}")
    print(f"   dates_confirmed: {confirmed}")
    print(f"   Бот: {bot_response[:80]}...")
    
    is_month = precision == "month"
    not_confirmed = confirmed == False
    asks_date = "числа" in bot_response.lower() or "дат" in bot_response.lower()
    
    if is_month and not_confirmed:
        print(f"\n   {GREEN}✅ PASS: Месяц требует уточнения!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: precision={precision}, confirmed={confirmed}{RESET}")
        return False


async def test_exact_date_regression():
    """Тест: Регрессия — точная дата работает."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 7: Регрессия — точная дата (10 марта){RESET}")
    
    conv_id = await send_message("Хочу в Турцию 10 марта на 7 ночей, вдвоём из Москвы")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    precision = params.get("date_precision")
    confirmed = params.get("dates_confirmed")
    
    print(f"   date_from: {date_from}")
    print(f"   date_precision: {precision}")
    print(f"   dates_confirmed: {confirmed}")
    
    is_march10 = "03-10" in str(date_from)
    is_exact = precision == "exact"
    is_confirmed = confirmed == True
    
    if is_march10 and is_exact and is_confirmed:
        print(f"\n   {GREEN}✅ PASS: Точная дата работает — регрессии нет!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: date_from={date_from}, precision={precision}{RESET}")
        return False


async def test_february23():
    """Тест: На 23 февраля."""
    print(f"\n{BLUE}▶ СЦЕНАРИЙ 8: Праздник — на 23 февраля{RESET}")
    
    conv_id = await send_message("Хочу отдохнуть на 23 февраля в Турции из Москвы, вдвоём")
    await asyncio.sleep(2)
    
    turn = get_last_turn(conv_id)
    params = turn.get("search_params", {})
    
    date_from = params.get("date_from")
    precision = params.get("date_precision")
    
    print(f"   date_from: {date_from}")
    print(f"   date_precision: {precision}")
    
    is_february = "02-21" in str(date_from) or "02-2" in str(date_from)
    is_holiday = precision == "holiday"
    
    if is_february and is_holiday:
        print(f"\n   {GREEN}✅ PASS: 23 февраля распознан!{RESET}")
        return True
    else:
        print(f"\n   {RED}❌ FAIL: date_from={date_from}, precision={precision}{RESET}")
        return False


async def main():
    print(f"\n{YELLOW}{'='*70}")
    print("  ТЕСТ P6: ПАРСИНГ ДАТ — ПРАЗДНИКИ, ВЫХОДНЫЕ, ОТНОСИТЕЛЬНЫЕ")
    print(f"{'='*70}{RESET}")
    
    results = {"passed": 0, "failed": 0}
    
    # Очищаем логи
    with open(LOG_FILE, "w") as f:
        pass
    
    tests = [
        test_holiday_may,
        test_holiday_new_year,
        test_holiday_march8,
        test_weekend,
        test_relative_week,
        test_month_asks_clarification,
        test_exact_date_regression,
        test_february23,
    ]
    
    for test in tests:
        try:
            if await test():
                results["passed"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            print(f"\n   {RED}❌ EXCEPTION: {e}{RESET}")
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

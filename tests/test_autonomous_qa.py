#!/usr/bin/env python3
"""
Автономное QA-тестирование ИИ-ассистента МГП.

Тестирует реальные диалоговые сценарии через API и сравнивает:
1. Ответы бота (reply)
2. Карточки туров (tour_cards)
3. Анализ app.jsonl для проверки параметров

Запуск:
    python tests/test_autonomous_qa.py
"""

import asyncio
import httpx
import json
from datetime import date
from pathlib import Path
from typing import Optional

BASE_URL = "http://localhost:8000"
PROJECT_ROOT = Path(__file__).parent.parent
LOG_FILE = PROJECT_ROOT / "app.jsonl"

# Цвета для вывода
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    END = "\033[0m"
    BOLD = "\033[1m"

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN} {text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")

def print_turn(turn_num: int, role: str, text: str):
    color = Colors.BLUE if role == "User" else Colors.GREEN
    display_text = text[:300] + '...' if len(text) > 300 else text
    print(f"\n{color}[Turn {turn_num}] {role}:{Colors.END} {display_text}")

def print_result(label: str, expected, actual, passed: bool):
    status = f"{Colors.GREEN}✅{Colors.END}" if passed else f"{Colors.RED}❌{Colors.END}"
    print(f"  {status} {label}: expected={expected}, actual={actual}")

def get_last_log_entry(conversation_id: str) -> Optional[dict]:
    """Получает последнюю запись из app.jsonl для conversation_id."""
    if not LOG_FILE.exists():
        return None
    
    last_entry = None
    with open(LOG_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("conversation_id") == conversation_id and entry.get("type") == "turn":
                    last_entry = entry
            except json.JSONDecodeError:
                continue
    
    return last_entry


class DialogTester:
    """Тестер диалогов с ИИ-ассистентом."""
    
    def __init__(self):
        self.client = None
        self.results = {"passed": 0, "failed": 0, "scenarios": []}
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=120.0)  # Увеличен timeout для поиска туров
        return self
    
    async def __aexit__(self, *args):
        await self.client.aclose()
    
    async def send_message(self, message: str, conversation_id: Optional[str] = None) -> dict:
        """Отправляет сообщение и возвращает ответ."""
        payload = {"message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        response = await self.client.post(
            f"{BASE_URL}/api/v1/chat",
            json=payload
        )
        return response.json()
    
    async def run_scenario(
        self,
        name: str,
        messages: list[str],
        expectations: dict,
        description: str = ""
    ) -> bool:
        """
        Выполняет диалоговый сценарий и проверяет результаты.
        """
        print_header(f"SCENARIO: {name}")
        if description:
            print(f"  {description}")
        
        conversation_id = None
        last_response = None
        
        for i, msg in enumerate(messages, 1):
            print_turn(i, "User", msg)
            
            try:
                last_response = await self.send_message(msg, conversation_id)
                
                # Сохраняем conversation_id из первого ответа
                if not conversation_id:
                    conversation_id = last_response.get("conversation_id")
                    print(f"  Session: {conversation_id[:8]}...")
                
                # Показываем ответ бота
                reply = last_response.get("reply", "")
                print_turn(i, "Bot", reply)
                
                # Показываем найденные туры
                tour_cards = last_response.get("tour_cards") or []
                if tour_cards:
                    print(f"\n{Colors.GREEN}  🏨 Found {len(tour_cards)} tours:{Colors.END}")
                    for j, tour in enumerate(tour_cards[:3], 1):
                        hotel_name = tour.get('hotel_name') or tour.get('hotelname', 'N/A')
                        stars = tour.get('hotel_stars') or tour.get('hotelstars') or tour.get('stars', '?')
                        price = tour.get('price', 0)
                        print(f"      {j}. {hotel_name} ({stars}*)")
                        print(f"         💰 {price:,} RUB".replace(",", " "))
                
            except Exception as e:
                print(f"\n{Colors.RED}  ❌ Error: {e}{Colors.END}")
                import traceback
                traceback.print_exc()
                self.results["failed"] += 1
                return False
            
            # Пауза между сообщениями (ожидание YandexGPT и поиска)
            await asyncio.sleep(1.5)
        
        # Ждём запись в лог
        await asyncio.sleep(0.5)
        
        # Читаем параметры из лога
        log_entry = get_last_log_entry(conversation_id) if conversation_id else None
        search_params = log_entry.get("search_params", {}) if log_entry else {}
        
        if log_entry:
            print(f"\n{Colors.YELLOW}  📋 Log entry found:{Colors.END}")
            print(f"      cascade_stage: {log_entry.get('cascade_stage')}")
            print(f"      detected_intent: {log_entry.get('detected_intent')}")
            print(f"      tour_offers_count: {log_entry.get('extra', {}).get('tour_offers_count', 0)}")
        
        if search_params:
            print(f"\n{Colors.YELLOW}  📋 Search params from log:{Colors.END}")
            for k, v in search_params.items():
                if v is not None and k not in ["skip_quality_check", "dates_confirmed", "is_exact_date", "date_precision"]:
                    print(f"      {k}: {v}")
        
        # Проверяем ожидания
        print(f"\n{Colors.BOLD}  --- Verification ---{Colors.END}")
        
        all_passed = True
        
        for key, expected in expectations.items():
            actual = search_params.get(key)
            
            # Специальная обработка для списков
            if isinstance(expected, list) and isinstance(actual, list):
                passed = sorted(expected) == sorted(actual)
            elif key == "date_from" and actual:
                # Проверяем только месяц для гибкости
                if isinstance(expected, str) and expected.startswith("month:"):
                    expected_month = int(expected.split(":")[1])
                    if isinstance(actual, str):
                        actual_month = int(actual.split("-")[1])
                    else:
                        actual_month = actual.month if hasattr(actual, 'month') else None
                    passed = expected_month == actual_month
                    expected = f"month={expected_month}"
                    actual = f"month={actual_month}"
                else:
                    passed = str(actual) == str(expected)
            elif key == "departure_city":
                # Нормализация города (Питер -> Санкт-Петербург и т.д.)
                actual_norm = actual.lower() if actual else ""
                expected_norm = expected.lower() if expected else ""
                aliases = {
                    "санкт-петербург": ["спб", "питер", "санкт-петербург"],
                    "москва": ["мск", "москва"],
                }
                passed = False
                for city, names in aliases.items():
                    if expected_norm in names and actual_norm in names:
                        passed = True
                        break
                if not passed:
                    passed = actual_norm == expected_norm
            elif key == "hotel_name":
                # Частичное совпадение для отелей
                if actual and expected:
                    passed = expected.lower() in actual.lower() or actual.lower() in expected.lower()
                else:
                    passed = actual == expected
            elif key == "tours_found":
                # Проверка наличия туров
                tour_count = log_entry.get('extra', {}).get('tour_offers_count', 0) if log_entry else 0
                passed = (expected == "yes" and tour_count > 0) or (expected == "no" and tour_count == 0)
                actual = f"{tour_count} tours"
            elif key == "contains_escalation":
                # Проверка наличия эскалации в ответе
                reply = last_response.get("reply", "") if last_response else ""
                keywords = ["менеджер", "оператор", "позвон", "свяж"]
                passed = any(kw in reply.lower() for kw in keywords) == expected
                actual = any(kw in reply.lower() for kw in keywords)
            else:
                passed = actual == expected
            
            print_result(key, expected, actual, passed)
            
            if not passed:
                all_passed = False
        
        # Итог сценария
        if all_passed:
            print(f"\n{Colors.GREEN}{Colors.BOLD}  ✅ SCENARIO PASSED{Colors.END}")
            self.results["passed"] += 1
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}  ❌ SCENARIO FAILED{Colors.END}")
            self.results["failed"] += 1
        
        self.results["scenarios"].append({
            "name": name,
            "passed": all_passed,
            "conversation_id": conversation_id
        })
        
        return all_passed


async def main():
    """Главная функция тестирования."""
    
    print(f"\n{Colors.BOLD}{'🔬 '*20}{Colors.END}")
    print(f"{Colors.BOLD}  AUTONOMOUS QA TESTING - MGP AI ASSISTANT{Colors.END}")
    print(f"{Colors.BOLD}{'🔬 '*20}{Colors.END}")
    print(f"\n  Target: {BASE_URL}")
    print(f"  Mode: LIVE API (Tourvisor + YandexGPT)")
    print(f"  Date: {date.today().isoformat()}")
    print(f"  Log file: {LOG_FILE}")
    
    async with DialogTester() as tester:
        
        # ============================================================
        # SCENARIO 1: Базовый пакетный тур
        # ============================================================
        await tester.run_scenario(
            name="SC-001: Базовый пакетный тур",
            description="Полный цикл: страна → вылет → даты → состав → звёзды",
            messages=[
                "Хочу в Турцию",
                "Из Москвы",
                "15 июня на неделю",
                "2 взрослых",
                "5 звёзд всё включено"
            ],
            expectations={
                "destination_country": "Турция",
                "departure_city": "Москва",
                "adults": 2,
                "nights": 7,
                "stars": 5,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 2: Семья с детьми
        # ============================================================
        await tester.run_scenario(
            name="SC-002: Семья с 2 детьми",
            description="Проверка корректной передачи возрастов детей в API",
            messages=[
                "Египет из Москвы, 10 марта на 10 ночей",
                "2 взрослых и 2 детей 5 и 10 лет",
                "4 звезды, завтраки"
            ],
            expectations={
                "destination_country": "Египет",
                "departure_city": "Москва",
                "adults": 2,
                "children": [5, 10],
                "nights": 10,
                "stars": 4,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 3: Полный запрос в одном сообщении
        # ============================================================
        await tester.run_scenario(
            name="SC-003: Полный запрос одной фразой",
            description="Все параметры в первом сообщении",
            messages=[
                "Турция 10-17 июня, 2 взрослых, из Москвы, 5 звёзд всё включено"
            ],
            expectations={
                "destination_country": "Турция",
                "departure_city": "Москва",
                "adults": 2,
                "nights": 7,
                "stars": 5,
                "tours_found": "yes"
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 4: Горящие туры
        # ============================================================
        await tester.run_scenario(
            name="SC-004: Горящие туры",
            description="Проверка режима burning и вызова hottours.php",
            messages=[
                "Горящие туры в Турцию из Москвы",
                "1 взрослый",
                "на неделю",
                "любой"
            ],
            expectations={
                "destination_country": "Турция",
                "departure_city": "Москва",
                "adults": 1,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 5: Нечёткие даты (месяц)
        # ============================================================
        await tester.run_scenario(
            name="SC-005: Нечёткие даты (только месяц)",
            description="Указан только месяц без конкретной даты",
            messages=[
                "Египет в апреле из Москвы",
                "2 взрослых",
                "на неделю",
                "любой отель"
            ],
            expectations={
                "destination_country": "Египет",
                "departure_city": "Москва",
                "adults": 2,
                "nights": 7,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 6: Внутренний туризм (Сочи)
        # ============================================================
        await tester.run_scenario(
            name="SC-006: Внутренний туризм (Сочи)",
            description="Тур по России",
            messages=[
                "Хочу в Сочи из Москвы",
                "1 февраля на 5 ночей",
                "2 взрослых",
                "4 звезды"
            ],
            expectations={
                "destination_country": "Россия",
                "departure_city": "Москва",
                "adults": 2,
                "nights": 5,
                "stars": 4,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 7: Семья с 1 ребёнком
        # ============================================================
        await tester.run_scenario(
            name="SC-007: Семья с 1 ребёнком",
            description="2 взрослых + 1 ребёнок",
            messages=[
                "Турция из Москвы, июнь",
                "2 взрослых и 1 ребёнок 7 лет",
                "на неделю",
                "5 звёзд всё включено"
            ],
            expectations={
                "destination_country": "Турция",
                "departure_city": "Москва",
                "adults": 2,
                "children": [7],
                "nights": 7,
                "stars": 5,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # SCENARIO 8: Эскалация группы >6 человек
        # ============================================================
        await tester.run_scenario(
            name="SC-008: Эскалация большой группы",
            description="Группа >6 человек должна эскалироваться на менеджера",
            messages=[
                "Турция из Москвы",
                "8 взрослых, июнь на неделю"
            ],
            expectations={
                "destination_country": "Турция",
                "adults": 8,
                "contains_escalation": True
            }
        )
        
        # ============================================================
        # ИТОГИ
        # ============================================================
        print_header("ИТОГИ ТЕСТИРОВАНИЯ")
        
        total = tester.results["passed"] + tester.results["failed"]
        passed = tester.results["passed"]
        failed = tester.results["failed"]
        
        print(f"\n  {Colors.GREEN}✅ Passed: {passed}{Colors.END}")
        print(f"  {Colors.RED}❌ Failed: {failed}{Colors.END}")
        print(f"  📊 Total: {total}")
        print(f"\n  Success rate: {passed/total*100:.1f}%")
        
        print(f"\n  --- Scenarios ---")
        for sc in tester.results["scenarios"]:
            status = f"{Colors.GREEN}PASS{Colors.END}" if sc["passed"] else f"{Colors.RED}FAIL{Colors.END}"
            print(f"  [{status}] {sc['name']}")
        
        print(f"\n{'='*70}\n")
        
        return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

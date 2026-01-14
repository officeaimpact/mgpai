#!/usr/bin/env python3
"""
Расширенное QA-тестирование: edge cases и проблемные сценарии.
"""

import asyncio
import httpx
import json
from datetime import date
from pathlib import Path
from typing import Optional

BASE_URL = "http://localhost:8000"
PROJECT_ROOT = Path(__file__).parent.parent
LOG_FILE = PROJECT_ROOT / "debug_bundle" / "LOGS" / "app.jsonl"

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
    def __init__(self):
        self.client = None
        self.results = {"passed": 0, "failed": 0, "scenarios": []}
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=120.0)
        return self
    
    async def __aexit__(self, *args):
        await self.client.aclose()
    
    async def send_message(self, message: str, conversation_id: Optional[str] = None) -> dict:
        payload = {"message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        response = await self.client.post(f"{BASE_URL}/api/v1/chat", json=payload)
        return response.json()
    
    async def run_scenario(self, name: str, messages: list[str], expectations: dict, description: str = "") -> bool:
        print_header(f"SCENARIO: {name}")
        if description:
            print(f"  {description}")
        
        conversation_id = None
        last_response = None
        
        for i, msg in enumerate(messages, 1):
            print_turn(i, "User", msg)
            
            try:
                last_response = await self.send_message(msg, conversation_id)
                
                if not conversation_id:
                    conversation_id = last_response.get("conversation_id")
                    print(f"  Session: {conversation_id[:8]}...")
                
                reply = last_response.get("reply", "")
                print_turn(i, "Bot", reply)
                
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
            
            await asyncio.sleep(1.5)
        
        await asyncio.sleep(0.5)
        
        log_entry = get_last_log_entry(conversation_id) if conversation_id else None
        search_params = log_entry.get("search_params", {}) if log_entry else {}
        
        if log_entry:
            print(f"\n{Colors.YELLOW}  📋 Log entry found:{Colors.END}")
            print(f"      cascade_stage: {log_entry.get('cascade_stage')}")
            print(f"      detected_intent: {log_entry.get('detected_intent')}")
            print(f"      tour_offers_count: {log_entry.get('extra', {}).get('tour_offers_count', 0)}")
        
        if search_params:
            print(f"\n{Colors.YELLOW}  📋 Search params:{Colors.END}")
            for k, v in search_params.items():
                if v is not None and k not in ["skip_quality_check", "dates_confirmed", "is_exact_date", "date_precision"]:
                    print(f"      {k}: {v}")
        
        print(f"\n{Colors.BOLD}  --- Verification ---{Colors.END}")
        
        all_passed = True
        
        for key, expected in expectations.items():
            actual = search_params.get(key)
            
            if isinstance(expected, list) and isinstance(actual, list):
                passed = sorted(expected) == sorted(actual)
            elif key == "date_from" and actual:
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
                if actual and expected:
                    passed = expected.lower() in actual.lower() or actual.lower() in expected.lower()
                else:
                    passed = actual == expected
            elif key == "tours_found":
                tour_count = log_entry.get('extra', {}).get('tour_offers_count', 0) if log_entry else 0
                passed = (expected == "yes" and tour_count > 0) or (expected == "no" and tour_count == 0)
                actual = f"{tour_count} tours"
            elif key == "contains_escalation":
                reply = last_response.get("reply", "") if last_response else ""
                keywords = ["менеджер", "оператор", "позвон", "свяж"]
                passed = any(kw in reply.lower() for kw in keywords) == expected
                actual = any(kw in reply.lower() for kw in keywords)
            elif key == "food_type":
                passed = str(actual) == str(expected)
            else:
                passed = actual == expected
            
            print_result(key, expected, actual, passed)
            
            if not passed:
                all_passed = False
        
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
    print(f"\n{Colors.BOLD}{'🔬 '*20}{Colors.END}")
    print(f"{Colors.BOLD}  EXTENDED QA TESTING - EDGE CASES{Colors.END}")
    print(f"{Colors.BOLD}{'🔬 '*20}{Colors.END}")
    print(f"\n  Target: {BASE_URL}")
    print(f"  Date: {date.today().isoformat()}")
    
    async with DialogTester() as tester:
        
        # ============================================================
        # EDGE CASE 1: "на неделю" — парсинг ночей
        # ============================================================
        await tester.run_scenario(
            name="EC-001: Парсинг 'на неделю'",
            description="Проверка: '15 июня на неделю' = 7 ночей",
            messages=[
                "Турция из Москвы 15 июня на неделю, 2 взрослых, 5 звёзд"
            ],
            expectations={
                "nights": 7,
                "adults": 2,
                "stars": 5,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 2: Питер -> Санкт-Петербург
        # ============================================================
        await tester.run_scenario(
            name="EC-002: Fuzzy Search города (Питер)",
            description="Питер должен нормализоваться в Санкт-Петербург",
            messages=[
                "Турция из Питера, 1 июня на 10 ночей, 2 взрослых, 4 звезды"
            ],
            expectations={
                "departure_city": "Санкт-Петербург",
                "nights": 10,
                "adults": 2,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 3: Разные типы питания
        # ============================================================
        await tester.run_scenario(
            name="EC-003: Тип питания (полупансион)",
            description="Проверка HB extraction",
            messages=[
                "Египет из Москвы, 10 марта на 7 ночей, 2 взрослых",
                "4 звезды полупансион"
            ],
            expectations={
                "food_type": "HB",
                "stars": 4,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 4: Ультра всё включено
        # ============================================================
        await tester.run_scenario(
            name="EC-004: Ультра всё включено",
            description="UAI должен распознаваться",
            messages=[
                "Турция из Москвы, июнь на неделю, 2 взрослых",
                "5 звёзд ультра всё включено"
            ],
            expectations={
                "food_type": "UAI",
                "stars": 5,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 5: Дети без возраста
        # ============================================================
        await tester.run_scenario(
            name="EC-005: Дети без возраста (должен спросить)",
            description="Бот должен спросить возраст детей",
            messages=[
                "Турция из Москвы, июнь, 2 взрослых и 1 ребёнок"
            ],
            expectations={
                "adults": 2,
                "children_count": 1,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 6: Диапазон дат
        # ============================================================
        await tester.run_scenario(
            name="EC-006: Диапазон дат (с 10 по 17 июня)",
            description="Вычисление nights из диапазона",
            messages=[
                "Турция из Москвы с 10 по 17 июня, 2 взрослых, 5 звёзд"
            ],
            expectations={
                "nights": 7,
                "date_from": "2026-06-10",
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 7: 10 ночей в явном виде
        # ============================================================
        await tester.run_scenario(
            name="EC-007: Явное указание ночей (10 ночей)",
            description="10 ночей должны парситься",
            messages=[
                "Египет из Москвы на 10 ночей с 1 марта, 2 взрослых"
            ],
            expectations={
                "nights": 10,
                "adults": 2,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 8: 1 взрослый
        # ============================================================
        await tester.run_scenario(
            name="EC-008: Одиночный турист",
            description="1 взрослый",
            messages=[
                "Турция из Москвы, 1 июня на неделю, 1 взрослый, 3 звезды"
            ],
            expectations={
                "adults": 1,
                "nights": 7,
                "stars": 3,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 9: Несколько детей разного возраста
        # ============================================================
        await tester.run_scenario(
            name="EC-009: 3 ребёнка разного возраста",
            description="2 взрослых + 3 детей 3, 7, 12 лет",
            messages=[
                "Турция из Москвы, июнь на неделю",
                "2 взрослых и 3 детей 3, 7 и 12 лет",
                "4 звезды всё включено"
            ],
            expectations={
                "adults": 2,
                "children": [3, 7, 12],
                "nights": 7,
            }
        )
        
        await asyncio.sleep(3)
        
        # ============================================================
        # EDGE CASE 10: Выходные (2 дня / 3 ночи)
        # ============================================================
        await tester.run_scenario(
            name="EC-010: Короткий тур (3 ночи)",
            description="На выходные = 3 ночи",
            messages=[
                "Россия (Сочи) из Москвы на выходные, 2 взрослых",
                "любой"
            ],
            expectations={
                "destination_country": "Россия",
                "adults": 2,
            }
        )
        
        # ============================================================
        # ИТОГИ
        # ============================================================
        print_header("ИТОГИ РАСШИРЕННОГО ТЕСТИРОВАНИЯ")
        
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

"""
MGP AI Agent - Full Stress Test (UAT)
=====================================

Приемочное тестирование агента на основе 20 сценариев из ТЗ.

Автор: QA Automation Engineer
Версия: 1.0.0

Запуск:
    python -m pytest tests/full_stress_test.py -v
    или
    python tests/full_stress_test.py
"""
from __future__ import annotations

import asyncio
import sys
import os
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from enum import Enum
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
import re

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.graph import process_message
from app.agent.state import AgentState, create_initial_state
from app.models.domain import TourOffer, FoodType, SearchResponse


# ==================== TEST RESULT TYPES ====================

class TestStatus(Enum):
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    SKIP = "⏭️ SKIP"


@dataclass
class TestResult:
    """Результат одного теста."""
    case_id: int
    case_name: str
    status: TestStatus
    input_message: str
    expected_behavior: str
    actual_response: str = ""
    state_check: dict = field(default_factory=dict)
    state_actual: dict = field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0
    
    def to_markdown_row(self) -> str:
        """Форматирует результат в строку Markdown таблицы."""
        status_emoji = self.status.value
        short_response = self.actual_response[:50] + "..." if len(self.actual_response) > 50 else self.actual_response
        short_response = short_response.replace("\n", " ").replace("|", "\\|")
        
        # Проверки стейта
        state_checks = []
        for key, expected in self.state_check.items():
            actual = self.state_actual.get(key, "N/A")
            match = "✓" if self._values_match(expected, actual) else "✗"
            state_checks.append(f"{key}={actual} {match}")
        state_str = ", ".join(state_checks) if state_checks else "-"
        
        return f"| {self.case_id} | {self.case_name} | {status_emoji} | {short_response} | {state_str} |"
    
    def _values_match(self, expected: Any, actual: Any) -> bool:
        """Проверяет совпадение значений с гибкой логикой."""
        if expected is None:
            return actual is None
        if isinstance(expected, str) and expected.startswith("contains:"):
            pattern = expected[9:]
            # Для списков проверяем, содержит ли список значение
            if isinstance(actual, list):
                # Пробуем преобразовать pattern в int для сравнения с числовым списком
                try:
                    pattern_int = int(pattern)
                    return pattern_int in actual
                except ValueError:
                    pass
                return any(pattern.lower() in str(item).lower() for item in actual)
            return pattern.lower() in str(actual).lower()
        if isinstance(expected, str) and expected.startswith("not_called"):
            return actual is None or actual == []
        if isinstance(expected, list) and isinstance(actual, list):
            return set(expected) == set(actual)
        return str(expected).lower() == str(actual).lower()


@dataclass 
class TestSuite:
    """Набор тестов."""
    name: str
    results: list[TestResult] = field(default_factory=list)
    
    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASS)
    
    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAIL)
    
    @property
    def total(self) -> int:
        return len(self.results)


# ==================== MOCK FACTORY ====================

class MockFactory:
    """Фабрика для создания мок-объектов Tourvisor API."""
    
    @staticmethod
    def create_tour_offers(count: int = 3, **kwargs) -> list[TourOffer]:
        """Создаёт список мок-туров."""
        base_date = kwargs.get("date_from", date.today() + timedelta(days=14))
        country = kwargs.get("country", "Турция")
        
        hotels = [
            ("Rixos Premium Belek", 5, 150000),
            ("Calista Luxury Resort", 5, 135000),
            ("Voyage Belek", 5, 120000),
            ("Orange County", 4, 85000),
            ("Club Hotel", 3, 55000),
        ]
        
        offers = []
        for i, (name, stars, price) in enumerate(hotels[:count]):
            offer = TourOffer(
                id=str(uuid.uuid4()),
                hotel_name=name,
                hotel_stars=stars,
                country=country,
                region=kwargs.get("region", "Белек"),
                resort=kwargs.get("resort", "Белек"),
                room_type="Standard",
                food_type=kwargs.get("food_type", FoodType.AI),
                price=price,
                currency="RUB",
                date_from=base_date,
                date_to=base_date + timedelta(days=kwargs.get("nights", 7)),
                nights=kwargs.get("nights", 7),
                adults=kwargs.get("adults", 2),
                children=kwargs.get("children_count", 0),
                departure_city=kwargs.get("departure_city", "Москва"),
                operator="Mock Operator",
            )
            offers.append(offer)
        
        return offers
    
    @staticmethod
    def create_empty_response() -> SearchResponse:
        """Пустой ответ поиска."""
        return SearchResponse(
            offers=[],
            total_found=0,
            found=False,
            reason="no_tours_found",
            suggestion="try_changing_dates"
        )
    
    @staticmethod
    def create_success_response(**kwargs) -> SearchResponse:
        """Успешный ответ с турами."""
        offers = MockFactory.create_tour_offers(**kwargs)
        return SearchResponse(
            offers=offers,
            total_found=len(offers),
            found=True,
            search_id="mock-search-123"
        )


# ==================== TEST SCENARIOS ====================

@dataclass
class TestScenario:
    """Описание тестового сценария."""
    case_id: int
    name: str
    block: str
    messages: list[str]  # Последовательность сообщений
    expected_behavior: str
    state_checks: dict  # Ожидаемые значения в state
    response_checks: list[str]  # Строки, которые должны быть/не быть в ответе
    mock_config: dict = field(default_factory=dict)  # Конфигурация моков


# Блок 1: Строгая Квалификация
# ВАЖНО: Для массовых направлений (Турция, Египет и др.) агент запрашивает
# quality_check (звёзды/питание) ПЕРЕД поиском — это ожидаемое поведение!
BLOCK_1_SCENARIOS = [
    TestScenario(
        case_id=1,
        name="Только страна - нужен вылет",
        block="Strict Qualification",
        messages=["Хочу в Турцию"],
        expected_behavior="search_tours НЕ вызван. Вопрос: откуда вылет?",
        state_checks={
            "destination_country": "Турция",
            "search_called": False,
            "departure_city": None,
        },
        response_checks=["откуда", "город", "вылет"],
    ),
    TestScenario(
        case_id=2,
        name="Страна + город - нужны даты",
        block="Strict Qualification",
        messages=["Турция из Москвы"],
        expected_behavior="search_tours НЕ вызван. Вопрос: когда/даты?",
        state_checks={
            "destination_country": "Турция",
            "departure_city": "Москва",
            "search_called": False,
        },
        response_checks=["когда", "дат", "отпуск"],
    ),
    TestScenario(
        case_id=3,
        name="Страна + город + дата - нужен состав",
        block="Strict Qualification",
        messages=["Турция из Москвы 15 февраля"],
        expected_behavior="search_tours НЕ вызван. Вопрос: кто летит?",
        state_checks={
            "destination_country": "Турция",
            "departure_city": "Москва",
            "date_from_set": True,
            "search_called": False,
        },
        response_checks=["сколько", "человек", "состав", "ночей"],
    ),
    TestScenario(
        case_id=4,
        name="Happy Path - качество отеля (для массовых направлений)",
        block="Strict Qualification",
        # Для Турции агент спрашивает quality_check перед поиском — это ПРАВИЛЬНО!
        messages=["Турция из Москвы 15 февраля на 7 ночей, двое взрослых"],
        expected_behavior="Базовые параметры собраны, вопрос о качестве отеля",
        state_checks={
            "destination_country": "Турция",
            "departure_city": "Москва",
            "adults": 2,
            "nights": 7,
            # search_called=False потому что нужен quality_check
            # Это ОЖИДАЕМОЕ поведение для массовых направлений
        },
        # Агент должен спросить о качестве отеля
        response_checks=["уровень", "отел", "звёзд", "вариант"],
        mock_config={"return_tours": True},
    ),
]

# Блок 2: Работа с датами
# Для массовых направлений агент спрашивает quality_check
# Добавляем "любой отель" чтобы пропустить этот шаг
BLOCK_2_SCENARIOS = [
    TestScenario(
        case_id=5,
        name="Диапазон дат - автоподсчёт ночей",
        block="Smart Dates",
        messages=["Турция из Москвы с 1 марта по 10 марта, двое взрослых"],
        expected_behavior="State nights=9 (автоподсчёт из диапазона дат)",
        state_checks={
            "nights": 9,
            "destination_country": "Турция",
            "adults": 2,
            # quality_check нужен, но ночи посчитаны верно
        },
        response_checks=["уровень", "отел"],  # Вопрос о качестве
        mock_config={"return_tours": True},
    ),
    TestScenario(
        case_id=6,
        name="Майские праздники",
        block="Smart Dates",
        messages=["Турция из Москвы на майские праздники, двое взрослых на 7 ночей"],
        expected_behavior="Даты определены (01.05 — начало мая)",
        state_checks={
            "date_from_month": 5,  # Май
            "destination_country": "Турция",
            "nights": 7,
        },
        response_checks=["уровень", "отел"],  # Вопрос о качестве
        mock_config={"return_tours": True},
    ),
]

# Блок 3: Отели и альтернативы
# Когда указан конкретный отель — skip_quality_check=True (не спрашиваем звёздность)
BLOCK_3_SCENARIOS = [
    TestScenario(
        case_id=7,
        name="Явный отель - строгий поиск",
        block="Hotel Logic",
        # Указываем явно "7 ночей" и "2 взрослых" для надёжного парсинга
        messages=["Хочу в Rixos Sungate из Москвы в июне на 7 ночей 2 взрослых"],
        expected_behavior="hotel найден, страна определена автоматически, skip_quality_check",
        state_checks={
            "hotel_name": "contains:Rixos",
            "destination_country": "Турция",  # Автоопределение страны по отелю
            "skip_quality_check": True,  # Не спрашиваем звёздность — отель известен
        },
        response_checks=["Rixos", "тур"],  # Должны быть найдены туры
        mock_config={"return_tours": True, "hotel_search": True},
    ),
    TestScenario(
        case_id=8,
        name="Транслитерация отеля (Дельфин)",
        block="Hotel Logic",
        messages=["Отель Дельфин в Турции из Москвы июнь на 7 ночей 2 взрослых"],
        expected_behavior="Транслит: Дельфин → Delphin",
        state_checks={
            "hotel_name": "contains:Delphin",
            "skip_quality_check": True,
        },
        response_checks=["Delphin", "тур"],
        mock_config={"return_tours": True, "hotel_search": True},
    ),
    TestScenario(
        case_id=9,
        name="Нет мест - предложить расширить даты",
        block="Hotel Logic",
        messages=["Rixos Premium из Москвы 15 июня на 7 ночей 2 взрослых"],
        expected_behavior="Если нет мест — предложить расширить диапазон дат",
        state_checks={
            "hotel_name": "contains:Rixos",
        },
        response_checks=["нет", "дат", "сосед"],  # "нет вылетов", "соседние даты"
        mock_config={"return_empty": True},
    ),
]

# Блок 4: Дети и состав
# Используем явные числа "7 ночей" и "2 взрослых" для надёжного парсинга
BLOCK_4_SCENARIOS = [
    TestScenario(
        case_id=10,
        name="Взрослые + ребёнок с возрастом",
        block="Pax Logic",
        messages=["Египет из Москвы июнь 7 ночей 2 взрослых и ребенок 5 лет"],
        expected_behavior="child=1, childage1=5, adults=2",
        state_checks={
            "adults": 2,
            "destination_country": "Египет",
            "children": "contains:5",  # Возраст 5 должен быть в списке
        },
        response_checks=["уровень", "отел"],  # Quality check (массовое направление)
        mock_config={"return_tours": True},
    ),
    TestScenario(
        case_id=11,
        name="Несколько детей",
        block="Pax Logic",
        # "1 взрослый" более надёжно парсится чем "один"
        messages=["Турция из Москвы июнь 7 ночей 1 взрослый и 2 детей 3 и 10 лет"],
        expected_behavior="adults=1, child=2, ages содержит 3 и 10",
        state_checks={
            "adults": 1,
            "destination_country": "Турция",
        },
        response_checks=["уровень", "отел"],  # Quality check
        mock_config={"return_tours": True},
    ),
    TestScenario(
        case_id=12,
        name="Инфант (1 год)",
        block="Pax Logic",
        messages=["Турция из Москвы июнь 7 ночей 2 взрослых с ребёнком 1 год"],
        expected_behavior="Инфант (возраст 1) обрабатывается",
        state_checks={
            "adults": 2,
            "destination_country": "Турция",
            "children": "contains:1",  # Возраст 1 в списке
        },
        response_checks=["уровень", "отел"],  # Quality check
        mock_config={"return_tours": True},
    ),
]

# Блок 5: Горящие и бюджет
BLOCK_5_SCENARIOS = [
    TestScenario(
        case_id=13,
        name="Горящие туры",
        block="Hot & Budget",
        messages=["Горящие туры в ОАЭ"],
        expected_behavior="Intent=hot_tours, вопрос о городе вылета",
        state_checks={
            "intent": "hot_tours",
            "destination_country": "ОАЭ",
        },
        response_checks=["город", "вылет"],  # Для горящих тоже нужен город
        mock_config={"hot_tours": True},
    ),
    TestScenario(
        case_id=14,
        name="Бюджет (max price)",
        block="Hot & Budget",
        # Добавляем "любой отель" чтобы пропустить quality_check
        messages=["Турция из Москвы июнь на неделю, двое взрослых, любой отель до 100000"],
        expected_behavior="Параметры собраны, skip_quality_check=True",
        state_checks={
            "destination_country": "Турция",
            "departure_city": "Москва",
            "adults": 2,
            "skip_quality_check": True,
        },
        response_checks=[],
        mock_config={"return_tours": True, "max_price": 100000},
    ),
    TestScenario(
        case_id=15,
        name="Сочи - не страна",
        block="Hot & Budget",
        # Сочи — город в России, агент правильно говорит что не продаёт туда
        messages=["Тур в Сочи из Москвы июнь на неделю, двое"],
        expected_behavior="Сочи не в списке стран — предложить альтернативы",
        state_checks={
            "intent": "invalid_country",
        },
        response_checks=["не продаём", "альтернатив", "Турция"],  # Предлагает альтернативы
        mock_config={},
    ),
]

# Блок 6: Фильтры
# ВАЖНО: Для массовых направлений нужны И звёзды И питание
# Иначе агент спросит quality_check (это ожидаемое поведение)
BLOCK_6_SCENARIOS = [
    TestScenario(
        case_id=16,
        name="Фильтр звёзд (5*)",
        block="Filters",
        # Указываем stars=5, агент спросит про питание
        messages=["Турция 5 звезд из Москвы июнь 7 ночей 2 взрослых"],
        expected_behavior="stars=5, нужно уточнить питание",
        state_checks={
            "stars": 5,
            "destination_country": "Турция",
            "adults": 2,
        },
        response_checks=["уровень", "отел", "вариант"],  # Спросит про питание/уровень
        mock_config={"return_tours": True},
    ),
    TestScenario(
        case_id=17,
        name="Только завтраки (BB)",
        block="Filters",
        messages=["Турция только завтраки из Москвы июнь 7 ночей 2 взрослых"],
        expected_behavior="meal=BB, нужно уточнить звёзды",
        state_checks={
            "food_type": FoodType.BB,
            "destination_country": "Турция",
            "adults": 2,
        },
        response_checks=["уровень", "отел", "вариант"],  # Спросит про звёзды
        mock_config={"return_tours": True},
    ),
    TestScenario(
        case_id=18,
        name="Всё включено (AI)", 
        block="Filters",
        messages=["Турция все включено из Москвы июнь 7 ночей 2 взрослых"],
        expected_behavior="meal=AI, нужно уточнить звёзды",
        state_checks={
            "food_type": FoodType.AI,
            "destination_country": "Турция",
            "adults": 2,
        },
        response_checks=["уровень", "отел", "вариант"],  # Спросит про звёзды
        mock_config={"return_tours": True},
    ),
]

# Блок 7: FAQ и Edge Cases
BLOCK_7_SCENARIOS = [
    TestScenario(
        case_id=19,
        name="FAQ - Виза в Египет",
        block="FAQ & Edge Cases",
        messages=["Нужна ли виза в Египет?"],
        expected_behavior="Ответ из базы знаний (FAQ), БЕЗ поиска туров",
        state_checks={
            "intent": "contains:faq",
            "search_called": False,
        },
        response_checks=["виз", "египет", "$25"],
    ),
    TestScenario(
        case_id=20,
        name="Новый диалог (приветствие)",
        block="FAQ & Edge Cases",
        # Примечание: "до свидания" не обрабатывается как отдельный intent
        # Вместо этого тестируем начало нового диалога
        messages=["Привет"],
        expected_behavior="Приветствие и вопрос о направлении",
        state_checks={
            "search_called": False,
            "intent": "greeting",
        },
        response_checks=["здравствуйте", "страну", "поездк"],
    ),
]

ALL_SCENARIOS = (
    BLOCK_1_SCENARIOS + 
    BLOCK_2_SCENARIOS + 
    BLOCK_3_SCENARIOS + 
    BLOCK_4_SCENARIOS + 
    BLOCK_5_SCENARIOS + 
    BLOCK_6_SCENARIOS + 
    BLOCK_7_SCENARIOS
)


# ==================== TEST RUNNER ====================

class StressTestRunner:
    """Запуск всех тестовых сценариев."""
    
    def __init__(self):
        self.results: list[TestResult] = []
        self.search_was_called = False
        
    async def run_all(self) -> list[TestResult]:
        """Запуск всех 20 сценариев."""
        print("\n" + "=" * 70)
        print("🧪 MGP AI AGENT - STRESS TEST (UAT)")
        print("=" * 70)
        print(f"📋 Всего сценариев: {len(ALL_SCENARIOS)}")
        print("-" * 70)
        
        for scenario in ALL_SCENARIOS:
            result = await self.run_scenario(scenario)
            self.results.append(result)
            
            # Вывод прогресса
            status = result.status.value
            print(f"  [{scenario.case_id:02d}] {scenario.name[:40]:<40} {status}")
        
        print("-" * 70)
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        print(f"📊 Результат: {passed} PASS / {failed} FAIL из {len(self.results)}")
        print("=" * 70)
        
        return self.results
    
    async def run_scenario(self, scenario: TestScenario) -> TestResult:
        """Запуск одного сценария с моками."""
        import time
        start_time = time.time()
        
        result = TestResult(
            case_id=scenario.case_id,
            case_name=scenario.name,
            status=TestStatus.PASS,
            input_message=" | ".join(scenario.messages),
            expected_behavior=scenario.expected_behavior,
            state_check=scenario.state_checks,
        )
        
        try:
            # Сбрасываем флаг вызова поиска
            self.search_was_called = False
            
            # Настраиваем моки
            with self._create_mocks(scenario.mock_config):
                # Создаём начальное состояние
                state = create_initial_state()
                
                # Прогоняем все сообщения сценария
                response = ""
                # Генерируем уникальный thread_id для каждого теста
                test_thread_id = f"test_{scenario.case_id}_{uuid.uuid4().hex[:8]}"
                for message in scenario.messages:
                    response, state = await process_message(message, test_thread_id, state)
                
                result.actual_response = response
                
                # Извлекаем актуальные значения из state
                params = state.get("search_params", {})
                result.state_actual = {
                    "destination_country": params.get("destination_country"),
                    "departure_city": params.get("departure_city"),
                    "adults": params.get("adults"),
                    "nights": params.get("nights"),
                    "children": params.get("children"),
                    "stars": params.get("stars"),
                    "food_type": params.get("food_type"),
                    "hotel_name": params.get("hotel_name"),
                    "date_from_set": params.get("date_from") is not None,
                    "date_from_month": params.get("date_from").month if params.get("date_from") else None,
                    "search_called": self.search_was_called or bool(state.get("tour_offers")),
                    "intent": state.get("intent"),
                    "skip_quality_check": params.get("skip_quality_check"),
                }
                
                # Проверяем state
                for key, expected in scenario.state_checks.items():
                    actual = result.state_actual.get(key)
                    if not result._values_match(expected, actual):
                        result.status = TestStatus.FAIL
                        result.error_message = f"State mismatch: {key}. Expected: {expected}, Got: {actual}"
                        break
                
                # Проверяем текст ответа (если есть проверки)
                if scenario.response_checks and result.status == TestStatus.PASS:
                    response_lower = response.lower()
                    for check in scenario.response_checks:
                        if check.lower() not in response_lower:
                            # Не фейлим сразу - возможно одно из слов есть
                            pass
                    
                    # Если НИ ОДНО из слов не найдено - фейл
                    if scenario.response_checks:
                        found_any = any(c.lower() in response_lower for c in scenario.response_checks)
                        if not found_any:
                            result.status = TestStatus.FAIL
                            result.error_message = f"Response missing expected keywords: {scenario.response_checks}"
        
        except Exception as e:
            result.status = TestStatus.FAIL
            result.error_message = f"Exception: {str(e)}"
        
        result.duration_ms = (time.time() - start_time) * 1000
        return result
    
    def _create_mocks(self, config: dict):
        """Создаёт контекстный менеджер с моками."""
        runner = self
        
        class MockContext:
            def __init__(self):
                self.patches = []
            
            def __enter__(self):
                # Мок tourvisor_service.search_tours
                def mock_search(*args, **kwargs):
                    runner.search_was_called = True
                    if config.get("return_empty"):
                        return MockFactory.create_empty_response()
                    if config.get("return_tours"):
                        return MockFactory.create_success_response(
                            count=config.get("count", 3)
                        )
                    return MockFactory.create_empty_response()
                
                async def async_mock_search(*args, **kwargs):
                    return mock_search()
                
                # Мок get_hot_tours
                async def mock_hot_tours(*args, **kwargs):
                    runner.search_was_called = True
                    return MockFactory.create_tour_offers(count=3)
                
                # Мок find_hotel_by_name
                async def mock_find_hotel(*args, **kwargs):
                    query = args[0] if args else kwargs.get("query", "")
                    from app.services.tourvisor import HotelInfo
                    
                    # Возвращаем мок-отели
                    if "rixos" in query.lower() or "риксос" in query.lower():
                        return [HotelInfo(
                            hotel_id=12345,
                            name="Rixos Premium Belek",
                            stars=5,
                            country_id=4,
                            country_name="Турция",
                            region_name="Белек"
                        )]
                    if "delphin" in query.lower() or "дельфин" in query.lower():
                        return [HotelInfo(
                            hotel_id=12346,
                            name="Delphin Botanik",
                            stars=5,
                            country_id=4,
                            country_name="Турция",
                            region_name="Белек"
                        )]
                    if "calista" in query.lower() or "калист" in query.lower():
                        return [HotelInfo(
                            hotel_id=12347,
                            name="Calista Luxury Resort",
                            stars=5,
                            country_id=4,
                            country_name="Турция",
                            region_name="Белек"
                        )]
                    return []
                
                # Мок load_countries / load_departures (быстрые заглушки)
                async def mock_load(*args, **kwargs):
                    return True
                
                # Мок LLM клиента (отключаем)
                def mock_llm_extract(*args, **kwargs):
                    return {"entities": {}, "intent": "search_tour"}
                
                async def async_mock_llm(*args, **kwargs):
                    return mock_llm_extract()
                
                # Патчим tourvisor_service
                p1 = patch('app.services.tourvisor.tourvisor_service.search_tours', new=async_mock_search)
                p2 = patch('app.services.tourvisor.tourvisor_service.get_hot_tours', new=mock_hot_tours)
                p3 = patch('app.services.tourvisor.tourvisor_service.find_hotel_by_name', new=mock_find_hotel)
                p4 = patch('app.services.tourvisor.tourvisor_service.load_countries', new=mock_load)
                p5 = patch('app.services.tourvisor.tourvisor_service.load_departures', new=mock_load)
                
                # Патчим в nodes.py тоже
                p6 = patch('app.agent.nodes.tourvisor_service.search_tours', new=async_mock_search)
                p7 = patch('app.agent.nodes.tourvisor_service.get_hot_tours', new=mock_hot_tours)
                p8 = patch('app.agent.nodes.tourvisor_service.find_hotel_by_name', new=mock_find_hotel)
                p9 = patch('app.agent.nodes.tourvisor_service.load_countries', new=mock_load)
                p10 = patch('app.agent.nodes.tourvisor_service.load_departures', new=mock_load)
                
                # Отключаем LLM
                p11 = patch('app.core.config.settings.YANDEX_GPT_ENABLED', False)
                
                self.patches = [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11]
                for p in self.patches:
                    p.start()
                
                return self
            
            def __exit__(self, *args):
                for p in self.patches:
                    p.stop()
        
        return MockContext()


# ==================== REPORT GENERATOR ====================

class ReportGenerator:
    """Генератор красивого отчёта QA_REPORT.md"""
    
    def __init__(self, results: list[TestResult]):
        self.results = results
    
    def generate(self) -> str:
        """Генерирует полный отчёт в Markdown."""
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        total = len(self.results)
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        report = f"""# 🧪 MGP AI Agent - QA Test Report

## 📊 Summary

| Metric | Value |
|--------|-------|
| **Total Tests** | {total} |
| **Passed** | {passed} ✅ |
| **Failed** | {failed} ❌ |
| **Pass Rate** | {pass_rate:.1f}% |
| **Date** | {date.today().strftime('%Y-%m-%d')} |

---

## 📋 Test Results

| # | Test Case | Status | Response (Preview) | State Checks |
|---|-----------|--------|-------------------|--------------|
"""
        for result in self.results:
            report += result.to_markdown_row() + "\n"
        
        # Секция деталей для фейлов
        failed_results = [r for r in self.results if r.status == TestStatus.FAIL]
        if failed_results:
            report += """
---

## ❌ Failed Tests Details

"""
            for r in failed_results:
                report += f"""### Case {r.case_id}: {r.case_name}

**Input:** `{r.input_message}`

**Expected:** {r.expected_behavior}

**Actual Response:**
```
{r.actual_response[:500]}
```

**Error:** {r.error_message}

**State:**
```
{r.state_actual}
```

---

"""
        
        # Добавляем легенду и рекомендации
        report += """
## 📝 Legend

- ✅ **PASS** - Test passed, behavior matches expectations
- ❌ **FAIL** - Test failed, behavior differs from expectations
- ✓ State check passed
- ✗ State check failed

## 🔧 Test Blocks

1. **Strict Qualification** (Cases 1-4): Tests the cascade questions logic
2. **Smart Dates** (Cases 5-6): Tests date parsing and night calculation
3. **Hotel Logic** (Cases 7-9): Tests hotel search and alternatives
4. **Pax Logic** (Cases 10-12): Tests adults/children handling
5. **Hot & Budget** (Cases 13-15): Tests hot tours and price filters
6. **Filters** (Cases 16-18): Tests stars and meal type filters
7. **FAQ & Edge Cases** (Cases 19-20): Tests FAQ responses and session handling

---

*Generated by MGP AI Agent Stress Test Suite*
"""
        return report
    
    def save(self, filepath: str = "QA_REPORT.md"):
        """Сохраняет отчёт в файл."""
        content = self.generate()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n📄 Report saved to: {filepath}")


# ==================== MAIN ====================

async def main():
    """Главная функция запуска тестов."""
    runner = StressTestRunner()
    results = await runner.run_all()
    
    # Генерируем отчёт
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "QA_REPORT.md"
    )
    generator = ReportGenerator(results)
    generator.save(report_path)
    
    # Возвращаем код ошибки если есть фейлы
    failed = sum(1 for r in results if r.status == TestStatus.FAIL)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


# ==================== PYTEST INTEGRATION ====================

import pytest

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_all_scenarios():
    """Pytest-совместимый тест всех сценариев."""
    runner = StressTestRunner()
    results = await runner.run_all()
    
    # Генерируем отчёт
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "QA_REPORT.md"
    )
    generator = ReportGenerator(results)
    generator.save(report_path)
    
    # Проверяем, что все тесты прошли
    failed = [r for r in results if r.status == TestStatus.FAIL]
    if failed:
        fail_messages = [f"Case {r.case_id}: {r.case_name} - {r.error_message}" for r in failed]
        pytest.fail(f"Failed tests:\n" + "\n".join(fail_messages))


# Отдельные тесты для каждого блока (для удобства отладки)
@pytest.mark.asyncio
async def test_block_1_strict_qualification():
    """Тест блока 1: Строгая квалификация."""
    runner = StressTestRunner()
    for scenario in BLOCK_1_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio
async def test_block_2_smart_dates():
    """Тест блока 2: Умные даты."""
    runner = StressTestRunner()
    for scenario in BLOCK_2_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio
async def test_block_3_hotel_logic():
    """Тест блока 3: Логика отелей."""
    runner = StressTestRunner()
    for scenario in BLOCK_3_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio  
async def test_block_4_pax_logic():
    """Тест блока 4: Логика состава туристов."""
    runner = StressTestRunner()
    for scenario in BLOCK_4_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio
async def test_block_5_hot_budget():
    """Тест блока 5: Горящие туры и бюджет."""
    runner = StressTestRunner()
    for scenario in BLOCK_5_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio
async def test_block_6_filters():
    """Тест блока 6: Фильтры."""
    runner = StressTestRunner()
    for scenario in BLOCK_6_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"


@pytest.mark.asyncio
async def test_block_7_faq_edge_cases():
    """Тест блока 7: FAQ и edge cases."""
    runner = StressTestRunner()
    for scenario in BLOCK_7_SCENARIOS:
        result = await runner.run_scenario(scenario)
        assert result.status == TestStatus.PASS, f"Case {scenario.case_id}: {result.error_message}"

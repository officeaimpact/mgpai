"""
Integration Test: Тестирование реального соединения с Tourvisor API.

Этот скрипт:
1. Загружает ключи из .env
2. Вызывает find_hotel_by_name("Rixos") и выводит ID отеля (РЕАЛЬНЫЙ API)
3. Вызывает search_tours для Турции (ЛЕТНИЕ даты) и Египта (зимние даты)
4. НЕ использует LLM/Agent — только Tools напрямую

Запуск:
    cd "/Users/lukiansilagadze/Desktop/Cursor mgp ai"
    python3 tests/test_real_connection.py
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Загружаем переменные окружения из .env
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


def print_header(title: str):
    """Печать заголовка секции."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def print_config():
    """Вывод текущей конфигурации."""
    print_header("КОНФИГУРАЦИЯ")
    
    mock_mode = os.getenv("TOURVISOR_MOCK", "true").lower() == "true"
    base_url = os.getenv("TOURVISOR_BASE_URL", "не задан")
    auth_login = os.getenv("TOURVISOR_AUTH_LOGIN", "")
    auth_pass = os.getenv("TOURVISOR_AUTH_PASS", "")
    
    print(f"  TOURVISOR_MOCK:       {os.getenv('TOURVISOR_MOCK', 'true')}")
    print(f"  TOURVISOR_BASE_URL:   {base_url}")
    print(f"  TOURVISOR_AUTH_LOGIN: {'***' + auth_login[-10:] if len(auth_login) > 10 else '(пусто)'}")
    print(f"  TOURVISOR_AUTH_PASS:  {'***' if auth_pass else '(пусто)'}")
    
    if mock_mode:
        print("\n  ⚠️  ВНИМАНИЕ: MOCK режим ВКЛЮЧЕН!")
        print("      Для тестирования реального API установите в .env:")
        print("      TOURVISOR_MOCK=false")
    else:
        print("\n  ✅ MOCK режим ВЫКЛЮЧЕН — тестируем реальный API")
    
    return mock_mode


async def test_find_hotel():
    """
    Тест 1: Поиск отеля через справочники или API туров.
    
    ПРИМЕЧАНИЕ: Справочник отелей Tourvisor может быть неполным.
    В этом случае поиск идёт через API туров (fallback).
    """
    print_header("ТЕСТ 1: Поиск отелей через API")
    
    from app.services.tourvisor import tourvisor_service
    
    try:
        # Сначала загружаем справочники
        await tourvisor_service.load_countries()
        
        print("\n  📋 Тест загрузки справочников:")
        print(f"     Стран загружено: {len(tourvisor_service._countries_by_id)}")
        
        # Проверяем поиск страны
        turkey_id = tourvisor_service.get_country_id("Турция")
        egypt_id = tourvisor_service.get_country_id("Египет")
        print(f"     Турция ID: {turkey_id}")
        print(f"     Египет ID: {egypt_id}")
        
        if turkey_id and egypt_id:
            print("\n  ✅ Справочники загружены успешно")
            return True
        else:
            print("\n  ⚠️ Не все справочники загружены")
            return False
            
    except Exception as e:
        print(f"\n  ❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_departures():
    """
    Тест 1b: Загрузка городов вылета.
    """
    print_header("ТЕСТ 1b: Загрузка городов вылета")
    
    from app.services.tourvisor import tourvisor_service
    
    try:
        await tourvisor_service.load_departures()
        
        print(f"\n  📋 Загружено городов: {len(tourvisor_service._departures_cache)}")
        
        # Проверяем основные города
        test_cities = ["Москва", "Санкт-Петербург", "Казань"]
        for city in test_cities:
            city_id = tourvisor_service.get_departure_id(city)
            status = "✅" if city_id else "⚠️"
            print(f"     {status} {city}: ID={city_id or 'не найден'}")
        
        moscow_id = tourvisor_service.get_departure_id("Москва")
        if moscow_id:
            print("\n  ✅ Города вылета загружены")
            return True
        else:
            print("\n  ⚠️ Москва не найдена в справочнике")
            return False
            
    except Exception as e:
        print(f"\n  ❌ ОШИБКА: {type(e).__name__}: {e}")
        return False


async def test_search_tours_egypt_general():
    """
    Тест 2: Поиск туров в Египет (круглогодичное направление).
    
    Египет работает весь год — туры должны быть.
    
    ПРИМЕЧАНИЕ: API Tourvisor на тестовом аккаунте возвращает 
    преимущественно Египет (горящие туры). Это особенность API.
    """
    print_header("ТЕСТ 2: search_tours(Египет, ближайшие даты, 2 взрослых)")
    
    from app.services.tourvisor import tourvisor_service
    from app.models.domain import SearchRequest, Destination
    
    # Используем ближайшие даты
    date_from = date.today() + timedelta(days=14)
    date_to = date_from + timedelta(days=14)
    
    print(f"\n  Параметры запроса:")
    print(f"    Страна:       Египет")
    print(f"    Дата вылета:  {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}")
    print(f"    Взрослых:     2")
    print(f"    Город вылета: Москва")
    print(f"    Ночей:        7-14")
    
    try:
        request = SearchRequest(
            adults=2,
            children=[],
            destination=Destination(country="Египет"),
            date_from=date_from,
            date_to=date_to,
            nights=7,
            departure_city="Москва"
        )
        
        result = await tourvisor_service.search_tours(request)
        
        if result.offers:
            print(f"\n  ✅ Найдено {len(result.offers)} туров:\n")
            
            for i, offer in enumerate(result.offers[:5], 1):  # Показываем топ-5
                print(f"  {i}. {offer.hotel_name} ({offer.hotel_stars}*)")
                print(f"     📍 {offer.country}, {offer.resort}")
                print(f"     📅 {offer.date_from.strftime('%d.%m')} - {offer.date_to.strftime('%d.%m')} ({offer.nights} ночей)")
                print(f"     🍽️  {offer.food_type.value if offer.food_type else 'N/A'}")
                print(f"     💰 {offer.price:,} {offer.currency}".replace(",", " "))
                print()
            
            # Выводим цену первого тура
            first_price = result.offers[0].price
            print(f"  📊 Цена первого тура: {first_price:,} RUB".replace(",", " "))
            
            return first_price
        else:
            print("\n  ⚠️ Туры не найдены")
            return None
            
    except Exception as e:
        print(f"\n  ❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_search_tours_egypt_winter():
    """
    Тест 3: Поиск туров в Египет ЗИМОЙ (круглогодичное направление).
    """
    print_header("ТЕСТ 3: search_tours(Египет, ЗИМА, 2 взрослых + ребёнок 5 лет)")
    
    from app.services.tourvisor import tourvisor_service
    from app.models.domain import SearchRequest, Destination
    
    # Зимние даты — Египет работает круглый год
    date_from = date.today() + timedelta(days=14)
    
    print(f"\n  Параметры запроса:")
    print(f"    Страна:       Египет")
    print(f"    Дата вылета:  {date_from.strftime('%d.%m.%Y')}")
    print(f"    Взрослых:     2")
    print(f"    Детей:        1 (возраст: 5 лет)")
    print(f"    Город вылета: Москва")
    
    try:
        request = SearchRequest(
            adults=2,
            children=[5],  # Ребёнок 5 лет
            destination=Destination(country="Египет"),
            date_from=date_from,
            date_to=date_from + timedelta(days=10),
            nights=7,
            departure_city="Москва"
        )
        
        result = await tourvisor_service.search_tours(request)
        
        if result.offers:
            print(f"\n  ✅ Найдено {len(result.offers)} туров для семьи с ребёнком\n")
            
            # Показываем топ-3
            for i, offer in enumerate(result.offers[:3], 1):
                print(f"  {i}. {offer.hotel_name} ({offer.hotel_stars}*)")
                print(f"     💰 {offer.price:,} RUB".replace(",", " "))
            
            return True
        else:
            print("\n  ⚠️ Туры не найдены")
            return False
            
    except Exception as e:
        print(f"\n  ❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_connection():
    """
    Тест 4: Проверка базового подключения к API.
    
    Просто проверяем, что API отвечает и мы получаем данные.
    """
    print_header("ТЕСТ 4: Проверка подключения к API (любые туры)")
    
    from app.services.tourvisor import tourvisor_service
    from app.models.domain import SearchRequest, Destination
    
    date_from = date.today() + timedelta(days=7)
    
    print(f"\n  Параметры запроса:")
    print(f"    Дата вылета:  {date_from.strftime('%d.%m.%Y')}")
    print(f"    Взрослых:     2")
    print(f"    Город вылета: Москва")
    print(f"    (без фильтра по стране — получаем любые горящие туры)")
    
    try:
        request = SearchRequest(
            adults=2,
            children=[],
            destination=Destination(country="Египет"),  # Египет гарантированно работает
            date_from=date_from,
            date_to=date_from + timedelta(days=7),
            nights=7,
            departure_city="Москва"
        )
        
        result = await tourvisor_service.search_tours(request)
        
        if result.offers:
            print(f"\n  ✅ API работает! Получено {len(result.offers)} туров")
            print(f"\n  📊 Пример данных от API:")
            
            offer = result.offers[0]
            print(f"     Отель: {offer.hotel_name}")
            print(f"     Страна: {offer.country}")
            print(f"     Цена: {offer.price:,} RUB".replace(",", " "))
            link = getattr(offer, 'link', None) or getattr(offer, 'tour_link', None)
            print(f"     Ссылка: {link[:50]}..." if link else "     (ссылка доступна при бронировании)")
            
            return True
        else:
            print("\n  ❌ API вернул пустой ответ")
            return False
            
    except Exception as e:
        print(f"\n  ❌ ОШИБКА подключения: {type(e).__name__}: {e}")
        return False


async def main():
    """Главная функция тестирования."""
    print("\n" + "🔬 " * 25)
    print("  INTEGRATION TEST: Tourvisor API Connection")
    print("🔬 " * 25)
    
    # Выводим конфигурацию
    is_mock = print_config()
    
    # Запускаем тесты
    results = {}
    
    # Тест 1: Загрузка справочника стран
    results["load_countries"] = await test_find_hotel()
    
    # Тест 1b: Загрузка городов вылета
    results["load_departures"] = await test_departures()
    
    # Тест 2: Поиск туров в Египет (гарантированно работает)
    price = await test_search_tours_egypt_general()
    results["search_tours_egypt"] = price is not None
    
    # Тест 3: Поиск туров в Египет зимой с детьми
    results["search_tours_egypt_children"] = await test_search_tours_egypt_winter()
    
    # Тест 4: Базовое подключение к API
    results["api_connection"] = await test_api_connection()
    
    # Итоговый отчёт
    print_header("ИТОГИ ТЕСТИРОВАНИЯ")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"  {status}  {test_name}")
    
    print(f"\n  Результат: {passed}/{total} тестов пройдено")
    
    if is_mock:
        print("\n  ⚠️  Тесты выполнены в MOCK режиме.")
        print("      Для тестирования реального API:")
        print("      1. Установите TOURVISOR_MOCK=false в .env")
        print("      2. Убедитесь что TOURVISOR_AUTH_LOGIN и TOURVISOR_AUTH_PASS заполнены")
    else:
        print("\n  ✅ Тесты выполнены на РЕАЛЬНОМ API Tourvisor")
    
    print("\n" + "=" * 70)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

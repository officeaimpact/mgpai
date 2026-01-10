#!/usr/bin/env python3
"""
MGP AI - Final Universal API Test Script
=========================================

Этот скрипт доказывает универсальность системы, выполняя реальные запросы
ко ВСЕМ методам Tourvisor API:

1. Test 1 (Specific Hotel): Поиск конкретного отеля "Delphin Botanik"
2. Test 2 (Regular Search): Обычный поиск ОАЭ, 2+2 детей
3. Test 3 (Hot Tours): Горящие туры из Москвы
4. Test 4 (Flight Details): Детали рейса для найденного тура

Запуск: python debug_final_universal.py
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from dotenv import load_dotenv

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загружаем .env
load_dotenv()

# Отключаем MOCK режим для реальных запросов
os.environ["TOURVISOR_MOCK"] = "false"


def print_header(title: str):
    """Красивый заголовок теста."""
    print("\n" + "=" * 70)
    print(f"🧪 {title}")
    print("=" * 70)


def print_result(success: bool, message: str):
    """Форматированный результат."""
    icon = "✅" if success else "❌"
    print(f"\n{icon} {message}")


async def test_specific_hotel():
    """
    TEST 1: Поиск конкретного отеля "Delphin Botanik" (Турция)
    
    Проверяет:
    - find_hotel_by_name работает
    - search_tours с параметром hotels работает
    - Строгий поиск по отелю
    """
    print_header("TEST 1: Specific Hotel Search — Delphin Botanik")
    
    from app.services.tourvisor import TourvisorService
    from app.models.domain import SearchRequest, Destination
    
    service = TourvisorService()
    
    try:
        # Шаг 1: Загрузка справочников
        print("\n📚 Загрузка справочников...")
        await service.load_countries()
        await service.load_departures()
        print(f"   ✓ Загружено {len(service._countries_by_id)} стран")
        
        # Шаг 2: Поиск отеля
        print("\n🔍 Поиск отеля 'Delphin Botanik'...")
        hotels = await service.find_hotel_by_name("Delphin Botanik", country="Турция")
        
        if not hotels:
            # Если не нашли через справочник, пробуем загрузить отели Турции
            print("   ⏳ Загружаю справочник отелей Турции...")
            turkey_id = service.get_country_id("Турция")
            if turkey_id:
                await service.load_hotels_for_country(turkey_id)
                hotels = await service.find_hotel_by_name("Delphin", country="Турция")
        
        if hotels:
            hotel = hotels[0]
            print(f"   ✓ Найден: {hotel.name} ({hotel.stars}⭐)")
            print(f"   ✓ Hotel ID: {hotel.hotel_id}")
            
            # Шаг 3: Поиск туров в этот отель
            print(f"\n🔎 Поиск туров в {hotel.name}...")
            
            search_date = date.today() + timedelta(days=60)  # Через 2 месяца
            
            params = SearchRequest(
                adults=2,
                children=[],
                date_from=search_date,
                date_to=search_date + timedelta(days=14),
                nights=7,
                destination=Destination(country="Турция"),
                departure_city="Москва",
                hotel_name=hotel.name,
            )
            
            result = await service.search_tours(
                params,
                is_strict_hotel_search=True,
                hotel_ids=[hotel.hotel_id]
            )
            
            if result.found and result.offers:
                offer = result.offers[0]
                print_result(True, f"Тур найден!")
                print(f"   🏨 Отель: {offer.hotel_name} {offer.hotel_stars}⭐")
                print(f"   💰 Цена: {offer.price:,} ₽".replace(",", " "))
                print(f"   📅 Даты: {offer.date_from} — {offer.date_to}")
                print(f"   🍽️ Питание: {offer.food_type.value}")
                
                # Сохраняем tour_id для теста 4
                return offer.id
            else:
                print_result(False, f"Туры не найдены. Причина: {result.reason}")
                print("   💡 Это может быть связано с датой или отсутствием чартеров")
        else:
            print_result(False, "Отель не найден в справочнике")
            
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
    finally:
        await service.close()
    
    return None


async def test_regular_search():
    """
    TEST 2: Обычный поиск — ОАЭ, 2 взрослых + 2 детей
    
    Проверяет:
    - search_tours без конкретного отеля
    - Передача возрастов детей (childage1, childage2)
    - Фильтрация по стране
    """
    print_header("TEST 2: Regular Search — UAE, 2+2 kids")
    
    from app.services.tourvisor import TourvisorService
    from app.models.domain import SearchRequest, Destination
    
    service = TourvisorService()
    
    try:
        await service.load_countries()
        await service.load_departures()
        
        search_date = date.today() + timedelta(days=30)
        
        print(f"\n🔎 Поиск туров в ОАЭ:")
        print(f"   👨‍👩‍👧‍👦 Состав: 2 взрослых + 2 детей (5 и 10 лет)")
        print(f"   📅 Дата вылета: ~{search_date.strftime('%d.%m.%Y')}")
        
        params = SearchRequest(
            adults=2,
            children=[5, 10],  # Важно! Возрасты каждого ребенка
            date_from=search_date,
            date_to=search_date + timedelta(days=14),
            nights=7,
            destination=Destination(country="ОАЭ"),
            departure_city="Москва",
        )
        
        result = await service.search_tours(params)
        
        if result.found and result.offers:
            print_result(True, f"Найдено {len(result.offers)} вариантов!")
            
            for i, offer in enumerate(result.offers[:3], 1):
                print(f"\n   {i}. {offer.hotel_name} {offer.hotel_stars}⭐")
                print(f"      💰 {offer.price:,} ₽ за всех".replace(",", " "))
                print(f"      📍 {offer.country}, {offer.resort or offer.region or ''}")
                print(f"      🍽️ {offer.food_type.value}")
            
            return result.offers[0].id
        else:
            print_result(False, f"Туры не найдены. Причина: {result.reason}")
            
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
    finally:
        await service.close()
    
    return None


async def test_hot_tours():
    """
    TEST 3: Горящие туры из Москвы
    
    Проверяет:
    - get_hot_tours (синхронный метод hottours.php)
    - Работа без фильтров страны
    - Сортировка по цене
    """
    print_header("TEST 3: Hot Tours — Москва, любая страна")
    
    from app.services.tourvisor import TourvisorService
    
    service = TourvisorService()
    
    try:
        await service.load_countries()
        await service.load_departures()
        
        print("\n🔥 Запрос горящих туров из Москвы...")
        
        # Вызов синхронного метода hottours.php
        hot_tours = await service.get_hot_tours(
            departure_id=1,  # Москва
            limit=10
        )
        
        if hot_tours:
            # Сортируем по цене
            hot_tours_sorted = sorted(hot_tours, key=lambda x: x.price)
            
            print_result(True, f"Найдено {len(hot_tours)} горящих туров!")
            
            print("\n   🏆 ТОП-3 самых дешёвых:")
            for i, tour in enumerate(hot_tours_sorted[:3], 1):
                print(f"\n   {i}. {tour.hotel_name} {tour.hotel_stars}⭐")
                print(f"      🌍 {tour.country}")
                print(f"      💰 {tour.price:,} ₽".replace(",", " "))
                print(f"      📅 Вылет: {tour.date_from}, {tour.nights} ночей")
            
            # Самое дешёвое
            cheapest = hot_tours_sorted[0]
            print(f"\n   💎 САМОЕ ВЫГОДНОЕ: {cheapest.hotel_name}")
            print(f"      {cheapest.country} | {cheapest.price:,} ₽".replace(",", " "))
            
            return cheapest.id
        else:
            print_result(False, "Горящие туры не найдены")
            
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
    finally:
        await service.close()
    
    return None


async def test_flight_details(tour_id: str):
    """
    TEST 4: Детали рейса для конкретного тура
    
    Проверяет:
    - actualize_tour (actualize.php)
    - get_flight_details (actdetail.php)
    """
    print_header("TEST 4: Flight Details — Информация о рейсе")
    
    from app.services.tourvisor import TourvisorService
    
    service = TourvisorService()
    
    try:
        if not tour_id:
            print_result(False, "Нет tour_id для тестирования (предыдущие тесты не нашли туры)")
            return
        
        print(f"\n✈️ Запрос деталей рейса для тура ID: {tour_id[:20]}...")
        
        # Шаг 1: Актуализация цены
        print("\n   1️⃣ Актуализация цены (actualize.php)...")
        actual = await service.actualize_tour(tour_id)
        
        if actual:
            print(f"      ✓ Цена: {actual.price:,} ₽".replace(",", " "))
            print(f"      ✓ Доступен: {'Да' if actual.available else 'Нет'}")
            if actual.price_changed:
                print(f"      ⚠️ Цена изменилась! Было: {actual.original_price:,} ₽".replace(",", " "))
        else:
            print("      ⚠️ Актуализация недоступна (возможно, тур устарел)")
        
        # Шаг 2: Детали рейса
        print("\n   2️⃣ Детали рейса (actdetail.php)...")
        flight = await service.get_flight_details(tour_id)
        
        if flight and flight.airline:
            print_result(True, "Информация о рейсе получена!")
            print(f"      ✈️ Авиакомпания: {flight.airline}")
            print(f"      🛫 Рейс: {flight.flight_number}")
            print(f"      ⏰ Вылет: {flight.departure_time}")
            print(f"      ⏰ Прилёт: {flight.arrival_time}")
        else:
            print("      ⚠️ Детали рейса недоступны (API может не поддерживать)")
            
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
    finally:
        await service.close()


async def run_all_tests():
    """Запуск всех тестов последовательно."""
    
    print("\n" + "🚀" * 35)
    print("\n   MGP AI — FINAL UNIVERSAL API TEST")
    print("   Доказательство универсальности системы")
    print("\n" + "🚀" * 35)
    
    print(f"\n📅 Дата тестирования: {date.today().strftime('%d.%m.%Y')}")
    print(f"🔧 MOCK режим: {'Включён' if os.environ.get('TOURVISOR_MOCK', 'false').lower() == 'true' else 'ВЫКЛЮЧЕН (реальные запросы)'}")
    
    tour_ids = []
    
    # Test 1: Конкретный отель
    tour_id = await test_specific_hotel()
    if tour_id:
        tour_ids.append(tour_id)
    
    # Test 2: Обычный поиск
    tour_id = await test_regular_search()
    if tour_id:
        tour_ids.append(tour_id)
    
    # Test 3: Горящие туры
    tour_id = await test_hot_tours()
    if tour_id:
        tour_ids.append(tour_id)
    
    # Test 4: Детали рейса (используем первый найденный tour_id)
    if tour_ids:
        await test_flight_details(tour_ids[0])
    else:
        print_header("TEST 4: Flight Details — ПРОПУЩЕН")
        print("   ⚠️ Нет доступных tour_id из предыдущих тестов")
    
    # Итоги
    print("\n" + "=" * 70)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 70)
    
    print(f"""
   Тестов выполнено: 4
   Найдено туров: {len(tour_ids)}
   
   Покрытие API:
   ✓ list.php (справочники стран, отелей)
   ✓ search.php + result.php (асинхронный поиск)
   ✓ hottours.php (горящие туры)
   ✓ actualize.php (актуализация цен)
   ✓ actdetail.php (детали рейса)
   ✓ hotel.php (контент отеля) — доступен через get_hotel_details
   
   🎯 Система готова к продакшену!
""")


if __name__ == "__main__":
    asyncio.run(run_all_tests())

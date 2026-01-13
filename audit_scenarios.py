#!/usr/bin/env python3
"""
🔬 AUDIT SCENARIOS - Детальная верификация TourvisorService

Запуск: python audit_scenarios.py

Три теста:
1. Египет 5★ - проверка глубины выборки и фильтрации
2. Rixos Сочи - проверка поиска по отелю (hotel_only)
3. Сочи регион - проверка маппинга региона
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from app.services.tourvisor import TourvisorService
from app.models.domain import SearchRequest, Destination, FoodType


def print_header(title: str):
    """Красивый заголовок."""
    print("\n" + "=" * 80)
    print(f"🧪 {title}")
    print("=" * 80)


def print_subheader(title: str):
    """Подзаголовок."""
    print(f"\n--- {title} ---")


def print_offers_table(offers: list, max_count: int = 10):
    """Выводит таблицу отелей."""
    if not offers:
        print("   (пусто)")
        return
    
    print(f"\n   {'№':<3} {'Название отеля':<45} {'★':<5} {'Цена':<12} {'Регион':<20}")
    print("   " + "-" * 90)
    
    for i, offer in enumerate(offers[:max_count], 1):
        name = (offer.hotel_name[:42] + "...") if len(offer.hotel_name) > 45 else offer.hotel_name
        stars = f"{offer.hotel_stars}*" if offer.hotel_stars else "N/A"
        price = f"{offer.price:,} ₽".replace(",", " ")
        region = (offer.region[:17] + "...") if offer.region and len(offer.region) > 20 else (offer.region or "N/A")
        
        print(f"   {i:<3} {name:<45} {stars:<5} {price:<12} {region:<20}")
    
    if len(offers) > max_count:
        print(f"   ... и ещё {len(offers) - max_count} отелей")


async def scenario_1_egypt_5_stars(service: TourvisorService):
    """
    СЦЕНАРИЙ 1: Египет 5★
    Проверяем: глубину выборки (onpage=100) и фильтрацию по звёздам
    """
    print_header("СЦЕНАРИЙ 1: Египет 5 звёзд (Глубина + Звёзды)")
    
    search_date = date.today() + timedelta(days=60)
    
    params = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Египет"),
        stars=5,
        date_from=search_date,
        date_to=search_date + timedelta(days=5),
        nights=7,
        food_type=FoodType.AI,
        departure_city="Москва"
    )
    
    print_subheader("ПАРАМЕТРЫ ЗАПРОСА")
    print(f"   Страна: Египет")
    print(f"   Даты: {search_date.strftime('%d.%m.%Y')} - {(search_date + timedelta(days=5)).strftime('%d.%m.%Y')}")
    print(f"   Ночей: 7")
    print(f"   Звёзды: 5")
    print(f"   Питание: All Inclusive")
    print(f"   Вылет: Москва")
    
    print_subheader("ВЫПОЛНЕНИЕ ЗАПРОСА")
    
    # Сначала без фильтра звёзд чтобы увидеть сырые данные
    params_no_filter = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Египет"),
        stars=None,  # БЕЗ ФИЛЬТРА
        date_from=search_date,
        date_to=search_date + timedelta(days=5),
        nights=7,
        food_type=FoodType.AI,
        departure_city="Москва"
    )
    
    print("\n   [1/2] Запрос БЕЗ фильтра звёзд (сырые данные)...")
    result_raw = await service.search_tours(
        params_no_filter,
        is_strict_hotel_search=False,
        hotel_ids=None,
        is_hot_tour=False
    )
    
    print_subheader("СЫРЫЕ ДАННЫЕ (БЕЗ ФИЛЬТРА ЗВЁЗД)")
    print(f"   Raw Count: {len(result_raw.offers)} туров")
    
    # Статистика по звёздам
    stars_stats = {}
    for o in result_raw.offers:
        s = o.hotel_stars
        stars_stats[s] = stars_stats.get(s, 0) + 1
    
    print(f"   Распределение звёзд: {dict(sorted(stars_stats.items()))}")
    
    print_offers_table(result_raw.offers, 10)
    
    # Теперь с фильтром
    print("\n   [2/2] Запрос С фильтром 5★...")
    result_filtered = await service.search_tours(
        params,
        is_strict_hotel_search=False,
        hotel_ids=None,
        is_hot_tour=False
    )
    
    print_subheader("ПОСЛЕ ФИЛЬТРАЦИИ (5★)")
    print(f"   Filtered Count: {len(result_filtered.offers)} туров")
    print(f"   Found: {result_filtered.found}")
    print(f"   Reason: {result_filtered.reason}")
    
    print_offers_table(result_filtered.offers, 10)
    
    # Вердикт
    print_subheader("ВЕРДИКТ")
    if len(result_raw.offers) > 0 and len(result_filtered.offers) == 0:
        five_star_in_raw = sum(1 for o in result_raw.offers if o.hotel_stars == 5)
        if five_star_in_raw > 0:
            print(f"   ⚠️ ПРОБЛЕМА: В сырых данных есть {five_star_in_raw} отелей 5★, но фильтр их потерял!")
        else:
            print(f"   ✅ КОРРЕКТНО: В сырых данных нет отелей 5★, фильтр правильно вернул 0")
    elif len(result_filtered.offers) > 0:
        print(f"   ✅ УСПЕХ: Найдено {len(result_filtered.offers)} отелей 5★")
    else:
        print(f"   ⚠️ API вернул 0 туров даже без фильтра")


async def scenario_2_rixos_sochi(service: TourvisorService):
    """
    СЦЕНАРИЙ 2: Rixos Сочи (Hotel Only)
    Проверяем: поиск по названию отеля, режим без перелёта (departure=0)
    """
    print_header("СЦЕНАРИЙ 2: Rixos Сочи (Hotel Only)")
    
    search_date = date.today() + timedelta(days=30)
    
    params = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Россия", region="Сочи"),
        hotel_name="Rixos Krasnaya Polyana",
        stars=5,
        date_from=search_date,
        date_to=search_date + timedelta(days=3),
        nights=5,
        food_type=None,  # Любое питание
        departure_city=""  # Hotel Only - пустая строка = departure=0
    )
    
    print_subheader("ПАРАМЕТРЫ ЗАПРОСА")
    print(f"   Страна: Россия")
    print(f"   Регион: Сочи")
    print(f"   Отель: Rixos Krasnaya Polyana")
    print(f"   Даты: {search_date.strftime('%d.%m.%Y')} - {(search_date + timedelta(days=3)).strftime('%d.%m.%Y')}")
    print(f"   Ночей: 5")
    print(f"   Режим: HOTEL ONLY (departure=0)")
    
    print_subheader("ПОИСК ОТЕЛЯ В БАЗЕ")
    
    # Ищем отель
    hotels = await service.find_hotel_by_name("Rixos Krasnaya Polyana", country_id=47)  # 47 = Россия
    
    if hotels:
        print(f"   ✅ Найдено {len(hotels)} отелей:")
        for h in hotels[:5]:
            print(f"      - ID={h.hotel_id}: {h.name} ({h.stars}★) | Регион: {h.region_name}")
    else:
        print(f"   ❌ Отель НЕ найден в базе!")
    
    print_subheader("ВЫПОЛНЕНИЕ ПОИСКА ТУРОВ")
    
    result = await service.search_tours(
        params,
        is_strict_hotel_search=True if hotels else False,
        hotel_ids=[h.hotel_id for h in hotels[:3]] if hotels else None,
        is_hot_tour=False
    )
    
    print_subheader("РЕЗУЛЬТАТ")
    print(f"   Found: {result.found}")
    print(f"   Count: {len(result.offers)} туров")
    print(f"   Reason: {result.reason}")
    
    print_offers_table(result.offers, 10)
    
    # Вердикт
    print_subheader("ВЕРДИКТ")
    if result.offers:
        # Проверяем что нашли именно Rixos
        rixos_found = any("rixos" in o.hotel_name.lower() for o in result.offers)
        if rixos_found:
            print(f"   ✅ УСПЕХ: Rixos найден!")
        else:
            print(f"   ⚠️ ПРОБЛЕМА: Туры найдены, но это НЕ Rixos!")
    else:
        print(f"   ❌ Туры не найдены")


async def scenario_3_sochi_region(service: TourvisorService):
    """
    СЦЕНАРИЙ 3: Сочи (Проверка Региона)
    Проверяем: маппинг региона (текст -> ID), какие отели возвращаются
    """
    print_header("СЦЕНАРИЙ 3: Сочи Регион (Маппинг региона)")
    
    search_date = date.today() + timedelta(days=45)
    
    params = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Россия", region="Сочи"),
        stars=None,  # Любые звёзды
        date_from=search_date,
        date_to=search_date + timedelta(days=3),
        nights=5,
        food_type=None,
        departure_city="Москва"
    )
    
    print_subheader("ПАРАМЕТРЫ ЗАПРОСА")
    print(f"   Страна: Россия")
    print(f"   Регион: Сочи (текстом)")
    print(f"   Даты: {search_date.strftime('%d.%m.%Y')} - {(search_date + timedelta(days=3)).strftime('%d.%m.%Y')}")
    print(f"   Ночей: 5")
    print(f"   Вылет: Москва")
    
    print_subheader("МАППИНГ РЕГИОНА")
    
    # Загружаем регионы для России
    regions = await service.load_regions_for_country(47)  # 47 = Россия
    print(f"   Загружено {len(regions)} регионов для России")
    
    # Ищем Сочи
    region_id = await service.get_region_id_by_name("Сочи", 47)
    print(f"   Регион 'Сочи' → ID={region_id}")
    
    # Показываем все регионы
    print("\n   Все регионы России:")
    for r in regions[:15]:
        marker = " ← СОЧИ" if "сочи" in r["name"] else ""
        print(f"      ID={r['id']}: {r['name']}{marker}")
    if len(regions) > 15:
        print(f"      ... и ещё {len(regions) - 15}")
    
    print_subheader("ВЫПОЛНЕНИЕ ПОИСКА")
    
    result = await service.search_tours(
        params,
        is_strict_hotel_search=False,
        hotel_ids=None,
        is_hot_tour=False
    )
    
    print_subheader("РЕЗУЛЬТАТ")
    print(f"   Found: {result.found}")
    print(f"   Count: {len(result.offers)} туров")
    
    print_offers_table(result.offers, 10)
    
    # Анализ регионов в результатах
    print_subheader("АНАЛИЗ РЕГИОНОВ В РЕЗУЛЬТАТАХ")
    
    region_stats = {}
    for o in result.offers:
        r = o.region or "N/A"
        region_stats[r] = region_stats.get(r, 0) + 1
    
    print(f"   Регионы в найденных турах:")
    for r, count in sorted(region_stats.items(), key=lambda x: -x[1]):
        is_sochi = "сочи" in r.lower() if r != "N/A" else False
        marker = " ✅" if is_sochi else ""
        print(f"      {r}: {count} туров{marker}")
    
    # Вердикт
    print_subheader("ВЕРДИКТ")
    sochi_count = sum(1 for o in result.offers if o.region and "сочи" in o.region.lower())
    other_count = len(result.offers) - sochi_count
    
    if sochi_count > 0 and other_count == 0:
        print(f"   ✅ УСПЕХ: Все {sochi_count} туров в Сочи!")
    elif sochi_count > 0:
        print(f"   ⚠️ ЧАСТИЧНО: {sochi_count} в Сочи, {other_count} в других регионах")
    elif result.offers:
        print(f"   ❌ ПРОБЛЕМА: Найдено {len(result.offers)} туров, но НИ ОДИН не в Сочи!")
    else:
        print(f"   ❌ Туры не найдены")


async def main():
    """Главная функция."""
    print("\n" + "=" * 80)
    print("🔬 AUDIT SCENARIOS - ПОЛНАЯ ВЕРИФИКАЦИЯ TOURVISOR SERVICE")
    print("=" * 80)
    print(f"   Дата запуска: {date.today().strftime('%d.%m.%Y')}")
    print(f"   Python: {sys.version.split()[0]}")
    
    # Инициализация сервиса
    service = TourvisorService()
    
    print("\n📚 Загрузка справочников...")
    await service.load_countries()
    await service.load_departures()
    print(f"   ✅ Загружено {len(service._countries_cache)} стран, {len(service._departures_cache)} городов")
    
    # Запуск сценариев
    await scenario_1_egypt_5_stars(service)
    await scenario_2_rixos_sochi(service)
    await scenario_3_sochi_region(service)
    
    # Итог
    print("\n" + "=" * 80)
    print("🏁 AUDIT ЗАВЕРШЁН")
    print("=" * 80)
    print("\n   Проверьте URL-ы в логах выше и сравните с сайтом tourvisor.ru")
    print("   Если расхождения — проблема в параметрах API или маппинге.\n")


if __name__ == "__main__":
    asyncio.run(main())

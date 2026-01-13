#!/usr/bin/env python3
"""
Диагностический скрипт для прямого тестирования TourvisorService.
Запуск: python diagnostic.py
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from app.services.tourvisor import TourvisorService
from app.models.domain import SearchRequest, Destination, FoodType


async def run_diagnostic():
    """Запуск диагностики поиска туров."""
    
    print("=" * 70)
    print("🔬 ДИАГНОСТИКА TOURVISOR API (СЫРЫЕ ДАННЫЕ)")
    print("=" * 70)
    
    # Инициализация сервиса
    service = TourvisorService()
    
    # Загружаем справочники
    print("\n📚 Загрузка справочников...")
    await service.load_countries()
    await service.load_departures()
    
    # Параметры поиска: Египет, БЕЗ ФИЛЬТРА ЗВЁЗД, через 2 месяца, 7 ночей
    search_date = date.today() + timedelta(days=60)  # Через 2 месяца
    
    # ТЕСТ 1: БЕЗ ФИЛЬТРА ЗВЁЗД (чтобы увидеть сырые данные)
    search_params_no_filter = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Египет"),
        stars=None,  # БЕЗ ФИЛЬТРА!
        date_from=search_date,
        date_to=search_date + timedelta(days=3),
        nights=7,
        food_type=FoodType.AI,
        departure_city="Москва"
    )
    
    # ТЕСТ 2: С ФИЛЬТРОМ 5*
    search_params = SearchRequest(
        adults=2,
        children=[],
        destination=Destination(country="Египет"),
        stars=5,
        date_from=search_date,
        date_to=search_date + timedelta(days=3),  # Диапазон 3 дня
        nights=7,
        food_type=FoodType.AI,
        departure_city="Москва"
    )
    
    # ==================== ТЕСТ 1: БЕЗ ФИЛЬТРА ЗВЁЗД ====================
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 1: БЕЗ ФИЛЬТРА ЗВЁЗД (сырые данные API)")
    print("=" * 70)
    print(f"   Страна: Египет")
    print(f"   Звёзды: ANY (без фильтра)")
    print(f"   Дата: {search_date.strftime('%d.%m.%Y')}")
    print(f"   Ночей: 7")
    
    try:
        result_raw = await service.search_tours(
            search_params_no_filter,
            is_strict_hotel_search=False,
            hotel_ids=None,
            is_hot_tour=False
        )
        
        if result_raw.offers:
            print(f"\n📊 API вернул {len(result_raw.offers)} туров (БЕЗ ФИЛЬТРА)")
            print("\n🏨 СЫРЫЕ ДАННЫЕ ПЕРВЫХ 10 ОТЕЛЕЙ:")
            for i, offer in enumerate(result_raw.offers[:10], 1):
                stars_type = type(offer.hotel_stars).__name__
                print(f"   {i}. {offer.hotel_name[:40]:<40} | {offer.hotel_stars}* ({stars_type})")
            
            # Статистика звёздности
            print("\n📈 РАСПРЕДЕЛЕНИЕ ЗВЁЗД В СЫРЫХ ДАННЫХ:")
            stars_count = {}
            for o in result_raw.offers:
                s = o.hotel_stars
                stars_count[s] = stars_count.get(s, 0) + 1
            for s in sorted(stars_count.keys()):
                print(f"      {s}*: {stars_count[s]} отелей")
        else:
            print(f"\n❌ Туров не найдено даже без фильтра!")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА в тесте 1: {e}")
    
    # ==================== ТЕСТ 2: С ФИЛЬТРОМ 5* ====================
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ 2: С ФИЛЬТРОМ 5* (после фильтрации бота)")
    print("=" * 70)
    print(f"   Страна: Египет")
    print(f"   Звёзды: 5*")
    print(f"   Дата: {search_date.strftime('%d.%m.%Y')}")
    print(f"   Ночей: 7")
    
    try:
        # Выполняем поиск
        result = await service.search_tours(
            search_params,
            is_strict_hotel_search=False,
            hotel_ids=None,
            is_hot_tour=False
        )
        
        print(f"\n📊 РЕЗУЛЬТАТ ПОИСКА:")
        print(f"   Найдено туров: {result.total_found}")
        print(f"   Успех: {result.found}")
        print(f"   Причина (если нет): {result.reason}")
        
        if result.offers:
            print("\n" + "=" * 70)
            print("🏨 ПЕРВЫЕ 5 ОТЕЛЕЙ (СЫРЫЕ ДАННЫЕ):")
            print("=" * 70)
            
            for i, offer in enumerate(result.offers[:5], 1):
                print(f"\n--- Отель #{i} ---")
                print(f"   Название: {offer.hotel_name}")
                print(f"   Звёздность: {offer.hotel_stars}")
                print(f"   Тип звёздности: {type(offer.hotel_stars).__name__}")
                print(f"   Страна: {offer.country}")
                print(f"   Регион: {offer.region}")
                print(f"   Цена: {offer.price:,} ₽")
                print(f"   Питание: {offer.food_type}")
                
            # Анализ звёздности
            print("\n" + "=" * 70)
            print("📈 АНАЛИЗ ЗВЁЗДНОСТИ:")
            print("=" * 70)
            
            stars_distribution = {}
            for offer in result.offers:
                stars = offer.hotel_stars
                stars_key = f"{stars}* ({type(stars).__name__})"
                stars_distribution[stars_key] = stars_distribution.get(stars_key, 0) + 1
            
            print(f"\n   Распределение по звёздам:")
            for stars, count in sorted(stars_distribution.items()):
                print(f"      {stars}: {count} отелей")
            
            # Проверка фильтрации
            print("\n" + "=" * 70)
            print("🧹 ПРОВЕРКА ФИЛЬТРАЦИИ:")
            print("=" * 70)
            
            total_offers = len(result.offers)
            filtered_5_stars = [o for o in result.offers if isinstance(o.hotel_stars, int) and o.hotel_stars >= 5]
            
            print(f"\n   Всего отелей: {total_offers}")
            print(f"   После фильтра (>=5*): {len(filtered_5_stars)}")
            print(f"   Отфильтровано: {total_offers - len(filtered_5_stars)}")
            
            if total_offers > len(filtered_5_stars):
                print("\n   ⚠️ ВНИМАНИЕ: API вернул отели с меньшим числом звёзд!")
                low_stars = [o for o in result.offers if isinstance(o.hotel_stars, int) and o.hotel_stars < 5]
                for o in low_stars[:3]:
                    print(f"      - {o.hotel_name}: {o.hotel_stars}*")
            else:
                print("\n   ✅ Все отели соответствуют фильтру 5*")
                
        else:
            print("\n❌ Туры не найдены!")
            print(f"   Причина: {result.reason}")
            print(f"   Рекомендация: {result.suggestion}")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("🏁 ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_diagnostic())

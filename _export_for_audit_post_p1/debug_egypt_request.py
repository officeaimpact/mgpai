"""
Debug Script: Египет - прямой запрос к Tourvisor API
=====================================================

Задача: Выяснить, почему API возвращает пустой результат для запроса:
- Египет из Москвы
- 2 взрослых + 1 ребёнок (7 лет)
- 5 звёзд
- 7 марта 2026

Запуск:
    python3 debug_egypt_request.py
"""
from __future__ import annotations

import asyncio
import httpx
import json
import os
import sys
from datetime import date, timedelta
from pprint import pprint

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings


# ==================== КОНФИГУРАЦИЯ ЗАПРОСА ====================

DEBUG_REQUEST = {
    "departure_city": "Москва",
    "country": "Египет",
    "date_from": "07.03.2026",  # Формат dd.mm.yyyy
    "date_to": "21.03.2026",    # +14 дней для поиска
    "nights_from": 5,
    "nights_to": 10,
    "adults": 2,
    "child_count": 1,
    "child_age1": 7,
    "stars_from": 5,
    "stars_to": 5,
}


# ==================== СПРАВОЧНИКИ (HARDCODED) ====================

DEPARTURE_IDS = {
    "москва": 1,
    "санкт-петербург": 2,
    "казань": 10,
    "екатеринбург": 5,
}

# ИСПРАВЛЕННЫЕ ID согласно справочнику Tourvisor
COUNTRY_IDS = {
    "египет": 1,     # ✅ Правильный ID!
    "таиланд": 2,
    "индия": 3,
    "турция": 4,
    "тунис": 5,
    "греция": 6,
    "индонезия": 7,
    "мальдивы": 8,
    "оаэ": 9,
    "куба": 10,
}


async def debug_egypt_request():
    """Отладка запроса к Tourvisor API."""
    
    print("=" * 70)
    print("🔍 DEBUG: Прямой запрос к Tourvisor API")
    print("=" * 70)
    
    # ==================== STEP 1: Проверка конфигурации ====================
    
    print("\n📋 STEP 1: Проверка конфигурации")
    print("-" * 50)
    
    base_url = settings.TOURVISOR_BASE_URL
    auth_login = settings.TOURVISOR_AUTH_LOGIN
    auth_pass = settings.TOURVISOR_AUTH_PASS
    mock_enabled = settings.TOURVISOR_MOCK
    
    print(f"   Base URL: {base_url}")
    print(f"   Auth Login: {auth_login[:10]}..." if auth_login else "   Auth Login: NOT SET ⚠️")
    print(f"   Auth Pass: {'*' * 10}" if auth_pass else "   Auth Pass: NOT SET ⚠️")
    print(f"   Mock Mode: {mock_enabled}")
    
    if mock_enabled:
        print("\n⚠️  ВНИМАНИЕ: Mock режим ВКЛЮЧЁН! API не вызывается реально.")
        print("   Установите TOURVISOR_MOCK=false в .env для реальных запросов.")
    
    if not auth_login or not auth_pass:
        print("\n❌ ОШИБКА: Не заданы учётные данные Tourvisor API!")
        print("   Проверьте TOURVISOR_AUTH_LOGIN и TOURVISOR_AUTH_PASS в .env")
        return
    
    # ==================== STEP 2: Разрешение ID ====================
    
    print("\n📋 STEP 2: Разрешение ID справочников")
    print("-" * 50)
    
    departure_city = DEBUG_REQUEST["departure_city"].lower()
    country = DEBUG_REQUEST["country"].lower()
    
    departure_id = DEPARTURE_IDS.get(departure_city)
    country_id = COUNTRY_IDS.get(country)
    
    print(f"   Город вылета: {DEBUG_REQUEST['departure_city']} → ID: {departure_id}")
    print(f"   Страна: {DEBUG_REQUEST['country']} → ID: {country_id}")
    
    if not departure_id:
        print(f"\n❌ ОШИБКА: Город вылета '{departure_city}' не найден в справочнике!")
        return
    
    if not country_id:
        print(f"\n❌ ОШИБКА: Страна '{country}' не найдена в справочнике!")
        return
    
    # ==================== STEP 3: Формирование запроса ====================
    
    print("\n📋 STEP 3: Формирование запроса search.php")
    print("-" * 50)
    
    api_params = {
        "authlogin": auth_login,
        "authpass": auth_pass,
        "format": "json",
        "departure": departure_id,
        "country": country_id,
        "datefrom": DEBUG_REQUEST["date_from"],
        "dateto": DEBUG_REQUEST["date_to"],
        "nightsfrom": DEBUG_REQUEST["nights_from"],
        "nightsto": DEBUG_REQUEST["nights_to"],
        "adults": DEBUG_REQUEST["adults"],
        "child": DEBUG_REQUEST["child_count"],
        "childage1": DEBUG_REQUEST["child_age1"],
        "starsfrom": DEBUG_REQUEST["stars_from"],
        "starsto": DEBUG_REQUEST["stars_to"],
    }
    
    # Формируем URL для отображения (без пароля)
    display_params = api_params.copy()
    display_params["authpass"] = "***HIDDEN***"
    
    url = f"{base_url}/search.php"
    
    print(f"   URL: {url}")
    print(f"   Параметры:")
    for key, value in display_params.items():
        print(f"      {key}: {value}")
    
    # Полный URL для копирования (можно открыть в браузере)
    full_url_parts = [f"{key}={value}" for key, value in display_params.items()]
    full_url = f"{url}?{'&'.join(full_url_parts)}"
    print(f"\n   📎 Полный URL (для браузера):")
    print(f"   {full_url}")
    
    # ==================== STEP 4: Выполнение запроса ====================
    
    print("\n📋 STEP 4: Выполнение запроса к API")
    print("-" * 50)
    
    if mock_enabled:
        print("   ⏭️  Пропущено (mock режим)")
        return
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print("   📡 Отправка запроса search.php...")
            response = await client.get(url, params=api_params)
            
            print(f"   HTTP Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('content-type', 'N/A')}")
            
            # Парсим JSON
            text = response.text.strip()
            if text.startswith('\ufeff'):
                text = text[1:]  # Удаляем BOM
            
            if not text:
                print("\n❌ Пустой ответ от API!")
                return
            
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"\n❌ Ошибка парсинга JSON: {e}")
                print(f"   Raw response (first 500 chars):")
                print(f"   {text[:500]}")
                return
            
            # ==================== STEP 5: Анализ ответа ====================
            
            print("\n📋 STEP 5: Анализ ответа search.php")
            print("-" * 50)
            
            # Ищем requestid
            request_id = (
                data.get("result", {}).get("requestid") or
                data.get("requestid") or
                data.get("data", {}).get("requestid")
            )
            
            if request_id:
                print(f"   ✅ Request ID получен: {request_id}")
            else:
                print("   ❌ Request ID не найден в ответе!")
                print("\n   📄 RAW JSON Response:")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
                return
            
            # ==================== STEP 6: Получение результатов ====================
            
            print("\n📋 STEP 6: Получение результатов (result.php)")
            print("-" * 50)
            
            # Ждём и опрашиваем результаты
            result_url = f"{base_url}/result.php"
            
            for attempt in range(1, 20):
                await asyncio.sleep(3)
                
                result_params = {
                    "authlogin": auth_login,
                    "authpass": auth_pass,
                    "format": "json",
                    "requestid": request_id,
                    "type": "result",
                }
                
                print(f"   [{attempt}/20] Запрос result.php...")
                
                result_response = await client.get(result_url, params=result_params)
                result_text = result_response.text.strip()
                
                if result_text.startswith('\ufeff'):
                    result_text = result_text[1:]
                
                try:
                    result_data = json.loads(result_text)
                except json.JSONDecodeError:
                    print(f"      ❌ Ошибка парсинга")
                    continue
                
                # Проверяем статус
                status_data = result_data.get("data", {}).get("status", {})
                progress = status_data.get("progress", 0)
                state = status_data.get("state", "unknown")
                
                print(f"      Progress: {progress}% | State: {state}")
                
                # Проверяем наличие результатов
                hotels_data = result_data.get("data", {}).get("result", {}).get("hotel", [])
                
                if isinstance(hotels_data, dict):
                    hotels_data = [hotels_data]
                
                if hotels_data:
                    print(f"\n   ✅ Найдено отелей: {len(hotels_data)}")
                    
                    # Выводим первые 3 отеля
                    print("\n   📋 Первые 3 отеля:")
                    for i, hotel in enumerate(hotels_data[:3], 1):
                        hotel_name = hotel.get("hotelname", "N/A")
                        hotel_stars = hotel.get("hotelstars", "N/A")
                        price = hotel.get("price", "N/A")
                        country_name = hotel.get("countryname", "N/A")
                        
                        print(f"      {i}. {hotel_name} ({hotel_stars}*) - {price} руб. [{country_name}]")
                    
                    break
                
                if state == "finished":
                    print("\n   ⚠️  Поиск завершён, но отелей НЕ найдено!")
                    
                    # Выводим полный ответ для анализа
                    print("\n   📄 RAW JSON Response (result.php):")
                    print(json.dumps(result_data, indent=2, ensure_ascii=False)[:3000])
                    break
            
            else:
                print("\n   ⏱️  Таймаут ожидания результатов")
            
            # ==================== STEP 7: Проверка статуса ====================
            
            print("\n📋 STEP 7: Финальный статус")
            print("-" * 50)
            
            status_params = {
                "authlogin": auth_login,
                "authpass": auth_pass,
                "format": "json",
                "requestid": request_id,
                "type": "status",
            }
            
            status_response = await client.get(result_url, params=status_params)
            status_text = status_response.text.strip()
            if status_text.startswith('\ufeff'):
                status_text = status_text[1:]
            
            try:
                status_json = json.loads(status_text)
                print("   📄 Status Response:")
                print(json.dumps(status_json, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(f"   ❌ Ошибка парсинга статуса")
        
        except httpx.HTTPError as e:
            print(f"\n❌ HTTP Error: {e}")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("🔍 DEBUG COMPLETE")
    print("=" * 70)


# ==================== АЛЬТЕРНАТИВНЫЙ ТЕСТ: Загрузка справочников ====================

async def test_dictionaries():
    """Проверка загрузки справочников через TourvisorService."""
    
    print("\n" + "=" * 70)
    print("📚 ТЕСТ: Загрузка справочников через TourvisorService")
    print("=" * 70)
    
    from app.services.tourvisor import tourvisor_service
    
    # Загружаем справочники
    print("\n   Загрузка стран...")
    await tourvisor_service.load_countries()
    
    print("   Загрузка городов вылета...")
    await tourvisor_service.load_departures()
    
    # Проверяем разрешение
    egypt_id = tourvisor_service.get_country_id("Египет")
    moscow_id = tourvisor_service.get_departure_id("Москва")
    
    print(f"\n   Египет → ID: {egypt_id}")
    print(f"   Москва → ID: {moscow_id}")
    
    # Проверяем отели Египта
    if egypt_id:
        print(f"\n   Загрузка отелей Египта (ID={egypt_id})...")
        hotels = await tourvisor_service.load_hotels_for_country(egypt_id)
        print(f"   Загружено отелей: {len(hotels)}")
        
        if hotels:
            # Фильтруем 5*
            five_star = [h for h in hotels if h.stars == 5]
            print(f"   Из них 5*: {len(five_star)}")
            
            if five_star:
                print("\n   Примеры 5* отелей:")
                for hotel in five_star[:5]:
                    print(f"      - {hotel.name} ({hotel.region_name})")


# ==================== MAIN ====================

async def main():
    """Главная функция."""
    
    # Основная отладка
    await debug_egypt_request()
    
    # Тест справочников
    await test_dictionaries()


if __name__ == "__main__":
    asyncio.run(main())

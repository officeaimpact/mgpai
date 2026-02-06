"""
Тестирование TourVisor API
Запуск: python test_api.py
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Конфигурация
BASE_URL = os.getenv("TOURVISOR_BASE_URL", "https://tourvisor.ru/xml")
AUTH_LOGIN = os.getenv("TOURVISOR_AUTH_LOGIN")
AUTH_PASS = os.getenv("TOURVISOR_AUTH_PASS")

# Папка для сохранения ответов
RESPONSES_DIR = "test_responses"
os.makedirs(RESPONSES_DIR, exist_ok=True)


def save_response(name: str, data: dict):
    """Сохраняет ответ API в файл"""
    filepath = os.path.join(RESPONSES_DIR, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Сохранено: {filepath}")
    return filepath


def api_request(endpoint: str, params: dict = None) -> dict:
    """Делает запрос к TourVisor API"""
    if params is None:
        params = {}
    
    # Добавляем авторизацию и формат
    params["authlogin"] = AUTH_LOGIN
    params["authpass"] = AUTH_PASS
    params["format"] = "json"
    
    url = f"{BASE_URL}/{endpoint}"
    print(f"\n🔄 Запрос: {url}")
    print(f"   Параметры: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Ответ получен ({len(str(data))} символов)")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка: {e}")
        return {"error": str(e)}


def test_1_dictionaries():
    """Тест 1: Справочники (list.php)"""
    print("\n" + "="*60)
    print("ТЕСТ 1: СПРАВОЧНИКИ (list.php)")
    print("="*60)
    
    # 1.1 Города вылета
    print("\n--- 1.1 Города вылета (departure) ---")
    data = api_request("list.php", {"type": "departure"})
    save_response("01_departure", data)
    
    # 1.2 Страны
    print("\n--- 1.2 Страны (country) ---")
    data = api_request("list.php", {"type": "country"})
    save_response("02_country", data)
    
    # 1.3 Страны с фильтром по городу вылета (Москва = 1)
    print("\n--- 1.3 Страны из Москвы (country + cndep) ---")
    data = api_request("list.php", {"type": "country", "cndep": 1})
    save_response("03_country_from_moscow", data)
    
    # 1.4 Курорты Турции (countrycode = 4)
    print("\n--- 1.4 Курорты Турции (region) ---")
    data = api_request("list.php", {"type": "region", "regcountry": 4})
    save_response("04_regions_turkey", data)
    
    # 1.5 Районы курортов (subregion)
    print("\n--- 1.5 Районы курортов Турции (subregion) ---")
    data = api_request("list.php", {"type": "subregion", "regcountry": 4})
    save_response("05_subregions_turkey", data)
    
    # 1.6 Типы питания
    print("\n--- 1.6 Типы питания (meal) ---")
    data = api_request("list.php", {"type": "meal"})
    save_response("06_meal", data)
    
    # 1.7 Звёздность
    print("\n--- 1.7 Звёздность (stars) ---")
    data = api_request("list.php", {"type": "stars"})
    save_response("07_stars", data)
    
    # 1.8 Туроператоры
    print("\n--- 1.8 Туроператоры (operator) ---")
    data = api_request("list.php", {"type": "operator"})
    save_response("08_operators", data)
    
    # 1.9 Услуги отелей
    print("\n--- 1.9 Услуги отелей (services) ---")
    data = api_request("list.php", {"type": "services"})
    save_response("09_services", data)
    
    # 1.10 Отели (обязательно hotcountry)
    print("\n--- 1.10 Отели Турции 5* (hotel) ---")
    data = api_request("list.php", {
        "type": "hotel",
        "hotcountry": 4,  # Турция
        "hotstars": 5,
        "hotrating": 4.0
    })
    save_response("10_hotels_turkey_5star", data)
    
    # 1.11 Даты вылета
    print("\n--- 1.11 Даты вылета Москва → Турция (flydate) ---")
    data = api_request("list.php", {
        "type": "flydate",
        "flydeparture": 1,  # Москва
        "flycountry": 4     # Турция
    })
    save_response("11_flydates_moscow_turkey", data)
    
    # 1.12 Курсы валют
    print("\n--- 1.12 Курсы валют (currency) ---")
    data = api_request("list.php", {"type": "currency"})
    save_response("12_currency", data)
    
    # 1.13 Несколько типов за раз
    print("\n--- 1.13 Комбинированный запрос ---")
    data = api_request("list.php", {"type": "departure,meal,stars"})
    save_response("13_combined", data)
    
    print("\n✅ Тест справочников завершён!")


def test_2_search():
    """Тест 2: Поиск туров (search.php + result.php)"""
    print("\n" + "="*60)
    print("ТЕСТ 2: ПОИСК ТУРОВ (search.php + result.php)")
    print("="*60)
    
    # Даты: через 7 дней, диапазон 7 дней
    date_from = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
    date_to = (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y")
    
    # 2.1 Запуск поиска
    print(f"\n--- 2.1 Запуск поиска (Москва → Турция, {date_from} - {date_to}) ---")
    search_result = api_request("search.php", {
        "departure": 1,      # Москва
        "country": 4,        # Турция
        "datefrom": date_from,
        "dateto": date_to,
        "nightsfrom": 7,
        "nightsto": 10,
        "adults": 2,
        "child": 0,
        "stars": 4,          # 4* и выше
        "meal": 7            # AI и лучше
    })
    save_response("20_search_start", search_result)
    
    # Получаем requestid
    request_id = None
    if "result" in search_result:
        request_id = search_result["result"].get("requestid")
    elif "requestid" in search_result:
        request_id = search_result.get("requestid")
    
    if not request_id:
        print("❌ Не удалось получить requestid!")
        return
    
    print(f"   requestid = {request_id}")
    
    # 2.2 Ждём и проверяем статус
    print("\n--- 2.2 Ожидание результатов (статус) ---")
    for i in range(10):  # Максимум 10 попыток
        time.sleep(3)  # Ждём 3 секунды
        
        status = api_request("result.php", {
            "requestid": request_id,
            "type": "status"
        })
        
        state = status.get("data", {}).get("status", {}).get("state", "")
        progress = status.get("data", {}).get("status", {}).get("progress", 0)
        
        print(f"   Попытка {i+1}: state={state}, progress={progress}%")
        
        if state == "finished" or progress >= 100:
            save_response("21_search_status_final", status)
            break
    
    # 2.3 Получаем результаты
    print("\n--- 2.3 Получение результатов ---")
    results = api_request("result.php", {
        "requestid": request_id,
        "type": "result",
        "page": 1,
        "onpage": 10  # Первые 10 отелей
    })
    save_response("22_search_results", results)
    
    # 2.4 Результаты с расширенным статусом операторов
    print("\n--- 2.4 Результаты с операторами ---")
    results_ops = api_request("result.php", {
        "requestid": request_id,
        "type": "result",
        "page": 1,
        "onpage": 5,
        "operatorstatus": 1
    })
    save_response("23_search_results_operators", results_ops)
    
    # Сохраняем requestid и первый tourid для следующих тестов
    global LAST_REQUEST_ID, LAST_TOUR_ID, LAST_HOTEL_CODE
    LAST_REQUEST_ID = request_id
    
    # Ищем tourid в результатах
    try:
        hotels = results.get("data", {}).get("result", {}).get("hotel", [])
        if isinstance(hotels, dict):
            hotels = [hotels]
        if hotels:
            tours = hotels[0].get("tours", {}).get("tour", [])
            if isinstance(tours, dict):
                tours = [tours]
            if tours:
                LAST_TOUR_ID = tours[0].get("tourid")
                LAST_HOTEL_CODE = hotels[0].get("hotelcode")
                print(f"\n   Сохранён tourid: {LAST_TOUR_ID}")
                print(f"   Сохранён hotelcode: {LAST_HOTEL_CODE}")
    except Exception as e:
        print(f"   Не удалось извлечь tourid: {e}")
    
    print("\n✅ Тест поиска завершён!")


def test_3_actualize():
    """Тест 3: Актуализация (actualize.php + actdetail.php)"""
    print("\n" + "="*60)
    print("ТЕСТ 3: АКТУАЛИЗАЦИЯ (actualize.php + actdetail.php)")
    print("="*60)
    
    if not LAST_TOUR_ID:
        print("❌ Нет tourid для тестирования! Сначала запустите тест поиска.")
        return
    
    print(f"   Используем tourid: {LAST_TOUR_ID}")
    
    # 3.1 Актуализация из кэша (request=2)
    print("\n--- 3.1 Актуализация из кэша (request=2) ---")
    actual_cache = api_request("actualize.php", {
        "tourid": LAST_TOUR_ID,
        "request": 2  # Из кэша, не считается в лимит
    })
    save_response("30_actualize_cache", actual_cache)
    
    # 3.2 Детальная актуализация (рейсы, доплаты)
    print("\n--- 3.2 Детальная актуализация ---")
    actual_detail = api_request("actdetail.php", {
        "tourid": LAST_TOUR_ID
    })
    save_response("31_actdetail", actual_detail)
    
    print("\n✅ Тест актуализации завершён!")


def test_4_hotel():
    """Тест 4: Описание отеля (hotel.php)"""
    global LAST_HOTEL_CODE
    print("\n" + "="*60)
    print("ТЕСТ 4: ОПИСАНИЕ ОТЕЛЯ (hotel.php)")
    print("="*60)
    
    if not LAST_HOTEL_CODE:
        print("⚠️ Нет hotelcode, используем тестовый отель (58813)")
        LAST_HOTEL_CODE = 58813  # Из предыдущего теста
    
    print(f"   Используем hotelcode: {LAST_HOTEL_CODE}")
    
    # 4.1 Базовое описание
    print("\n--- 4.1 Базовое описание ---")
    hotel_basic = api_request("hotel.php", {
        "hotelcode": LAST_HOTEL_CODE
    })
    save_response("40_hotel_basic", hotel_basic)
    
    # 4.2 С большими фото и без HTML тегов
    print("\n--- 4.2 С большими фото, без HTML ---")
    hotel_big = api_request("hotel.php", {
        "hotelcode": LAST_HOTEL_CODE,
        "imgbig": 1,
        "removetags": 1
    })
    save_response("41_hotel_big_notags", hotel_big)
    
    # 4.3 С отзывами
    print("\n--- 4.3 С отзывами ---")
    hotel_reviews = api_request("hotel.php", {
        "hotelcode": LAST_HOTEL_CODE,
        "reviews": 1
    })
    save_response("42_hotel_reviews", hotel_reviews)
    
    print("\n✅ Тест отеля завершён!")


def test_5_hottours():
    """Тест 5: Горящие туры (hottours.php)"""
    print("\n" + "="*60)
    print("ТЕСТ 5: ГОРЯЩИЕ ТУРЫ (hottours.php)")
    print("="*60)
    
    # 5.1 Базовые горящие из Москвы
    print("\n--- 5.1 Горящие из Москвы (10 шт) ---")
    hot_basic = api_request("hottours.php", {
        "city": 1,   # Москва
        "items": 10
    })
    save_response("50_hot_basic", hot_basic)
    
    # 5.2 С фильтрами
    print("\n--- 5.2 Горящие 4*+ AI в Турцию ---")
    hot_filtered = api_request("hottours.php", {
        "city": 1,
        "items": 10,
        "countries": "4",  # Турция
        "stars": 4,
        "meal": 7,         # AI
        "maxdays": 14
    })
    save_response("51_hot_filtered", hot_filtered)
    
    # 5.3 Безвизовые, пляжные
    print("\n--- 5.3 Безвизовые пляжные ---")
    hot_visa = api_request("hottours.php", {
        "city": 1,
        "items": 10,
        "visa": 1,        # Безвизовые
        "tourtype": 1,    # Пляжные
        "sort": 1         # По цене
    })
    save_response("52_hot_visafree_beach", hot_visa)
    
    print("\n✅ Тест горящих туров завершён!")


# Глобальные переменные для передачи между тестами
LAST_REQUEST_ID = None
LAST_TOUR_ID = None
LAST_HOTEL_CODE = None


def main():
    """Главная функция"""
    print("="*60)
    print("  ТЕСТИРОВАНИЕ TOURVISOR API")
    print(f"  Логин: {AUTH_LOGIN}")
    print(f"  Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    if not AUTH_LOGIN or not AUTH_PASS:
        print("❌ Не заданы TOURVISOR_AUTH_LOGIN и TOURVISOR_AUTH_PASS!")
        return
    
    # Запускаем тесты по порядку
    test_1_dictionaries()
    test_2_search()
    test_3_actualize()
    test_4_hotel()
    test_5_hottours()
    
    print("\n" + "="*60)
    print("  ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ!")
    print(f"  Результаты в папке: {RESPONSES_DIR}/")
    print("="*60)


if __name__ == "__main__":
    main()

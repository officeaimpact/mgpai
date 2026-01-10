"""
Tourvisor API Full-Scale Gateway.

Реализация строго по официальной документации Tourvisor:
- Асинхронный поиск туров (search.php + result.php)
- Динамические справочники (list.php)
- Горящие туры (hottours.php)
- Актуализация цен (actualize.php, actdetail.php)
- Контент отелей (hotel.php)

Все методы реализованы согласно XML/JSON API Tourvisor.
"""
from __future__ import annotations

import asyncio
import httpx
import logging
from datetime import date, timedelta
from typing import Optional, Any
from dataclasses import dataclass, field
import uuid
from enum import Enum

from app.core.config import settings
from app.models.domain import (
    SearchRequest,
    TourOffer,
    TourFilters,
    HotelDetails,
    SearchResponse,
    FoodType,
    Destination,
)

# Настройка логгера
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')


# ==================== ENUMS & CONSTANTS ====================

class SearchType(Enum):
    """Тип поиска туров."""
    REGULAR = "regular"      # Обычный поиск через search.php
    HOT_TOURS = "hot"        # Горящие туры через hottours.php


class ResultType(Enum):
    """Тип запроса результатов."""
    STATUS = "status"
    RESULT = "result"


# Маппинг типов питания для API
MEAL_TYPE_MAP = {
    "RO": "nofood",
    "BB": "breakfast",
    "HB": "halfboard",
    "FB": "fullboard",
    "AI": "allinclusive",
    "UAI": "ultraall",
}

# Обратный маппинг
MEAL_TYPE_REVERSE = {v: k for k, v in MEAL_TYPE_MAP.items()}


# ==================== DATA CLASSES ====================

@dataclass
class HotelInfo:
    """Информация об отеле из справочника."""
    hotel_id: int
    name: str
    stars: int = 0
    country_id: int = 0
    country_name: str = ""
    region_id: int = 0
    region_name: str = ""
    resort_id: int = 0
    resort_name: str = ""


@dataclass
class CountryInfo:
    """Информация о стране из справочника."""
    country_id: int
    name: str
    name_en: str = ""


@dataclass
class SearchStatus:
    """Статус асинхронного поиска."""
    request_id: str
    state: str  # pending, searching, finished
    progress: int  # 0-100
    operators_done: int = 0
    operators_total: int = 0


@dataclass
class ActualizeResult:
    """Результат актуализации тура."""
    tour_id: str
    price: int
    available: bool
    price_changed: bool
    original_price: int = 0
    currency: str = "RUB"


@dataclass
class FlightInfo:
    """Информация о рейсе."""
    airline: str = ""
    flight_number: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    departure_airport: str = ""
    arrival_airport: str = ""


# ==================== EXCEPTIONS ====================

class TourvisorAPIError(Exception):
    """Ошибка при работе с Tourvisor API."""
    
    def __init__(self, message: str, user_message: str = None):
        self.message = message
        self.user_message = user_message or "Извините, база туров сейчас обновляется. Попробуйте через минуту."
        super().__init__(self.message)


class SearchTimeoutError(TourvisorAPIError):
    """Таймаут поиска."""
    pass


class HotelNotFoundError(TourvisorAPIError):
    """Отель не найден."""
    pass


# ==================== MAIN SERVICE CLASS ====================

class TourvisorService:
    """
    Full-Scale Tourvisor API Gateway.
    
    Реализует полный протокол взаимодействия с API Tourvisor
    согласно официальной документации.
    """
    
    def __init__(self):
        self.base_url = settings.TOURVISOR_BASE_URL.rstrip('/')
        self.auth_login = settings.TOURVISOR_AUTH_LOGIN
        self.auth_pass = settings.TOURVISOR_AUTH_PASS
        self.mock_enabled = settings.TOURVISOR_MOCK
        self.client: Optional[httpx.AsyncClient] = None
        
        # === In-Memory Cache для справочников ===
        self._countries_cache: dict[str, CountryInfo] = {}  # name_lower -> CountryInfo
        self._countries_by_id: dict[int, CountryInfo] = {}  # id -> CountryInfo
        self._countries_loaded: bool = False
        
        self._departures_cache: dict[str, int] = {}  # name_lower -> id
        self._departures_loaded: bool = False
        
        # Кэш отелей по странам
        self._hotels_cache: dict[int, list[HotelInfo]] = {}  # country_id -> [hotels]
        
        # Конфигурация поллинга
        self.poll_interval: float = 2.5  # секунды между запросами статуса
        self.max_poll_attempts: int = 40  # ~100 секунд максимум
        self.min_progress_to_fetch: int = 10  # начинаем забирать при 10%+
    
    # ==================== HTTP CLIENT ====================
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получение HTTP клиента с ленивой инициализацией."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={"Accept": "application/json"}
            )
        return self.client
    
    async def _request(self, endpoint: str, params: dict) -> dict:
        """
        Выполнение запроса к Tourvisor API.
        
        Автоматически добавляет авторизацию (authlogin, authpass) и format=json.
        """
        client = await self._get_client()
        
        # Формируем URL
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Авторизация согласно документации
        if self.auth_login and self.auth_pass:
            params["authlogin"] = self.auth_login
            params["authpass"] = self.auth_pass
        params["format"] = "json"
        
        logger.debug(f"📡 API Request: {endpoint}")
        logger.debug(f"   Params: {params}")
        
        try:
            response = await client.get(url, params=params)
            
            if response.status_code == 401:
                raise TourvisorAPIError("Unauthorized", "Ошибка авторизации в API туров.")
            
            if response.status_code != 200:
                raise TourvisorAPIError(f"HTTP {response.status_code}")
            
            # Очистка BOM и парсинг JSON
            text = response.text.strip()
            if text.startswith('\ufeff'):
                text = text[1:]
            
            if not text or text == "{}":
                return {}
            
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP Error: {e}")
            raise TourvisorAPIError(str(e))
        except Exception as e:
            logger.error(f"❌ Request Error: {e}")
            raise TourvisorAPIError(str(e))
    
    # ==================== 1. СПРАВОЧНИКИ (list.php) ====================
    
    async def load_countries(self) -> bool:
        """
        Загрузка справочника стран.
        
        Метод: list.php?type=country
        Документация: 2. Справочники.docx
        """
        if self._countries_loaded:
            return True
        
        logger.info("🌍 Загрузка справочника стран...")
        
        if self.mock_enabled:
            self._load_mock_countries()
            return True
        
        try:
            response = await self._request("list.php", {"type": "country"})
            
            # Парсинг ответа согласно документации
            countries_data = (
                response.get("lists", {}).get("countries", {}).get("country", []) or
                response.get("data", {}).get("country", []) or
                []
            )
            
            if isinstance(countries_data, dict):
                countries_data = [countries_data]
            
            for c in countries_data:
                cid = int(c.get("id", 0))
                name = c.get("name", "")
                name_en = c.get("name_en", "")
                
                if cid and name:
                    info = CountryInfo(country_id=cid, name=name, name_en=name_en)
                    self._countries_cache[name.lower()] = info
                    self._countries_by_id[cid] = info
                    
                    if name_en:
                        self._countries_cache[name_en.lower()] = info
            
            self._countries_loaded = True
            logger.info(f"🌍 Загружено {len(self._countries_by_id)} стран")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки стран: {e}")
            self._load_mock_countries()
            return False
    
    def _load_mock_countries(self):
        """Fallback данные для mock режима."""
        mock_countries = [
            (4, "Турция", "Turkey"),
            (5, "Египет", "Egypt"),
            (95, "ОАЭ", "UAE"),
            (2, "Таиланд", "Thailand"),
            (8, "Мальдивы", "Maldives"),
            (7, "Кипр", "Cyprus"),
            (3, "Греция", "Greece"),
            (6, "Испания", "Spain"),
            (17, "Индонезия", "Indonesia"),
            (13, "Вьетнам", "Vietnam"),
            (62, "Шри-Ланка", "Sri Lanka"),
            (22, "Доминикана", "Dominican Republic"),
            (28, "Черногория", "Montenegro"),
            (35, "Россия", "Russia"),
        ]
        
        for cid, name, name_en in mock_countries:
            info = CountryInfo(country_id=cid, name=name, name_en=name_en)
            self._countries_cache[name.lower()] = info
            self._countries_cache[name_en.lower()] = info
            self._countries_by_id[cid] = info
        
        self._countries_loaded = True
        logger.info(f"🌍 [MOCK] Загружено {len(self._countries_by_id)} стран")
    
    async def load_departures(self) -> bool:
        """
        Загрузка справочника городов вылета.
        
        Метод: list.php?type=departure
        """
        if self._departures_loaded:
            return True
        
        logger.info("✈️ Загрузка городов вылета...")
        
        if self.mock_enabled:
            self._departures_cache = self._get_default_departures()
            self._departures_loaded = True
            return True
        
        try:
            response = await self._request("list.php", {"type": "departure"})
            
            departures_data = (
                response.get("lists", {}).get("departures", {}).get("departure", []) or
                response.get("data", {}).get("departure", []) or
                []
            )
            
            if isinstance(departures_data, dict):
                departures_data = [departures_data]
            
            for d in departures_data:
                did = int(d.get("id", 0))
                name = d.get("name", "")
                
                if did and name:
                    self._departures_cache[name.lower()] = did
            
            # Дополняем известными городами
            defaults = self._get_default_departures()
            for name, did in defaults.items():
                if name not in self._departures_cache:
                    self._departures_cache[name] = did
            
            self._departures_loaded = True
            logger.info(f"✈️ Загружено {len(self._departures_cache)} городов вылета")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки городов: {e}")
            self._departures_cache = self._get_default_departures()
            self._departures_loaded = True
            return False
    
    def _get_default_departures(self) -> dict[str, int]:
        """Дефолтные города вылета."""
        return {
            "москва": 1, "moscow": 1,
            "санкт-петербург": 2, "спб": 2, "питер": 2,
            "казань": 10,
            "екатеринбург": 5,
            "новосибирск": 8,
            "краснодар": 12,
            "ростов-на-дону": 14, "ростов": 14,
            "уфа": 16,
            "самара": 7,
            "нижний новгород": 6,
        }
    
    async def load_hotels_for_country(self, country_id: int) -> list[HotelInfo]:
        """
        Загрузка списка отелей для страны.
        
        Метод: list.php?type=hotel&hotcountry=ID
        Документация: 2. Справочники.docx
        
        ВАЖНО: Используем параметр hotcountry (не countryid)!
        """
        if country_id in self._hotels_cache:
            return self._hotels_cache[country_id]
        
        logger.info(f"🏨 Загрузка отелей для страны ID={country_id}...")
        
        if self.mock_enabled:
            return []
        
        try:
            response = await self._request("list.php", {
                "type": "hotel",
                "hotcountry": country_id  # Правильный параметр согласно документации
            })
            
            hotels_data = (
                response.get("lists", {}).get("hotels", {}).get("hotel", []) or
                response.get("data", {}).get("hotel", []) or
                []
            )
            
            if isinstance(hotels_data, dict):
                hotels_data = [hotels_data]
            
            hotels = []
            for h in hotels_data:
                hotel = HotelInfo(
                    hotel_id=int(h.get("id", 0)),
                    name=h.get("name", ""),
                    stars=int(h.get("stars", 0)),
                    country_id=country_id,
                    region_id=int(h.get("regionid", 0)),
                    region_name=h.get("regionname", ""),
                    resort_id=int(h.get("subregionid", 0)),
                    resort_name=h.get("subregionname", ""),
                )
                if hotel.hotel_id and hotel.name:
                    hotels.append(hotel)
            
            self._hotels_cache[country_id] = hotels
            logger.info(f"🏨 Загружено {len(hotels)} отелей")
            return hotels
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки отелей: {e}")
            return []
    
    # ==================== LOOKUP METHODS ====================
    
    def get_country_id(self, name: str) -> Optional[int]:
        """Получение ID страны по названию."""
        if not name:
            return None
        
        name_lower = name.lower().strip()
        
        if name_lower in self._countries_cache:
            return self._countries_cache[name_lower].country_id
        
        # Типичные вариации
        variations = {
            "тайланд": "таиланд",
            "турции": "турция", "турцию": "турция",
            "египта": "египет",
            "эмираты": "оаэ", "дубай": "оаэ",
            "мальдив": "мальдивы",
            "бали": "индонезия",
        }
        
        if name_lower in variations:
            fixed = variations[name_lower]
            if fixed in self._countries_cache:
                return self._countries_cache[fixed].country_id
        
        # Нечеткий поиск
        for key, info in self._countries_cache.items():
            if name_lower in key or key in name_lower:
                return info.country_id
        
        return None
    
    def get_country_name(self, country_id: int) -> Optional[str]:
        """Получение названия страны по ID."""
        if country_id in self._countries_by_id:
            return self._countries_by_id[country_id].name
        return None
    
    def get_departure_id(self, name: str) -> Optional[int]:
        """Получение ID города вылета."""
        if not name:
            return None
        
        name_lower = name.lower().strip()
        
        if name_lower in self._departures_cache:
            return self._departures_cache[name_lower]
        
        for key, did in self._departures_cache.items():
            if name_lower in key or key in name_lower:
                return did
        
        return None
    
    # ==================== 2. ПОИСК ОТЕЛЕЙ ====================
    
    async def find_hotel_by_name(
        self,
        query: str,
        country: Optional[str] = None,
        country_id: Optional[int] = None
    ) -> list[HotelInfo]:
        """
        Поиск отелей по названию.
        
        Согласно документации: сначала определяем страну,
        затем загружаем справочник отелей и фильтруем.
        """
        logger.info(f"\n🔍 Поиск отеля: '{query}'")
        
        if self.mock_enabled:
            return []
        
        await self.load_countries()
        
        # Определяем страну
        if country_id:
            search_country_ids = [country_id]
        elif country:
            cid = self.get_country_id(country)
            search_country_ids = [cid] if cid else []
        else:
            # Популярные направления для поиска
            search_country_ids = [4, 5, 95, 2, 8]  # Турция, Египет, ОАЭ, Таиланд, Мальдивы
        
        if not search_country_ids:
            logger.warning("   ⚠️ Страна не определена")
            return []
        
        query_lower = query.lower()
        results = []
        
        for cid in search_country_ids:
            hotels = await self.load_hotels_for_country(cid)
            
            for hotel in hotels:
                if query_lower in hotel.name.lower():
                    results.append(hotel)
                    logger.info(f"   ✅ Найден: {hotel.name} ({hotel.stars}*)")
        
        if results:
            logger.info(f"   📊 Всего найдено: {len(results)} отелей")
        else:
            logger.warning(f"   ⚠️ Отели не найдены")
        
        return results
    
    # ==================== 3. АСИНХРОННЫЙ ПОИСК ТУРОВ (search.php) ====================
    
    async def search_tours(
        self,
        params: SearchRequest,
        filters: Optional[TourFilters] = None,
        is_strict_hotel_search: bool = False,
        hotel_ids: Optional[list[int]] = None
    ) -> SearchResponse:
        """
        Асинхронный поиск туров через search.php.
        
        Протокол (согласно документации):
        1. GET search.php с параметрами → получаем requestid
        2. Цикл опроса result.php?type=status каждые 2-3 сек
        3. Когда progress > 0, запрашиваем result.php?type=result
        
        Args:
            params: Параметры поиска
            filters: Дополнительные фильтры
            is_strict_hotel_search: Строгий поиск по конкретным отелям
            hotel_ids: Список ID отелей (если известны)
        """
        logger.info("\n" + "=" * 60)
        logger.info("🔍 ПОИСК ТУРОВ (Async Protocol)")
        logger.info("=" * 60)
        
        if self.mock_enabled:
            logger.info("   🔧 MOCK режим")
            return await self._mock_search_tours(params)
        
        # Загружаем справочники
        await self.load_countries()
        await self.load_departures()
        
        # Получаем ID страны
        country_id = self.get_country_id(params.destination.country)
        if not country_id:
            logger.error(f"❌ Страна не найдена: {params.destination.country}")
            return SearchResponse(
                offers=[], total_found=0, found=False,
                reason="unknown_country",
                suggestion="check_country_name"
            )
        
        # Получаем ID города вылета
        departure_id = self.get_departure_id(params.departure_city) or 1
        
        # Если указан отель — ищем его ID
        if params.hotel_name and not hotel_ids:
            logger.info(f"   🏨 Поиск отеля: {params.hotel_name}")
            hotels = await self.find_hotel_by_name(params.hotel_name, country_id=country_id)
            if hotels:
                hotel_ids = [h.hotel_id for h in hotels[:5]]
                logger.info(f"   ✅ ID отелей: {hotel_ids}")
            elif is_strict_hotel_search:
                return SearchResponse(
                    offers=[], total_found=0, found=False,
                    reason="hotel_not_found",
                    suggestion="check_hotel_name"
                )
        
        # === STEP 1: Инициируем поиск ===
        api_params = self._build_search_params(
            params, country_id, departure_id, hotel_ids
        )
        
        logger.info(f"   📡 Инициация поиска...")
        logger.info(f"      Страна: {country_id}")
        logger.info(f"      Вылет: {departure_id}")
        logger.info(f"      Даты: {api_params.get('datefrom')} - {api_params.get('dateto')}")
        
        try:
            search_response = await self._request("search.php", api_params)
            request_id = self._extract_request_id(search_response)
            
            if not request_id:
                logger.error("❌ Не получен requestid")
                return SearchResponse(
                    offers=[], total_found=0, found=False,
                    reason="api_error"
                )
            
            logger.info(f"   ✅ Request ID: {request_id}")
            
            # === STEP 2: Цикл опроса статуса ===
            offers = await self._poll_and_fetch_results(
                request_id, country_id, is_strict_hotel_search, hotel_ids
            )
            
            # Применяем фильтры
            if filters:
                offers = self._apply_filters(offers, filters)
            
            if params.stars:
                offers = [o for o in offers if o.hotel_stars == params.stars]
            
            if params.food_type:
                offers = [o for o in offers if o.food_type == params.food_type]
            
            # Сортируем и лимитируем
            offers = sorted(offers, key=lambda x: x.price)[:5]
            
            if offers:
                logger.info(f"   ✅ Найдено туров: {len(offers)}")
                return SearchResponse(
                    offers=offers,
                    total_found=len(offers),
                    search_id=request_id,
                    found=True
                )
            else:
                logger.warning("   ⚠️ Туры не найдены")
                return SearchResponse(
                    offers=[], total_found=0, search_id=request_id,
                    found=False, reason="no_tours_found",
                    suggestion="try_changing_dates"
                )
                
        except SearchTimeoutError:
            return SearchResponse(
                offers=[], total_found=0, found=False,
                reason="search_timeout",
                suggestion="try_later"
            )
        except TourvisorAPIError as e:
            logger.error(f"❌ API Error: {e.message}")
            return SearchResponse(
                offers=[], total_found=0, found=False,
                reason="api_error"
            )
    
    def _build_search_params(
        self,
        params: SearchRequest,
        country_id: int,
        departure_id: int,
        hotel_ids: Optional[list[int]]
    ) -> dict:
        """
        Формирование параметров для search.php.
        
        Согласно документации 1. Поиск туров.docx:
        - datefrom, dateto: в формате dd.mm.yyyy
        - child: количество детей
        - childage1, childage2...: возрасты детей (НЕ массив!)
        - hotels: список ID через запятую
        """
        nights_from = params.nights or 7
        nights_to = (params.nights + 3) if params.nights else 14
        
        api_params = {
            "departure": departure_id,
            "country": country_id,
            "datefrom": params.date_from.strftime("%d.%m.%Y"),
            "dateto": (params.date_to or params.date_from + timedelta(days=14)).strftime("%d.%m.%Y"),
            "nightsfrom": nights_from,
            "nightsto": nights_to,
            "adults": params.adults,
            # По умолчанию ищем ВСЕ туры (не только горящие)
            # hideregular=0 означает показывать регулярные рейсы
        }
        
        # === ДЕТИ: передаём как childage1, childage2... ===
        if params.children:
            api_params["child"] = len(params.children)
            for i, age in enumerate(params.children, 1):
                api_params[f"childage{i}"] = age
        
        # Регион/курорт
        if params.destination.region:
            api_params["region"] = params.destination.region
        
        # === Конкретные отели (список через запятую) ===
        if hotel_ids:
            api_params["hotels"] = ",".join(map(str, hotel_ids))
        elif params.hotel_name:
            api_params["hotel"] = params.hotel_name
        
        # Звёздность
        if params.stars:
            api_params["starsfrom"] = params.stars
            api_params["starsto"] = params.stars
        
        # Питание
        if params.food_type and params.food_type.value in MEAL_TYPE_MAP:
            api_params["meal"] = MEAL_TYPE_MAP[params.food_type.value]
        
        return api_params
    
    async def _poll_and_fetch_results(
        self,
        request_id: str,
        country_id: int,
        is_strict_hotel_search: bool,
        hotel_ids: Optional[list[int]]
    ) -> list[TourOffer]:
        """
        Цикл опроса статуса и получения результатов.
        
        Протокол:
        1. result.php?type=status — проверяем progress
        2. Когда progress > min_progress_to_fetch — забираем результаты
        3. result.php?type=result — получаем данные
        """
        all_offers = []
        fetched = False
        
        for attempt in range(1, self.max_poll_attempts + 1):
            await asyncio.sleep(self.poll_interval)
            
            # === Проверяем статус ===
            status = await self._get_search_status(request_id)
            
            logger.info(f"   ⏳ [{attempt}/{self.max_poll_attempts}] "
                       f"Progress: {status.progress}% | State: {status.state}")
            
            # Если достаточный прогресс — забираем результаты
            if status.progress >= self.min_progress_to_fetch or status.state == "finished":
                if not fetched or status.progress > 50:  # Перезабираем при 50%+
                    offers = await self._fetch_results(
                        request_id, country_id, is_strict_hotel_search, hotel_ids
                    )
                    if offers:
                        all_offers = offers
                        fetched = True
            
            # Если завершено — выходим
            if status.state == "finished":
                break
        
        if not fetched:
            raise SearchTimeoutError("Search timeout")
        
        return all_offers
    
    async def _get_search_status(self, request_id: str) -> SearchStatus:
        """
        Получение статуса поиска.
        
        Метод: result.php?type=status&requestid=XXX
        """
        try:
            response = await self._request("result.php", {
                "type": "status",
                "requestid": request_id
            })
            
            data = response.get("data", {}).get("status", {})
            
            return SearchStatus(
                request_id=request_id,
                state=data.get("state", "unknown"),
                progress=int(data.get("progress", 0)),
                operators_done=int(data.get("done", 0)),
                operators_total=int(data.get("total", 0)),
            )
        except Exception:
            return SearchStatus(
                request_id=request_id,
                state="error",
                progress=0
            )
    
    async def _fetch_results(
        self,
        request_id: str,
        country_id: int,
        is_strict_hotel_search: bool,
        hotel_ids: Optional[list[int]]
    ) -> list[TourOffer]:
        """
        Получение результатов поиска.
        
        Метод: result.php?type=result&requestid=XXX
        """
        try:
            response = await self._request("result.php", {
                "type": "result",
                "requestid": request_id
            })
            
            return self._parse_tour_results(
                response, country_id, is_strict_hotel_search, hotel_ids
            )
        except Exception as e:
            logger.error(f"❌ Ошибка получения результатов: {e}")
            return []
    
    def _extract_request_id(self, response: dict) -> Optional[str]:
        """Извлечение requestid из ответа search.php."""
        return (
            response.get("result", {}).get("requestid") or
            response.get("requestid") or
            response.get("data", {}).get("requestid")
        )
    
    def _parse_tour_results(
        self,
        response: dict,
        country_id: int,
        is_strict_hotel_search: bool,
        hotel_ids: Optional[list[int]]
    ) -> list[TourOffer]:
        """Парсинг результатов поиска."""
        
        hotels_data = response.get("data", {}).get("result", {}).get("hotel", [])
        
        if isinstance(hotels_data, dict):
            hotels_data = [hotels_data]
        
        if not hotels_data:
            return []
        
        offers = []
        expected_country = self.get_country_name(country_id)
        
        for hotel in hotels_data:
            # Фильтрация по стране
            hotel_country_id = hotel.get("countryid")
            if hotel_country_id and int(hotel_country_id) != country_id:
                continue
            
            # Строгий поиск по отелю
            if is_strict_hotel_search and hotel_ids:
                hotel_code = hotel.get("hotelcode")
                if hotel_code and int(hotel_code) not in hotel_ids:
                    continue
            
            try:
                offer = self._parse_single_offer(hotel, expected_country)
                if offer:
                    offers.append(offer)
            except Exception as e:
                logger.debug(f"Ошибка парсинга: {e}")
                continue
        
        return offers
    
    def _parse_single_offer(self, hotel: dict, country_name: Optional[str]) -> Optional[TourOffer]:
        """Парсинг одного предложения."""
        
        tours = hotel.get("tours", {}).get("tour", [])
        if isinstance(tours, dict):
            tours = [tours]
        
        tour = tours[0] if tours else {}
        
        price = hotel.get("price") or tour.get("price", 0)
        if not price:
            return None
        
        # Даты
        date_from = self._parse_date(tour.get("flydate") or tour.get("checkin"))
        nights = int(tour.get("nights", 7))
        
        if not date_from:
            date_from = date.today() + timedelta(days=14)
        
        date_to = date_from + timedelta(days=nights)
        
        # Питание
        meal_code = tour.get("meal", "AI")
        if meal_code in MEAL_TYPE_REVERSE:
            meal_code = MEAL_TYPE_REVERSE[meal_code]
        
        try:
            food_type = FoodType(meal_code.upper())
        except ValueError:
            food_type = FoodType.AI
        
        return TourOffer(
            id=str(tour.get("tourid", uuid.uuid4())),
            hotel_name=hotel.get("hotelname", "Unknown"),
            hotel_stars=int(hotel.get("hotelstars", 0)),
            hotel_rating=float(hotel.get("hotelrating")) if hotel.get("hotelrating") else None,
            country=hotel.get("countryname") or country_name or "",
            region=hotel.get("regionname"),
            resort=hotel.get("subregionname") or hotel.get("resortname"),
            room_type=tour.get("room", "Standard"),
            food_type=food_type,
            price=int(price),
            currency="RUB",
            date_from=date_from,
            date_to=date_to,
            nights=nights,
            adults=int(tour.get("adults", 2)),
            children=int(tour.get("child", 0)),
            departure_city=tour.get("departurename", "Москва"),
            operator=tour.get("operatorname", ""),
            hotel_link=hotel.get("fulldesclink", ""),
            hotel_photo=hotel.get("picturelink", ""),
        )
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Парсинг даты (формат dd.mm.yyyy)."""
        if not date_str:
            return None
        
        try:
            parts = date_str.split(".")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except:
            pass
        
        return None
    
    def _apply_filters(self, offers: list[TourOffer], filters: TourFilters) -> list[TourOffer]:
        """Применение фильтров."""
        result = offers
        
        if filters.food_types:
            result = [o for o in result if o.food_type in filters.food_types]
        
        if filters.min_stars:
            result = [o for o in result if o.hotel_stars >= filters.min_stars]
        
        if filters.max_stars:
            result = [o for o in result if o.hotel_stars <= filters.max_stars]
        
        if filters.min_price:
            result = [o for o in result if o.price >= filters.min_price]
        
        if filters.max_price:
            result = [o for o in result if o.price <= filters.max_price]
        
        return result
    
    # ==================== 4. ГОРЯЩИЕ ТУРЫ (hottours.php) ====================
    
    async def get_hot_tours(
        self,
        departure_id: int = 1,
        country_id: Optional[int] = None,
        limit: int = 10
    ) -> list[TourOffer]:
        """
        Получение горящих туров.
        
        Метод: hottours.php (синхронный, быстрый)
        Документация: 1. Горящие туры.docx
        
        Параметры:
        - city: ID города вылета
        - country: ID страны (опционально)
        - items: количество результатов
        """
        logger.info("🔥 Получение горящих туров...")
        
        if self.mock_enabled:
            return await self._mock_hot_tours()
        
        try:
            params = {
                "city": departure_id,
                "items": limit,
            }
            
            if country_id:
                params["country"] = country_id
            
            response = await self._request("hottours.php", params)
            
            tours_data = response.get("data", {}).get("tour", [])
            
            if isinstance(tours_data, dict):
                tours_data = [tours_data]
            
            offers = []
            for t in tours_data:
                try:
                    offer = self._parse_hot_tour(t)
                    if offer:
                        offers.append(offer)
                except Exception:
                    continue
            
            logger.info(f"🔥 Найдено {len(offers)} горящих туров")
            return offers
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения горящих туров: {e}")
            return []
    
    def _parse_hot_tour(self, tour: dict) -> Optional[TourOffer]:
        """Парсинг горящего тура."""
        
        price = tour.get("price", 0)
        if not price:
            return None
        
        date_from = self._parse_date(tour.get("flydate"))
        nights = int(tour.get("nights", 7))
        
        if not date_from:
            date_from = date.today() + timedelta(days=3)
        
        return TourOffer(
            id=str(tour.get("tourid", uuid.uuid4())),
            hotel_name=tour.get("hotelname", "Unknown"),
            hotel_stars=int(tour.get("hotelstars", 0)),
            country=tour.get("countryname", ""),
            region=tour.get("regionname"),
            resort=tour.get("subregionname"),
            room_type=tour.get("room", "Standard"),
            food_type=FoodType.AI,
            price=int(price),
            currency="RUB",
            date_from=date_from,
            date_to=date_from + timedelta(days=nights),
            nights=nights,
            adults=2,
            children=0,
            departure_city=tour.get("departurename", "Москва"),
            operator=tour.get("operatorname", ""),
            hotel_link=tour.get("fulldesclink", ""),
            hotel_photo=tour.get("picturelink", ""),
        )
    
    # ==================== 5. АКТУАЛИЗАЦИЯ (actualize.php, actdetail.php) ====================
    
    async def actualize_tour(self, tour_id: str) -> Optional[ActualizeResult]:
        """
        Актуализация цены тура.
        
        Метод: actualize.php?tourid=XXX
        Документация: 3. Актуализация.docx
        
        Вызывается когда пользователь выбрал конкретный тур.
        """
        logger.info(f"💰 Актуализация тура: {tour_id}")
        
        if self.mock_enabled:
            return ActualizeResult(
                tour_id=tour_id,
                price=100000,
                available=True,
                price_changed=False
            )
        
        try:
            response = await self._request("actualize.php", {"tourid": tour_id})
            
            data = response.get("data", {}).get("tour", {})
            
            if not data:
                return None
            
            current_price = int(data.get("price", 0))
            original_price = int(data.get("originalprice", current_price))
            
            return ActualizeResult(
                tour_id=tour_id,
                price=current_price,
                available=data.get("available", "1") == "1",
                price_changed=current_price != original_price,
                original_price=original_price,
                currency=data.get("currency", "RUB")
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка актуализации: {e}")
            return None
    
    async def get_flight_details(self, tour_id: str) -> Optional[FlightInfo]:
        """
        Получение детальной информации о рейсе.
        
        Метод: actdetail.php?tourid=XXX
        Документация: 4. Актуализация детальная.docx
        
        ВАЖНО: Это новый метод, старый (flights=1) не работает!
        """
        logger.info(f"✈️ Получение данных о рейсе: {tour_id}")
        
        if self.mock_enabled:
            return FlightInfo(
                airline="Aeroflot",
                flight_number="SU123",
                departure_time="10:00",
                arrival_time="14:00",
            )
        
        try:
            response = await self._request("actdetail.php", {"tourid": tour_id})
            
            flight_data = response.get("data", {}).get("flight", {})
            
            if not flight_data:
                return None
            
            return FlightInfo(
                airline=flight_data.get("airline", ""),
                flight_number=flight_data.get("flightnumber", ""),
                departure_time=flight_data.get("departuretime", ""),
                arrival_time=flight_data.get("arrivaltime", ""),
                departure_airport=flight_data.get("departureairport", ""),
                arrival_airport=flight_data.get("arrivalairport", ""),
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных о рейсе: {e}")
            return None
    
    # ==================== 6. КОНТЕНТ ОТЕЛЯ (hotel.php) ====================
    
    async def get_hotel_details(self, hotel_code: int) -> Optional[HotelDetails]:
        """
        Получение детальной информации об отеле.
        
        Метод: hotel.php?hotelcode=XXX
        Документация: 1. Описания отелей.docx
        
        Возвращает фото и описание.
        """
        logger.info(f"🏨 Получение информации об отеле: {hotel_code}")
        
        if self.mock_enabled:
            return None
        
        try:
            response = await self._request("hotel.php", {"hotelcode": hotel_code})
            
            data = response.get("data", {}).get("hotel", {})
            
            if not data:
                return None
            
            # Получаем фото (массив images -> image)
            photos = []
            images_data = data.get("images", {}).get("image", [])
            if isinstance(images_data, dict):
                images_data = [images_data]
            
            for img in images_data:
                if isinstance(img, str):
                    photos.append(img)
                elif isinstance(img, dict):
                    # Берём ссылку на 800px версию
                    url = img.get("800") or img.get("url") or img.get("src")
                    if url:
                        photos.append(url)
            
            return HotelDetails(
                id=hotel_code,
                name=data.get("name", ""),
                stars=int(data.get("stars", 0)),
                rating=float(data.get("rating")) if data.get("rating") else None,
                country=data.get("countryname", ""),
                region=data.get("regionname"),
                resort=data.get("subregionname"),
                address=data.get("address"),
                description=data.get("description"),
                photos=photos[:10],  # Лимит 10 фото
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об отеле: {e}")
            return None
    
    # ==================== MOCK DATA ====================
    
    async def _mock_search_tours(self, params: SearchRequest) -> SearchResponse:
        """Mock данные для тестирования."""
        
        base_date = params.date_from or date.today() + timedelta(days=14)
        nights = params.nights or 7
        country = params.destination.country
        
        offers = []
        mock_hotels = [
            ("Beach Resort", 4, 65000),
            ("Grand Hotel", 5, 95000),
            ("Family Inn", 3, 45000),
        ]
        
        for name, stars, price in mock_hotels:
            total_price = price * params.adults
            for age in (params.children or []):
                if age < 2:
                    total_price += price * 0.1
                elif age < 12:
                    total_price += price * 0.5
                else:
                    total_price += price * 0.8
            
            offer = TourOffer(
                id=str(uuid.uuid4()),
                hotel_name=f"{name} {country}",
                hotel_stars=stars,
                country=country,
                region="Mock Region",
                resort="Mock Resort",
                room_type="Standard",
                food_type=params.food_type or FoodType.AI,
                price=int(total_price),
                currency="RUB",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                adults=params.adults,
                children=len(params.children or []),
                departure_city=params.departure_city,
                operator="Mock Operator",
            )
            offers.append(offer)
        
        return SearchResponse(
            offers=offers,
            total_found=len(offers),
            found=True
        )
    
    async def _mock_hot_tours(self) -> list[TourOffer]:
        """Mock горящие туры."""
        return [
            TourOffer(
                id=str(uuid.uuid4()),
                hotel_name="Hot Deal Resort",
                hotel_stars=4,
                country="Египет",
                region="Хургада",
                resort="Макади Бей",
                room_type="Standard",
                food_type=FoodType.AI,
                price=45000,
                currency="RUB",
                date_from=date.today() + timedelta(days=3),
                date_to=date.today() + timedelta(days=10),
                nights=7,
                adults=2,
                children=0,
                departure_city="Москва",
                operator="Anex Tour",
            )
        ]
    
    # ==================== CLEANUP ====================
    
    async def close(self):
        """Закрытие HTTP клиента."""
        if self.client:
            await self.client.aclose()
            self.client = None


# ==================== SERVICE SINGLETON ====================

tourvisor_service = TourvisorService()

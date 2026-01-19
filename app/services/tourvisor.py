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

# Fuzzy Matching для городов вылета
try:
    from thefuzz import fuzz, process
    FUZZY_ENABLED = True
except ImportError:
    FUZZY_ENABLED = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ thefuzz не установлен. Fuzzy matching отключен.")

# Импорт авто-сгенерированных констант (синхронизируются из Tourvisor API)
try:
    from app.core.tourvisor_constants import COUNTRIES, DEPARTURES
    CONSTANTS_LOADED = True
except ImportError:
    # Fallback если файл констант ещё не создан
    COUNTRIES = {}
    DEPARTURES = {}
    CONSTANTS_LOADED = False

# Настройка логгера
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Debug Logger для трассировки API вызовов
from app.core.debug_logger import debug_logger
import time
import contextvars

# Контекстные переменные для передачи conversation_id и turn_id
_conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('conversation_id', default='')
_turn_id_var: contextvars.ContextVar[int] = contextvars.ContextVar('turn_id', default=0)


def set_trace_context(conversation_id: str, turn_id: int) -> None:
    """Установка контекста для трассировки API вызовов."""
    _conversation_id_var.set(conversation_id)
    _turn_id_var.set(turn_id)


def get_trace_context() -> tuple[str, int]:
    """Получение контекста трассировки."""
    return _conversation_id_var.get(), _turn_id_var.get()


# ==================== ENUMS & CONSTANTS ====================

class SearchType(Enum):
    """Тип поиска туров."""
    REGULAR = "regular"      # Обычный поиск через search.php
    HOT_TOURS = "hot"        # Горящие туры через hottours.php


class ResultType(Enum):
    """Тип запроса результатов."""
    STATUS = "status"
    RESULT = "result"


# Маппинг типов питания для API (ID из справочника Tourvisor)
# КРИТИЧНО: API требует числовые ID, не строки!
# Источник: list.php?type=meal
MEAL_TYPE_MAP = {
    "RO": 2,   # Room Only - Без питания
    "BB": 3,   # Bed&Breakfast - Только завтрак
    "HB": 4,   # Half Board - Завтрак + Ужин
    "FB": 5,   # Full Board - Полный Пансион
    "AI": 7,   # All Inclusive - Всё включено
    "UAI": 9,  # Ultra All Inclusive - Ультра всё включено
}

# Обратный маппинг (ID -> код)
MEAL_TYPE_REVERSE = {v: k for k, v in MEAL_TYPE_MAP.items()}

# ==================== КЕШИ РЕГИОНОВ (динамически загружаются) ====================
# Загружаются через API list.php, НЕ хардкод!
# Согласно "2. Справочники.docx"
_REGIONS_CACHE: dict[int, list[dict]] = {}      # country_id -> list of regions
_SUBREGIONS_CACHE: dict[int, list[dict]] = {}   # country_id -> list of subregions (курорты)


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
        # КРИТИЧНО: GDS/регулярные рейсы грузятся ДОЛГО!
        # Если обрываем рано — теряем большинство туров
        self.poll_interval: float = 2.0  # секунды между запросами статуса
        self.max_poll_attempts: int = 60  # ~120 секунд максимум
        self.min_progress_to_fetch: int = 70  # Начинаем забирать при 70%+
        self.min_wait_seconds: float = 25.0  # Минимум 25 секунд ожидания (GDS грузится долго!)
    
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
        Логирует вызов в debug_bundle/LOGS/app.jsonl если DEBUG_LOGS=1.
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
        
        # Замеряем время выполнения
        start_time = time.time()
        status_code = None
        error_msg = None
        response_summary = None
        result_count = None
        
        try:
            response = await client.get(url, params=params)
            status_code = response.status_code
            
            if response.status_code == 401:
                error_msg = "Unauthorized"
                raise TourvisorAPIError("Unauthorized", "Ошибка авторизации в API туров.")
            
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                raise TourvisorAPIError(f"HTTP {response.status_code}")
            
            # Очистка BOM и парсинг JSON
            text = response.text.strip()
            if text.startswith('\ufeff'):
                text = text[1:]
            
            if not text or text == "{}":
                response_summary = "Empty response"
                return {}
            
            result = response.json()
            
            # Формируем summary для логирования
            response_summary = self._create_response_summary(endpoint, result)
            result_count = self._extract_result_count(endpoint, result)
            
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP Error: {e}")
            error_msg = str(e)
            raise TourvisorAPIError(str(e))
        except TourvisorAPIError:
            raise
        except Exception as e:
            logger.error(f"❌ Request Error: {e}")
            error_msg = str(e)
            raise TourvisorAPIError(str(e))
        finally:
            # Логируем API trace если включено
            elapsed_ms = (time.time() - start_time) * 1000
            self._log_api_trace(
                endpoint=endpoint,
                params=params,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                result_count=result_count,
                error=error_msg,
                response_summary=response_summary
            )
    
    def _create_response_summary(self, endpoint: str, result: dict) -> str:
        """Создание краткого summary ответа API (без полного raw)."""
        if not result:
            return "Empty"
        
        if endpoint == "search.php":
            request_id = result.get("result", {}).get("requestid")
            return f"requestid={request_id}" if request_id else "No requestid"
        
        elif endpoint == "result.php":
            status = result.get("data", {}).get("status", {})
            progress = status.get("progress", 0) if isinstance(status, dict) else 0
            tours_data = result.get("data", {}).get("result", {}).get("hotel", [])
            count = len(tours_data) if isinstance(tours_data, list) else 0
            return f"progress={progress}%, hotels={count}"
        
        elif endpoint == "hottours.php":
            tours = result.get("hottours", {}).get("tour", [])
            count = len(tours) if isinstance(tours, list) else 0
            return f"hottours={count}"
        
        elif endpoint == "list.php":
            # Справочники
            keys = list(result.keys())[:3]
            return f"lists: {keys}"
        
        elif endpoint in ("actualize.php", "actdetail.php"):
            actualize = result.get("actualize", {})
            price = actualize.get("price")
            return f"price={price}" if price else "No price"
        
        elif endpoint == "hotel.php":
            hotel = result.get("hotel", {})
            name = hotel.get("name", "")[:30]
            return f"hotel={name}" if name else "No hotel data"
        
        else:
            # Общий случай
            keys = list(result.keys())[:5]
            return f"keys={keys}"
    
    def _extract_result_count(self, endpoint: str, result: dict) -> Optional[int]:
        """Извлечение количества результатов из ответа API."""
        if endpoint == "result.php":
            tours = result.get("data", {}).get("result", {}).get("hotel", [])
            return len(tours) if isinstance(tours, list) else None
        
        elif endpoint == "hottours.php":
            tours = result.get("hottours", {}).get("tour", [])
            return len(tours) if isinstance(tours, list) else None
        
        elif endpoint == "list.php":
            # Пробуем найти списки
            for key in ["countries", "departures", "hotels", "regions"]:
                data = result.get("lists", {}).get(key, {})
                if isinstance(data, dict):
                    items = data.get(key[:-1], [])  # countries -> country
                    if isinstance(items, list):
                        return len(items)
            return None
        
        return None
    
    def _log_api_trace(
        self,
        endpoint: str,
        params: dict,
        status_code: Optional[int],
        elapsed_ms: float,
        result_count: Optional[int],
        error: Optional[str],
        response_summary: Optional[str]
    ) -> None:
        """Логирование API trace в debug_bundle."""
        if not debug_logger.enabled:
            return
        
        try:
            conversation_id, turn_id = get_trace_context()
            
            debug_logger.log_api_trace(
                conversation_id=conversation_id or "unknown",
                turn_id=turn_id,
                endpoint=endpoint,
                request_params=params,  # Будет санитизирован внутри log_api_trace
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                result_count=result_count,
                error=error,
                response_summary=response_summary
            )
        except Exception as e:
            logger.warning(f"[DEBUG_LOGGER] Ошибка логирования API trace: {e}")
    
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
        """
        Fallback данные из авто-сгенерированного файла констант.
        
        Константы загружаются из app/core/tourvisor_constants.py,
        который создаётся скриптом scripts/sync_tourvisor_data.py
        """
        if CONSTANTS_LOADED and COUNTRIES:
            # Используем авто-сгенерированные константы
            seen_ids = set()
            for name, cid in COUNTRIES.items():
                # Добавляем в кэш
                if cid not in seen_ids:
                    # Определяем отображаемое имя (первое русское)
                    display_name = name.title()
                    info = CountryInfo(country_id=cid, name=display_name, name_en="")
                    self._countries_by_id[cid] = info
                    seen_ids.add(cid)
                
                # Добавляем маппинг имени
                if cid in self._countries_by_id:
                    self._countries_cache[name.lower()] = self._countries_by_id[cid]
            
            self._countries_loaded = True
            logger.info(f"🌍 [CONSTANTS] Загружено {len(self._countries_by_id)} стран из tourvisor_constants.py")
        else:
            # Минимальный fallback если константы не загружены
            logger.warning("⚠️ tourvisor_constants.py не найден! Запустите: python scripts/sync_tourvisor_data.py")
            
            minimal_countries = [
                (1, "Египет"), (2, "Таиланд"), (4, "Турция"), (8, "Мальдивы"), (9, "ОАЭ")
            ]
            for cid, name in minimal_countries:
                info = CountryInfo(country_id=cid, name=name, name_en="")
                self._countries_cache[name.lower()] = info
                self._countries_by_id[cid] = info
            
            self._countries_loaded = True
            logger.info(f"🌍 [FALLBACK] Загружено {len(self._countries_by_id)} стран (минимум)")
    
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
        """
        Города вылета из авто-сгенерированного файла констант.
        
        Константы загружаются из app/core/tourvisor_constants.py,
        который создаётся скриптом scripts/sync_tourvisor_data.py
        """
        if CONSTANTS_LOADED and DEPARTURES:
            logger.info(f"✈️ [CONSTANTS] Используем {len(DEPARTURES)} городов из tourvisor_constants.py")
            return DEPARTURES.copy()
        
        # Минимальный fallback если константы не загружены
        logger.warning("⚠️ tourvisor_constants.py не найден! Запустите: python scripts/sync_tourvisor_data.py")
        return {
            # Москва
            "москва": 1, "мск": 1, "москвы": 1,
            # Санкт-Петербург
            "санкт-петербург": 2, "спб": 2, "питер": 2, "петербург": 2,
            # Екатеринбург
            "екатеринбург": 3, "екб": 3,
            # Новосибирск
            "новосибирск": 8, "новосиб": 8,
            # Казань
            "казань": 10, "казани": 10,
            # Сочи
            "сочи": 62, "сочи (адлер)": 62, "адлер": 62,
            # Краснодар
            "краснодар": 11,
        }
    
    async def load_dictionaries(self) -> bool:
        """
        System Startup Sync — загрузка всех критических справочников.
        
        Согласно "2. Справочники.docx":
        - Страны: list.php?type=country
        - Города вылета: list.php?type=departure
        
        Вызывать при инициализации сервиса или старте приложения.
        
        Returns:
            True если загрузка успешна
        """
        logger.info("📚 System Startup Sync: загрузка справочников...")
        
        countries_ok = await self.load_countries()
        departures_ok = await self.load_departures()
        
        if countries_ok and departures_ok:
            logger.info(f"✅ Справочники загружены: {len(self._countries_cache)} стран, {len(self._departures_cache)} городов")
            return True
        else:
            logger.error("❌ Ошибка загрузки справочников!")
            return False
    
    async def load_regions_for_country(self, country_id: int) -> list[dict]:
        """
        Загрузка справочника регионов для страны.
        
        Метод: list.php?type=region&regcountry=ID
        
        Returns:
            Список словарей с id и name регионов
        """
        global _REGIONS_CACHE
        
        if country_id in _REGIONS_CACHE:
            return _REGIONS_CACHE[country_id]
        
        logger.info(f"🗺️ Загрузка регионов для страны {country_id}...")
        
        try:
            response = await self._request("list.php", {
                "type": "region",
                "regcountry": country_id
            })
            
            regions_data = (
                response.get("lists", {}).get("regions", {}).get("region", []) or
                response.get("data", {}).get("region", []) or
                []
            )
            
            if isinstance(regions_data, dict):
                regions_data = [regions_data]
            
            regions = []
            for r in regions_data:
                rid = int(r.get("id", 0))
                name = r.get("name", "")
                if rid and name:
                    regions.append({"id": rid, "name": name.lower()})
            
            _REGIONS_CACHE[country_id] = regions
            logger.info(f"🗺️ Загружено {len(regions)} регионов для страны {country_id}")
            return regions
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки регионов: {e}")
            return []
    
    async def get_region_id_by_name(self, region_name: str, country_id: int) -> Optional[int]:
        """
        Динамический поиск ID региона по названию через API.
        
        Согласно "2. Справочники.docx":
        1. Сначала ищем в regions (list.php?type=region)
        2. Если не найден — ищем в subregions (list.php?type=subregion)
        
        Args:
            region_name: Название региона (напр. "Сочи")
            country_id: ID страны
            
        Returns:
            ID региона или None если не найден
        """
        if not region_name or not country_id:
            return None
        
        region_name_lower = region_name.lower().strip()
        
        # ШАГ 1: Ищем в основных регионах (type=region)
        regions = await self.load_regions_for_country(country_id)
        
        # Точное совпадение в regions
        for r in regions:
            if r["name"] == region_name_lower:
                logger.info(f"🗺️ Регион '{region_name}' → ID={r['id']} (region, точное)")
                return r["id"]
        
        # Частичное совпадение в regions
        for r in regions:
            if region_name_lower in r["name"] or r["name"] in region_name_lower:
                logger.info(f"🗺️ Регион '{region_name}' → ID={r['id']} (region, fuzzy: {r['name']})")
                return r["id"]
        
        # ШАГ 2: Ищем в субрегионах/курортах (type=subregion)
        subregions = await self.load_subregions_for_country(country_id)
        
        # Точное совпадение в subregions
        for r in subregions:
            if r["name"] == region_name_lower:
                logger.info(f"🗺️ Субрегион '{region_name}' → ID={r['id']} (subregion, точное)")
                return r["id"]
        
        # Частичное совпадение в subregions
        for r in subregions:
            if region_name_lower in r["name"] or r["name"] in region_name_lower:
                logger.info(f"🗺️ Субрегион '{region_name}' → ID={r['id']} (subregion, fuzzy: {r['name']})")
                return r["id"]
        
        logger.warning(f"⚠️ Регион/субрегион '{region_name}' не найден в стране {country_id}")
        return None
    
    async def load_subregions_for_country(self, country_id: int) -> list[dict]:
        """
        Загрузка справочника субрегионов (курортов) для страны.
        
        Метод: list.php?type=subregion&regcountry=ID
        Согласно "2. Справочники.docx", Source 44
        
        Returns:
            Список словарей с id и name субрегионов
        """
        global _SUBREGIONS_CACHE
        
        if country_id in _SUBREGIONS_CACHE:
            return _SUBREGIONS_CACHE[country_id]
        
        logger.info(f"🏖️ Загрузка субрегионов (курортов) для страны {country_id}...")
        
        try:
            response = await self._request("list.php", {
                "type": "subregion",
                "regcountry": country_id
            })
            
            subregions_data = (
                response.get("lists", {}).get("subregions", {}).get("subregion", []) or
                response.get("data", {}).get("subregion", []) or
                []
            )
            
            if isinstance(subregions_data, dict):
                subregions_data = [subregions_data]
            
            subregions = []
            for r in subregions_data:
                rid = int(r.get("id", 0))
                name = r.get("name", "")
                if rid and name:
                    subregions.append({"id": rid, "name": name.lower()})
            
            _SUBREGIONS_CACHE[country_id] = subregions
            logger.info(f"🏖️ Загружено {len(subregions)} субрегионов для страны {country_id}")
            return subregions
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки субрегионов: {e}")
            return []
    
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
        """
        Получение ID города вылета с Fuzzy Matching.
        
        Поддерживает:
        - Точное совпадение: "москва" → 1
        - Частичное: "сочи" → "сочи (адлер)" → ID
        - Fuzzy (>80%): "Питер" → "Санкт-Петербург", "Екб" → "Екатеринбург"
        """
        if not name:
            return None
        
        name_lower = name.lower().strip()
        
        # 1. Точное совпадение
        if name_lower in self._departures_cache:
            logger.info(f"   ✈️ Город '{name}' → точное совпадение")
            return self._departures_cache[name_lower]
        
        # 2. Частичное совпадение (substring)
        for key, did in self._departures_cache.items():
            if name_lower in key or key in name_lower:
                logger.info(f"   ✈️ Город '{name}' → частичное: '{key}'")
                return did
        
        # 3. Fuzzy Matching (если thefuzz установлен)
        if FUZZY_ENABLED and self._departures_cache:
            result = self._fuzzy_find_city(name_lower, self._departures_cache)
            if result:
                found_name, found_id, score = result
                logger.info(f"   ✈️ Город '{name}' → fuzzy ({score}%): '{found_name}'")
                return found_id
        
        logger.warning(f"   ⚠️ Город '{name}' не найден в справочнике")
        return None
    
    def _fuzzy_find_city(
        self, 
        user_input: str, 
        city_dict: dict[str, int],
        threshold: int = 80
    ) -> Optional[tuple[str, int, int]]:
        """
        Fuzzy поиск города в справочнике.
        
        Args:
            user_input: Ввод пользователя (lowercase)
            city_dict: Словарь {город: id}
            threshold: Минимальный % совпадения (default 80%)
        
        Returns:
            tuple(найденный_ключ, id, score) или None
        """
        if not FUZZY_ENABLED or not city_dict:
            return None
        
        # Извлекаем все ключи
        choices = list(city_dict.keys())
        
        # Ищем лучшее совпадение
        result = process.extractOne(user_input, choices, scorer=fuzz.ratio)
        
        if result:
            best_match, score = result[0], result[1]
            if score >= threshold:
                return (best_match, city_dict[best_match], score)
        
        # Пробуем partial_ratio для случаев типа "сочи" → "сочи (адлер)"
        result_partial = process.extractOne(user_input, choices, scorer=fuzz.partial_ratio)
        
        if result_partial:
            best_match, score = result_partial[0], result_partial[1]
            if score >= 90:  # Более строгий порог для partial
                return (best_match, city_dict[best_match], score)
        
        return None
    
    # ==================== 2. ПОИСК ОТЕЛЕЙ ====================
    
    # ==================== ТРАНСЛИТЕРАЦИЯ РУС → ENG ====================
    # Для поиска отелей "Риксос" → "Rixos"
    TRANSLIT_MAP = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    
    # Известные маппинги отелей (Русский → Английский)
    HOTEL_NAME_ALIASES = {
        "риксос": "rixos", "рикос": "rixos",
        "калиста": "calista", "калист": "calista",
        "регнум": "regnum", 
        "титаник": "titanic",
        "дельфин": "delphin", "делфин": "delphin",
        "барут": "barut",
        "вояж": "voyage", "войаж": "voyage",
        "глория": "gloria",
        "хилтон": "hilton",
        "шератон": "sheraton",
        "мариотт": "marriott", "марриотт": "marriott",
        "атлантис": "atlantis",
        "джумейра": "jumeirah", "джумейр": "jumeirah",
        "санрайз": "sunrise",
        "штайгенбергер": "steigenberger",
    }
    
    def _transliterate(self, text: str) -> str:
        """Транслитерация русского текста в латиницу."""
        result = []
        for char in text.lower():
            result.append(self.TRANSLIT_MAP.get(char, char))
        return "".join(result)
    
    def _normalize_hotel_query(self, query: str) -> list[str]:
        """
        Нормализация запроса для поиска отеля.
        Возвращает список вариантов поиска.
        """
        query_lower = query.lower().strip()
        variants = [query_lower]
        
        # Проверяем известные алиасы
        for rus, eng in self.HOTEL_NAME_ALIASES.items():
            if rus in query_lower:
                variants.append(query_lower.replace(rus, eng))
        
        # Транслитерация если есть кириллица
        if any(ord(c) > 127 for c in query_lower):
            transliterated = self._transliterate(query_lower)
            variants.append(transliterated)
        
        return list(set(variants))  # Убираем дубли
    
    async def find_hotel_by_name(
        self,
        query: str,
        country: Optional[str] = None,
        country_id: Optional[int] = None,
        region: Optional[str] = None,
        resort: Optional[str] = None
    ) -> list[HotelInfo]:
        """
        Поиск отелей по названию с поддержкой транслитерации.
        
        HOTEL FILTER FIX: Если указан region/resort, фильтруем результаты!
        Это предотвращает проблему "Жемчужина в Махачкале" когда ищут Сочи.
        
        Поддерживает:
        - Русские названия: "Риксос" → "Rixos"
        - Частичное совпадение: "rixos" → "Rixos Premium Belek"
        - Нечувствительность к регистру
        - Фильтрация по региону/курорту
        """
        logger.info(f"\n🔍 Поиск отеля: '{query}'" + (f" в регионе: {region or resort}" if region or resort else ""))
        
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
            # Популярные направления (ID из tourvisor_constants.py)
            search_country_ids = [
                COUNTRIES.get("турция", 4),
                COUNTRIES.get("египет", 1), 
                COUNTRIES.get("оаэ", 9),
                COUNTRIES.get("таиланд", 2),
                COUNTRIES.get("мальдивы", 8)
            ]
        
        if not search_country_ids:
            logger.warning("   ⚠️ Страна не определена")
            return []
        
        # Получаем все варианты поиска (с транслитерацией)
        search_variants = self._normalize_hotel_query(query)
        logger.info(f"   🔤 Варианты поиска: {search_variants}")
        
        # Нормализуем region/resort для сравнения
        region_lower = region.lower() if region else None
        resort_lower = resort.lower() if resort else None
        
        results = []
        filtered_by_region = []
        
        for cid in search_country_ids:
            hotels = await self.load_hotels_for_country(cid)
            
            for hotel in hotels:
                hotel_name_lower = hotel.name.lower()
                
                # Проверяем все варианты запроса
                for variant in search_variants:
                    if variant in hotel_name_lower:
                        if hotel not in results:  # Избегаем дублей
                            results.append(hotel)
                            
                            # HOTEL FILTER FIX: Проверяем совпадение региона/курорта
                            # ИСПРАВЛЕНО: Используем правильные атрибуты HotelInfo!
                            if region_lower or resort_lower:
                                # HotelInfo имеет: region_name, resort_name
                                hotel_region = (hotel.region_name or '').lower()
                                hotel_resort = (hotel.resort_name or '').lower()
                                
                                # Fuzzy matching: проверяем вхождение в обе стороны
                                location_match = False
                                search_terms = [region_lower, resort_lower]
                                hotel_locations = [hotel_region, hotel_resort]
                                
                                for search_term in search_terms:
                                    if not search_term:
                                        continue
                                    for hotel_loc in hotel_locations:
                                        if not hotel_loc:
                                            continue
                                        # Двусторонний fuzzy match
                                        if search_term in hotel_loc or hotel_loc in search_term:
                                            location_match = True
                                            break
                                    if location_match:
                                        break
                                
                                if location_match:
                                    filtered_by_region.append(hotel)
                                    logger.info(f"   ✅ Найден в {region or resort}: {hotel.name} ({hotel.stars}*) [region={hotel_region}, resort={hotel_resort}]")
                            else:
                                logger.info(f"   ✅ Найден: {hotel.name} ({hotel.stars}*)")
                        break
        
        # Если указан регион — применяем фильтрацию
        if region_lower or resort_lower:
            if filtered_by_region:
                logger.info(f"   📊 Отфильтровано по региону '{region or resort}': {len(filtered_by_region)} из {len(results)} отелей")
                return filtered_by_region
            elif results:
                # FALLBACK: Фильтрация дала 0, но общий поиск нашёл отели
                # Возвращаем полный список чтобы не терять результаты из-за опечаток
                logger.warning(f"   ⚠️ Фильтр по региону '{region or resort}' дал 0 результатов. Показываем все {len(results)} найденных отелей.")
                return results
        
        if results:
            logger.info(f"   📊 Всего найдено: {len(results)} отелей")
        else:
            logger.warning(f"   ⚠️ Отели не найдены для запроса: {search_variants}")
        
        return results
    
    # ==================== 3. АСИНХРОННЫЙ ПОИСК ТУРОВ (search.php) ====================
    
    async def search_tours(
        self,
        params: SearchRequest,
        filters: Optional[TourFilters] = None,
        is_strict_hotel_search: bool = False,
        hotel_ids: Optional[list[int]] = None,
        is_hot_tour: bool = False
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
        
        # ==================== ГОРОД ВЫЛЕТА (NO DEFAULT!) ====================
        departure_id = self.get_departure_id(params.departure_city)
        
        if not departure_id:
            logger.error(f"❌ Город вылета '{params.departure_city}' НЕ НАЙДЕН в справочнике!")
            # НЕ используем дефолт Москва — возвращаем ошибку
            return SearchResponse(
                offers=[], total_found=0, found=False,
                reason="unknown_departure",
                suggestion=f"Город вылета '{params.departure_city}' не найден"
            )
        
        logger.info(f"   ✈️ Город вылета: '{params.departure_city}' → ID={departure_id}")
        
        # Если указан отель — ищем его ID (с фильтрацией по региону!)
        if params.hotel_name and not hotel_ids:
            logger.info(f"   🏨 Поиск отеля: {params.hotel_name}")
            # HOTEL FILTER FIX: Передаём region/resort для фильтрации
            hotels = await self.find_hotel_by_name(
                params.hotel_name, 
                country_id=country_id,
                region=params.destination.region if params.destination else None,
                resort=params.destination.resort if params.destination else None
            )
            if hotels:
                hotel_ids = [h.hotel_id for h in hotels[:5]]
                logger.info(f"   ✅ ID отелей: {hotel_ids}")
            elif is_strict_hotel_search:
                # ⛔ STOP: Строгий поиск по отелю, но ID не найдены — НЕ делаем общий поиск!
                logger.warning(f"   ⛔ STOP: Strict hotel search for '{params.hotel_name}' but no IDs found. Returning empty.")
                return SearchResponse(
                    offers=[], total_found=0, found=False,
                    reason="hotel_not_found_in_db",
                    suggestion=f"Отель '{params.hotel_name}' не найден в базе туроператоров"
                )
        
        # ⛔ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Если strict поиск, но hotel_ids пустые — СТОП!
        if is_strict_hotel_search and not hotel_ids:
            logger.warning("⛔ STOP: Strict hotel search requested but no hotel_ids provided. Returning empty.")
            return SearchResponse(
                offers=[], total_found=0, found=False,
                reason="hotel_not_found_in_db",
                suggestion="Отель не найден в базе туроператоров"
            )
        
        # === STEP 0.5: Динамический поиск ID региона через API ===
        region_id = None
        if params.destination and params.destination.region:
            region_id = await self.get_region_id_by_name(
                params.destination.region, 
                country_id
            )
        
        # === STEP 1: Инициируем поиск ===
        api_params = self._build_search_params(
            params, country_id, departure_id, hotel_ids,
            is_hot_tour=is_hot_tour,
            region_id=region_id
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
                request_id, country_id, is_strict_hotel_search, hotel_ids,
                departure_city=params.departure_city or "Москва"
            )
            
            # ==================== СТРОГАЯ ФИЛЬТРАЦИЯ ПО ЗВЁЗДАМ ====================
            # API Tourvisor НЕ гарантирует соответствие параметру starsfrom!
            # Мы ОБЯЗАНЫ фильтровать на своей стороне для гарантии качества.
            # НИКАКОГО SOFT FALLBACK — если клиент просил 5*, показываем ТОЛЬКО 5*!
            
            logger.info(f"   📊 API вернул {len(offers)} туров (onpage=100)")
            
            if params.stars and offers:
                original_count = len(offers)
                min_stars = int(params.stars)
                
                # СТРОГИЙ ФИЛЬТР: оставляем ТОЛЬКО то, что просил клиент
                filtered_offers = [
                    o for o in offers 
                    if isinstance(o.hotel_stars, int) and o.hotel_stars >= min_stars
                ]
                
                logger.info(f"   🧹 STRICT FILTER {min_stars}*: было {original_count}, стало {len(filtered_offers)}")
                
                # Показываем статистику если были отсеяны отели
                if original_count > len(filtered_offers):
                    rejected = original_count - len(filtered_offers)
                    logger.info(f"   ⛔ Отсеяно {rejected} отелей с меньшим кол-вом звёзд")
                
                offers = filtered_offers
            
            # Сортируем по цене и берём СТРОГО 5 (лимит Pydantic!)
            offers = sorted(offers, key=lambda x: x.price)[:5]
            
            if offers:
                logger.info(f"   ✅ Отдаём пользователю: {len(offers)} туров")
                return SearchResponse(
                    offers=offers,
                    total_found=len(offers),
                    search_id=request_id,
                    found=True
                )
            else:
                # ЧЕСТНЫЙ ОТВЕТ: туров с указанными фильтрами нет
                logger.warning(f"   ⚠️ Туры не найдены (stars={params.stars}, food={params.food_type})")
                return SearchResponse(
                    offers=[], 
                    total_found=0, 
                    search_id=request_id,
                    found=False, 
                    reason="no_tours_with_filters",
                    suggestion=f"На {params.stars}* туров нет" if params.stars else "Туры не найдены"
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
        hotel_ids: Optional[list[int]],
        expand_dates: bool = True,
        expand_nights: bool = True,
        is_hot_tour: bool = False,
        region_id: Optional[int] = None  # ID региона (из API)
    ) -> dict:
        """
        Формирование параметров для search.php.
        
        Согласно документации 1. Поиск туров.docx:
        - datefrom, dateto: в формате dd.mm.yyyy
        - child: количество детей
        - childage1, childage2...: возрасты детей (НЕ массив!)
        - hotels: список ID через запятую
        
        КРИТИЧНО: Даты уже расширены в nodes.py — просто используем их!
        """
        # ==================== P1 FIX: NIGHTS PRIORITY ====================
        # КРИТИЧНО: Явно указанные пользователем ночи ВСЕГДА имеют приоритет!
        # Диапазон дат (date_from/date_to) расширяется в nodes.py для гибкости поиска,
        # но это НЕ должно влиять на количество ночей.
        
        date_start = params.date_from
        date_end = params.date_to or params.date_from
        
        # P1 FIX: Приоритет явных nights над вычисленными из дат
        if params.nights:
            # Ночи явно указаны пользователем — используем их БЕЗ ИЗМЕНЕНИЙ
            nights_from = params.nights
            logger.info(f"   📅 P1: Явные nights={nights_from}, даты поиска: {date_start.strftime('%d.%m')} - {date_end.strftime('%d.%m')}")
        elif params.date_to and params.date_to != params.date_from:
            # Ночи НЕ указаны, но есть точный диапазон дат (например "с 10 по 17 июня")
            # В этом случае вычисляем nights из разницы
            calculated_nights = (params.date_to - params.date_from).days
            nights_from = calculated_nights if calculated_nights > 0 else 7
            logger.info(f"   📅 P1: Вычислено из диапазона: nights={nights_from} ({date_start.strftime('%d.%m')} - {date_end.strftime('%d.%m')})")
        else:
            logger.warning("⚠️ P1: nights не указан и нет диапазона — fallback=7")
            nights_from = 7  # Fallback
        
        # ==================== R7 FIX: Уменьшенный диапазон ночей ====================
        # Было +2 (7→9), стало +1 (7→8) для более точного соответствия запросу
        # Это решает проблему "запросил 7 ночей, получил 8"
        nights_to = nights_from + 1
        logger.info(f"   R7 FIX: nightsfrom={nights_from}, nightsto={nights_to}")
        
        # ==================== DEPARTURE: P0 STABILIZATION ====================
        # departure=0 ставится ТОЛЬКО для hotel_only режима!
        # Для package/burning отсутствие departure — ошибка каскада.
        mode = getattr(params, "search_mode", "package")
        
        # P0 STABILIZATION: departure=0 ТОЛЬКО для hotel_only режима!
        # Для package/burning отсутствие departure — это ошибка каскада (должен был спросить).
        
        is_hotel_only = (mode == "hotel_only")
        
        # departure=0 ставится ТОЛЬКО для hotel_only
        if is_hotel_only:
            final_departure_id = 0
            logger.info(f"   🚗 HOTEL_ONLY MODE: departure=0")
        elif departure_id:
            final_departure_id = departure_id
            logger.info(f"   ✈️ ПЕРЕЛЁТ: departure={final_departure_id}")
        else:
            # P0: Для package/burning БЕЗ departure — это критическая ошибка!
            # Каскад должен был спросить "Откуда вылетаете?"
            logger.error(f"   ❌ P0 ERROR: mode={mode} без departure_id! Каскад не спросил город вылета.")
            # Используем departure_id=0 как fallback, но логируем ошибку
            final_departure_id = 0
            logger.warning(f"   ⚠️ FALLBACK: departure=0 (но это ошибка каскада!)")
        
        api_params = {
            "departure": final_departure_id,
            "country": country_id,
            "datefrom": date_start.strftime("%d.%m.%Y"),
            "dateto": date_end.strftime("%d.%m.%Y"),
            "nightsfrom": nights_from,
            "nightsto": nights_to,
            "adults": params.adults,
            # КРИТИЧНО: Показываем ВСЕ рейсы включая регулярные (GDS)!
            "hideregular": 0,
        }
        
        # === ДЕТИ: передаём как childage1, childage2... ===
        if params.children:
            api_params["child"] = len(params.children)
            for i, age in enumerate(params.children, 1):
                api_params[f"childage{i}"] = age
        
        # Регион/курорт — используем параметр "regions" (множественное число!)
        # Согласно "1. Поиск туров.docx", Source 185
        if region_id:
            api_params["regions"] = region_id  # CRITICAL: "regions", не "region"!
            logger.info(f"   🗺️ Регион '{params.destination.region}' → regions={region_id}")
        elif params.destination.region:
            # Fallback: передаём текстом (не рекомендуется, но API может понять)
            api_params["regions"] = params.destination.region
            logger.warning(f"   ⚠️ Регион '{params.destination.region}' передаём текстом (ID не найден)")
        
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
        
        # === УСЛУГИ ОТЕЛЕЙ (services) ===
        # Передаются как список ID через запятую
        if hasattr(params, 'services') and params.services:
            api_params["services"] = ",".join(map(str, params.services))
        
        # === ТИПЫ ОТЕЛЕЙ (hoteltypes) ===
        # Значения: active, relax, family, health, city, beach, deluxe
        if hasattr(params, 'hotel_types') and params.hotel_types:
            api_params["hoteltypes"] = ",".join(params.hotel_types)
        
        # === ТИП ТУРА (tourtype) ===
        # 0=любой, 1=пляжный, 2=горнолыжный, 3=экскурсионный
        if hasattr(params, 'tour_type') and params.tour_type is not None:
            api_params["tourtype"] = params.tour_type
        
        # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ API ПАРАМЕТРОВ ===
        logger.info(f"   📡 API params: nights={nights_from}-{nights_to}, "
                   f"dates={date_start.strftime('%d.%m')}-{date_end.strftime('%d.%m')}, "
                   f"adults={params.adults}, stars={params.stars}, meal={api_params.get('meal', 'any')}, "
                   f"hideregular={api_params.get('hideregular', 'N/A')}")
        
        # === ПОЛНЫЙ URL ДЛЯ СРАВНЕНИЯ С БРАУЗЕРОМ ===
        url_params = "&".join(f"{k}={v}" for k, v in api_params.items())
        full_url = f"http://tourvisor.ru/xml/search.php?{url_params}&format=json"
        logger.info(f"   🔗 ПОЛНЫЙ URL: {full_url}")
        
        # === ЭКВИВАЛЕНТНАЯ ССЫЛКА ДЛЯ БРАУЗЕРА TOURVISOR ===
        browser_url = (
            f"https://tourvisor.ru/tours/{params.destination.country.lower() if params.destination else 'turkey'}/"
            f"?s_nights_from={nights_from}&s_nights_to={nights_to}"
            f"&s_j_date_from={date_start.strftime('%d.%m.%Y')}&s_j_date_to={date_end.strftime('%d.%m.%Y')}"
            f"&s_adults={params.adults}"
            f"&s_flyfrom={final_departure_id}&s_country={country_id}"
            f"&s_regular=1"  # Включаем регулярные рейсы
            + (f"&s_stars={params.stars}" if params.stars else "")
            + (f"&s_meal={api_params.get('meal', '')}" if api_params.get('meal') else "")
        )
        logger.info(f"   🌐 BROWSER URL: {browser_url}")
        
        # === 🔥 ДЕТЕКТОР ЛЖИ (TRUTH CHECK) ===
        print(f"\n🔥 [TRUTH CHECK] SEARCH MODE: {getattr(params, 'tour_type', 'package')} | DEPARTURE ID: {api_params.get('departure')}")
        print(f"🔥 [TRUTH CHECK] DATES SENT: {api_params.get('datefrom')} - {api_params.get('dateto')}")
        print(f"🔥 [TRUTH CHECK] NIGHTS SENT: {api_params.get('nightsfrom')} - {api_params.get('nightsto')}")
        print(f"🔥 [TRUTH CHECK] FINAL URL: http://tourvisor.ru/xml/search.php?{url_params}\n")
        
        return api_params
    
    async def _poll_and_fetch_results(
        self,
        request_id: str,
        country_id: int,
        is_strict_hotel_search: bool,
        hotel_ids: Optional[list[int]],
        onpage: int = 100,  # УВЕЛИЧЕНО: запрашиваем 100 отелей для глубокой выборки
        departure_city: str = "Москва"  # Город вылета для карточек
    ) -> list[TourOffer]:
        """
        Цикл опроса статуса и получения результатов.
        
        Протокол (УЛУЧШЕННЫЙ):
        1. Ждём минимум min_wait_seconds (5 сек) перед первым fetch
        2. result.php?type=status — проверяем progress
        3. Забираем результаты при progress >= 50% ИЛИ state == finished
        4. Перезабираем финальные результаты когда state == finished
        
        КРИТИЧНО: onpage=100 чтобы получить достаточную выборку для фильтрации!
        """
        all_offers = []
        fetched = False
        start_time = asyncio.get_event_loop().time()
        
        logger.info(f"   🔄 Начинаем опрос результатов (request_id={request_id})")
        
        for attempt in range(1, self.max_poll_attempts + 1):
            await asyncio.sleep(self.poll_interval)
            
            elapsed = asyncio.get_event_loop().time() - start_time
            
            # === Проверяем статус ===
            status = await self._get_search_status(request_id)
            
            logger.info(f"   ⏳ [{attempt}/{self.max_poll_attempts}] "
                       f"Progress: {status.progress}% | State: {status.state} | "
                       f"Elapsed: {elapsed:.1f}s | Found: {len(all_offers)}")
            
            # === КРИТИЧНО: Ждём минимум 5 секунд перед первым fetch ===
            if elapsed < self.min_wait_seconds:
                continue
            
            # === P1: ИСПРАВЛЕНИЕ ДУБЛИРОВАНИЯ RESULT.PHP ===
            # Если завершено — делаем ОДИН финальный fetch и выходим
            if status.state == "finished":
                final_offers = await self._fetch_results(
                    request_id, country_id, is_strict_hotel_search, hotel_ids,
                    onpage=onpage, departure_city=departure_city
                )
                if final_offers:
                    all_offers = final_offers
                    fetched = True
                logger.info(f"   🏁 P1: Поиск завершён: {len(all_offers)} туров за {elapsed:.1f}s (1 fetch)")
                break
            
            # Промежуточные результаты — только если ещё не finished
            if status.progress >= self.min_progress_to_fetch and not fetched:
                offers = await self._fetch_results(
                    request_id, country_id, is_strict_hotel_search, hotel_ids,
                    onpage=onpage, departure_city=departure_city
                )
                if offers:
                    all_offers = offers
                    fetched = True
                    logger.info(f"   ✅ Промежуточные результаты: {len(offers)} туров (progress={status.progress}%)")
        
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
        hotel_ids: Optional[list[int]],
        page: int = 1,
        onpage: int = 100,  # CRITICAL: 100 для глубокой выборки (Source 216)
        departure_city: str = "Москва"  # Город вылета для карточек
    ) -> list[TourOffer]:
        """
        Получение результатов поиска с поддержкой пагинации.
        
        Метод: result.php?type=result&requestid=XXX&page=N&onpage=M
        Согласно "1. Поиск туров.docx", Source 216
        
        Args:
            request_id: ID поискового запроса
            country_id: ID страны
            is_strict_hotel_search: Строгий поиск по отелю
            hotel_ids: Список ID отелей
            page: Номер страницы (начиная с 1)
            onpage: Количество отелей на странице (100 для глубокой выборки)
            departure_city: Город вылета из SearchRequest (для карточек)
        """
        try:
            response = await self._request("result.php", {
                "type": "result",
                "requestid": request_id,
                "page": page,
                "onpage": onpage
            })
            
            return self._parse_tour_results(
                response, country_id, is_strict_hotel_search, hotel_ids, departure_city
            )
        except Exception as e:
            logger.error(f"❌ Ошибка получения результатов: {e}")
            return []
    
    async def fetch_more_results(
        self,
        request_id: str,
        country_id: int,
        page: int = 2,
        onpage: int = 100,  # Глубокая выборка
        departure_city: str = "Москва"  # Город вылета для карточек
    ) -> list[TourOffer]:
        """
        Получение дополнительных результатов (пагинация).
        
        Используется для кнопки "Ещё туры".
        
        Args:
            request_id: ID поискового запроса (сохранённый ранее)
            country_id: ID страны
            page: Номер страницы (2, 3, 4...)
            onpage: Количество отелей на странице (100 для глубокой выборки)
            departure_city: Город вылета (для отображения в карточках)
            
        Returns:
            Список дополнительных туров
        """
        logger.info(f"📄 Загрузка страницы {page} результатов...")
        
        return await self._fetch_results(
            request_id=request_id,
            country_id=country_id,
            is_strict_hotel_search=False,
            hotel_ids=None,
            page=page,
            onpage=onpage,
            departure_city=departure_city
        )
    
    async def continue_search(
        self,
        request_id: str,
        country_id: int,
        departure_city: str = "Москва"  # Город вылета для карточек
    ) -> tuple[list[TourOffer], bool]:
        """
        Продолжение поиска для получения более полных результатов.
        
        GAP Analysis: Реализация continue для углублённого поиска.
        
        Согласно документации Tourvisor API:
        - После первичного поиска можно вызвать search.php?continue=requestid
        - Это продолжит опрос туроператоров для получения большего количества туров
        
        Args:
            request_id: ID предыдущего поискового запроса
            country_id: ID страны
            departure_city: Город вылета (для отображения в карточках)
            
        Returns:
            Tuple (список туров, есть ли ещё результаты)
        """
        logger.info(f"🔄 Продолжение поиска: {request_id}")
        
        try:
            # Запрос на продолжение поиска
            response = await self._request("search.php", {
                "continue": request_id
            })
            
            # Получаем новый requestid или используем старый
            new_request_id = response.get("result", {}).get("requestid", request_id)
            
            # Ждём дополнительные результаты (глубокая выборка)
            offers = await self._poll_and_fetch_results(
                request_id=new_request_id,
                country_id=country_id,
                is_strict_hotel_search=False,
                hotel_ids=None,
                onpage=100,  # Глубокая выборка
                departure_city=departure_city
            )
            
            # Сортируем и берём СТРОГО 5 туров (лимит Pydantic!)
            offers = sorted(offers, key=lambda x: x.price)[:5]
            
            # Проверяем, есть ли ещё данные
            has_more = len(offers) >= 5
            
            return offers, has_more
            
        except Exception as e:
            logger.error(f"❌ Ошибка продолжения поиска: {e}")
            return [], False
    
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
        hotel_ids: Optional[list[int]],
        departure_city: str = "Москва"
    ) -> list[TourOffer]:
        """Парсинг результатов поиска.
        
        Args:
            departure_city: Город вылета из SearchRequest (для карточек)
        """
        
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
                offer = self._parse_single_offer(hotel, expected_country, departure_city)
                if offer:
                    offers.append(offer)
            except Exception as e:
                logger.debug(f"Ошибка парсинга: {e}")
                continue
        
        return offers
    
    def _parse_single_offer(self, hotel: dict, country_name: Optional[str], departure_city: str = "Москва") -> Optional[TourOffer]:
        """Парсинг одного предложения.
        
        Args:
            hotel: Данные отеля из API
            country_name: Название страны
            departure_city: Город вылета из SearchRequest (не из API!)
        """
        
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
        
        # === GAP Analysis: Извлекаем tour_id для бронирования ===
        tour_id = tour.get("tourid") or tour.get("tour_id") or tour.get("id")
        
        return TourOffer(
            id=str(tour_id if tour_id else uuid.uuid4()),
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
            departure_city=departure_city,  # Используем город из SearchRequest, не из API!
            operator=tour.get("operatorname", ""),
            hotel_link=hotel.get("fulldesclink", ""),
            hotel_photo=hotel.get("picturelink", ""),
            tour_id=str(tour_id) if tour_id else None,  # GAP Analysis: для booking_url
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
        limit: int = 10,
        departure_city: str = "Москва"  # Город вылета для карточек
    ) -> list[TourOffer]:
        """
        Получение горящих туров.
        
        Метод: hottours.php (синхронный, быстрый)
        Документация: 1. Горящие туры.docx
        
        Параметры:
        - city: ID города вылета
        - country: ID страны (опционально)
        - items: количество результатов
        - departure_city: Название города вылета (для отображения в карточках)
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
            
            # P5 FIX: Структура ответа hottours.php — {"hottours": {"tour": [...]}}
            hottours_data = response.get("hottours", {})
            tours_data = hottours_data.get("tour", []) if isinstance(hottours_data, dict) else []
            
            logger.info(f"   🔥 hottours structure: hottours={type(hottours_data).__name__}, tours={len(tours_data) if isinstance(tours_data, list) else 'N/A'}")
            
            if isinstance(tours_data, dict):
                tours_data = [tours_data]
            
            offers = []
            for t in tours_data:
                try:
                    offer = self._parse_hot_tour(t, departure_city)
                    if offer:
                        offers.append(offer)
                except Exception:
                    continue
            
            logger.info(f"🔥 Найдено {len(offers)} горящих туров")
            return offers
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения горящих туров: {e}")
            return []
    
    def _fix_photo_url(self, url: str) -> str:
        """
        P0 FIX: Исправляет protocol-relative URL (//...) на полный https://...
        Проблема: Tourvisor возвращает URL типа //static.tourvisor.ru/...
        Браузер не загружает такие URL без протокола.
        """
        if url and url.startswith('//'):
            return 'https:' + url
        return url or ""
    
    def _parse_hot_tour(self, tour: dict, departure_city: str = "Москва") -> Optional[TourOffer]:
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
            departure_city=departure_city,  # Используем город из параметра, не из API!
            operator=tour.get("operatorname", ""),
            hotel_link=tour.get("fulldesclink", ""),
            # P4 FIX: для hottours поле называется "hotelpicture", не "picturelink"
            # P0 FIX: исправляем protocol-relative URL (//...) на https://...
            hotel_photo=self._fix_photo_url(tour.get("hotelpicture", "")),
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

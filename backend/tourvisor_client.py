"""
TourVisor API Client
Клиент для работы с TourVisor API
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx
from dotenv import load_dotenv

load_dotenv()


# ==================== ИСКЛЮЧЕНИЯ ====================

class TourVisorError(Exception):
    """Базовое исключение TourVisor API"""
    pass


class TourVisorAPIError(TourVisorError):
    """Ошибка от API (errormessage)"""
    def __init__(self, message: str, raw_response: Dict = None):
        super().__init__(message)
        self.raw_response = raw_response


class TourIdExpiredError(TourVisorAPIError):
    """tourid истёк или недействителен"""
    pass


class SearchNotFoundError(TourVisorAPIError):
    """requestid не найден"""
    pass


class NoResultsError(TourVisorError):
    """Поиск завершён без результатов"""
    def __init__(self, message: str = "Туры не найдены", filters_hint: str = None):
        super().__init__(message)
        self.filters_hint = filters_hint  # Подсказка какие фильтры смягчить


class TourVisorClient:
    """Асинхронный клиент TourVisor API"""
    
    def __init__(self):
        self.base_url = os.getenv("TOURVISOR_BASE_URL", "https://tourvisor.ru/xml")
        self.auth_login = os.getenv("TOURVISOR_AUTH_LOGIN")
        self.auth_pass = os.getenv("TOURVISOR_AUTH_PASS")
    
    async def _request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """
        Базовый запрос к API с обработкой ошибок
        
        ВАЖНО: TourVisor возвращает HTTP 200 даже при ошибках!
        Ошибки определяются по полям в JSON:
        - errormessage — текст ошибки
        - success: 0 — флаг неуспеха
        """
        if params is None:
            params = {}
        
        # Добавляем авторизацию
        params["authlogin"] = self.auth_login
        params["authpass"] = self.auth_pass
        params["format"] = "json"
        
        url = f"{self.base_url}/{endpoint}"
        
        # Создаём новый клиент для каждого запроса (избегаем Event loop is closed)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        # Проверяем на ошибки API (HTTP 200, но есть errormessage)
        self._check_api_error(data, endpoint)
        
        return data
    
    def _check_api_error(self, data: Dict, endpoint: str):
        """
        Проверить ответ на ошибки API
        
        Известные ошибки:
        - "Wrong (obsolete) TourID." — tourid истёк
        - "no search results" в status.state — requestid не найден
        """
        # Проверка на errormessage (например, для actualize.php)
        if "data" in data:
            inner = data["data"]
            if isinstance(inner, dict):
                error_msg = inner.get("errormessage")
                success = inner.get("success")
                
                if error_msg:
                    # Специфичные ошибки
                    if "TourID" in error_msg or "tourid" in error_msg.lower():
                        raise TourIdExpiredError(error_msg, data)
                    raise TourVisorAPIError(error_msg, data)
                
                if success == 0:
                    raise TourVisorAPIError("Операция не выполнена (success=0)", data)
        
        # Проверка на "no search results" (для result.php)
        if endpoint == "result.php":
            status = data.get("data", {}).get("status", {})
            if status.get("state") == "no search results":
                raise SearchNotFoundError("Поиск не найден (requestid недействителен)", data)
    
    # ==================== СПРАВОЧНИКИ ====================
    
    async def get_departures(self) -> List[Dict]:
        """Получить список городов вылета"""
        data = await self._request("list.php", {"type": "departure"})
        departures = data.get("lists", {}).get("departures", {}).get("departure", [])
        return departures if isinstance(departures, list) else [departures]
    
    async def get_countries(self, departure_id: Optional[int] = None) -> List[Dict]:
        """Получить список стран (опционально: с вылетами из города)"""
        params = {"type": "country"}
        if departure_id:
            params["cndep"] = departure_id
        data = await self._request("list.php", params)
        countries = data.get("lists", {}).get("countries", {}).get("country", [])
        return countries if isinstance(countries, list) else [countries]
    
    async def get_regions(self, country_id: int) -> List[Dict]:
        """Получить курорты страны"""
        data = await self._request("list.php", {"type": "region", "regcountry": country_id})
        regions = data.get("lists", {}).get("regions", {}).get("region", [])
        return regions if isinstance(regions, list) else [regions]
    
    async def get_subregions(self, country_id: int) -> List[Dict]:
        """Получить районы курортов страны"""
        data = await self._request("list.php", {"type": "subregion", "regcountry": country_id})
        subregions = data.get("lists", {}).get("subregions", {}).get("subregion", [])
        return subregions if isinstance(subregions, list) else [subregions]
    
    async def get_meals(self) -> List[Dict]:
        """Получить типы питания"""
        data = await self._request("list.php", {"type": "meal"})
        meals = data.get("lists", {}).get("meals", {}).get("meal", [])
        return meals if isinstance(meals, list) else [meals]
    
    async def get_stars(self) -> List[Dict]:
        """Получить категории отелей"""
        data = await self._request("list.php", {"type": "stars"})
        stars = data.get("lists", {}).get("stars", {}).get("star", [])
        return stars if isinstance(stars, list) else [stars]
    
    async def get_operators(self, departure_id: Optional[int] = None, country_id: Optional[int] = None) -> List[Dict]:
        """Получить туроператоров"""
        params = {"type": "operator"}
        if departure_id:
            params["flydeparture"] = departure_id
        if country_id:
            params["flycountry"] = country_id
        data = await self._request("list.php", params)
        operators = data.get("lists", {}).get("operators", {}).get("operator", [])
        return operators if isinstance(operators, list) else [operators]
    
    async def get_services(self) -> List[Dict]:
        """Получить услуги отелей"""
        data = await self._request("list.php", {"type": "services"})
        services = data.get("lists", {}).get("services", {}).get("service", [])
        return services if isinstance(services, list) else [services]
    
    async def get_hotels(
        self,
        country_id: int,
        region_id: Optional[str] = None,
        stars: Optional[int] = None,
        rating: Optional[float] = None,
        hotel_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """Получить отели по фильтрам"""
        params = {"type": "hotel", "hotcountry": country_id}
        if region_id:
            params["hotregion"] = region_id
        if stars:
            params["hotstars"] = stars
        if rating:
            params["hotrating"] = rating
        if hotel_types:
            for ht in hotel_types:
                params[f"hot{ht}"] = 1
        
        data = await self._request("list.php", params)
        hotels = data.get("lists", {}).get("hotels", {}).get("hotel", [])
        return hotels if isinstance(hotels, list) else [hotels]
    
    async def get_flydates(self, departure_id: int, country_id: int) -> List[str]:
        """Получить доступные даты вылета"""
        data = await self._request("list.php", {
            "type": "flydate",
            "flydeparture": departure_id,
            "flycountry": country_id
        })
        flydates = data.get("lists", {}).get("flydates", {}).get("flydate", [])
        return flydates if isinstance(flydates, list) else [flydates]
    
    async def get_currencies(self) -> List[Dict]:
        """Получить курсы валют у туроператоров (USD/EUR)"""
        data = await self._request("list.php", {"type": "currency"})
        currencies = data.get("lists", {}).get("currencies", {}).get("currency", [])
        return currencies if isinstance(currencies, list) else [currencies]
    
    # ==================== ПОИСК ТУРОВ ====================
    
    async def search_tours(
        self,
        departure: int,
        country: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        nights_from: int = 7,
        nights_to: int = 10,
        adults: int = 2,
        children: int = 0,
        child_ages: Optional[List[int]] = None,
        stars: Optional[int] = None,
        meal: Optional[int] = None,
        rating: Optional[int] = None,
        hotels: Optional[str] = None,
        regions: Optional[str] = None,
        subregions: Optional[str] = None,
        operators: Optional[str] = None,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        hotel_types: Optional[str] = None,
        services: Optional[str] = None,
        tourid: Optional[str] = None,
        onrequest: Optional[int] = None,
        directflight: Optional[int] = None,
        flightclass: Optional[str] = None,
        currency: Optional[int] = None,
        pricetype: Optional[int] = None,
        starsbetter: Optional[int] = None,
        mealbetter: Optional[int] = None,
        hideregular: Optional[int] = None
    ) -> str:
        """
        Запустить поиск туров
        Возвращает requestid для получения результатов
        """
        # Даты по умолчанию
        if not date_from:
            date_from = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        if not date_to:
            date_to = (datetime.now() + timedelta(days=8)).strftime("%d.%m.%Y")
        
        params = {
            "departure": departure,
            "country": country,
            "datefrom": date_from,
            "dateto": date_to,
            "nightsfrom": nights_from,
            "nightsto": nights_to,
            "adults": adults,
            "child": children
        }
        
        # Возраста детей
        if child_ages:
            for i, age in enumerate(child_ages[:3], 1):
                params[f"childage{i}"] = age
        
        # Опциональные фильтры
        if stars:
            params["stars"] = stars
        if meal:
            params["meal"] = meal
        if rating:
            params["rating"] = rating
        if hotels:
            params["hotels"] = hotels
        if regions:
            params["regions"] = regions
        if subregions:
            params["subregions"] = subregions
        if operators:
            params["operators"] = operators
        if price_from:
            params["pricefrom"] = price_from
        if price_to:
            params["priceto"] = price_to
        if hotel_types:
            params["hoteltypes"] = hotel_types
        if services:
            params["services"] = services
        if tourid:
            params["tourid"] = tourid
        if onrequest is not None:
            params["onrequest"] = onrequest
        if directflight is not None:
            params["directflight"] = directflight
        if flightclass:
            params["flightclass"] = flightclass
        if currency is not None:
            params["currency"] = currency
        if pricetype is not None:
            params["pricetype"] = pricetype
        if starsbetter is not None:
            params["starsbetter"] = starsbetter
        if mealbetter is not None:
            params["mealbetter"] = mealbetter
        if hideregular is not None:
            params["hideregular"] = hideregular
        
        data = await self._request("search.php", params)
        
        # requestid может быть в разных местах
        if "result" in data:
            return data["result"].get("requestid")
        return data.get("requestid")
    
    async def get_search_status(self, request_id: str) -> Dict:
        """Получить статус поиска"""
        data = await self._request("result.php", {
            "requestid": request_id,
            "type": "status"
        })
        return data.get("data", {}).get("status", {})
    
    async def get_search_results(
        self,
        request_id: str,
        page: int = 1,
        per_page: int = 25,
        include_operators: bool = False,
        no_description: bool = False
    ) -> Dict:
        """Получить результаты поиска"""
        params = {
            "requestid": request_id,
            "type": "result",
            "page": page,
            "onpage": per_page
        }
        if include_operators:
            params["operatorstatus"] = 1
        if no_description:
            params["nodescription"] = 1
        
        data = await self._request("result.php", params)
        return data.get("data", {})
    
    async def wait_for_search(
        self,
        request_id: str,
        max_wait: int = 30,
        poll_interval: float = 2.0
    ) -> Dict:
        """
        Дождаться завершения поиска и вернуть результаты
        
        Raises:
            NoResultsError: Поиск завершён, но туры не найдены
            SearchNotFoundError: requestid недействителен
        """
        start = datetime.now()
        last_status = {}
        
        while (datetime.now() - start).seconds < max_wait:
            try:
                last_status = await self.get_search_status(request_id)
            except SearchNotFoundError:
                raise  # requestid недействителен
            
            state = last_status.get("state")
            
            if state == "finished":
                # Проверяем есть ли результаты
                hotels_found = last_status.get("hotelsfound", 0)
                tours_found = last_status.get("toursfound", 0)
                
                if hotels_found == 0 or tours_found == 0:
                    raise NoResultsError(
                        f"Поиск завершён: найдено {hotels_found} отелей, {tours_found} туров",
                        filters_hint="Попробуйте расширить даты, увеличить бюджет или убрать фильтры"
                    )
                
                return await self.get_search_results(request_id)
            
            await asyncio.sleep(poll_interval)
        
        # Timeout — возвращаем что есть (может быть частичный результат)
        hotels = last_status.get("hotelsfound", 0)
        if hotels == 0:
            raise NoResultsError(
                "Поиск не завершён за отведённое время и результатов нет",
                filters_hint="Попробуйте позже или измените параметры поиска"
            )
        
        return await self.get_search_results(request_id)
    
    # ==================== АКТУАЛИЗАЦИЯ ====================
    
    async def actualize_tour(
        self,
        tour_id: str,
        request_mode: int = 2,  # 0=авто, 1=всегда запрос, 2=из кэша
        currency: int = 0  # 0=RUB, 1=USD/EUR, 2=BYR, 3=KZT
    ) -> Dict:
        """
        Актуализировать цену тура
        
        ВАЖНО: tourid живёт ~24 часа после поиска!
        
        Args:
            tour_id: ID тура из результатов поиска
            request_mode: 0=авто, 1=всегда запрос к ТО (тратит лимит!), 2=из кэша
            currency: 0=RUB, 1=USD/EUR, 2=BYR, 3=KZT
        
        Returns:
            Dict с актуальными данными тура
        
        Raises:
            TourIdExpiredError: tourid истёк — нужен новый поиск
        """
        params = {
            "tourid": tour_id,
            "request": request_mode
        }
        if currency != 0:
            params["currency"] = currency
        
        try:
            data = await self._request("actualize.php", params)
        except TourIdExpiredError as e:
            # Добавляем контекст для AI
            e.args = (
                "Данные тура устарели (прошло более 24 часов). "
                "Необходимо выполнить новый поиск с теми же параметрами.",
            )
            raise
        
        tour_data = data.get("data", {}).get("tour", {})
        
        # Добавляем флаг актуальности
        tour_data["_actualized"] = True
        tour_data["_actualized_at"] = datetime.now().isoformat()
        
        return tour_data
    
    async def get_tour_details(
        self, 
        tour_id: str,
        currency: int = 0  # 0=RUB, 1=USD/EUR, 2=BYR, 3=KZT
    ) -> Dict:
        """
        Получить детальную информацию о туре (рейсы, доплаты)
        
        ВАЖНО: Каждый вызов тратит лимит запросов!
        
        Raises:
            TourIdExpiredError: tourid истёк
        """
        params = {"tourid": tour_id}
        if currency != 0:
            params["currency"] = currency
        
        try:
            data = await self._request("actdetail.php", params)
        except TourIdExpiredError as e:
            e.args = (
                "Данные тура устарели. Нужен новый поиск для получения деталей рейсов.",
            )
            raise
        
        return data
    
    # ==================== ОТЕЛИ ====================
    
    async def get_hotel_info(
        self,
        hotel_code: int,
        big_images: bool = False,
        remove_tags: bool = True,
        include_reviews: bool = False
    ) -> Dict:
        """Получить информацию об отеле"""
        params = {"hotelcode": hotel_code}
        if big_images:
            params["imgbig"] = 1
        if remove_tags:
            params["removetags"] = 1
        if include_reviews:
            params["reviews"] = 1
        
        data = await self._request("hotel.php", params)
        return data.get("data", {}).get("hotel", {})
    
    # ==================== ГОРЯЩИЕ ТУРЫ ====================
    
    async def get_hot_tours(
        self,
        city: int,
        count: int = 10,
        city2: Optional[int] = None,
        city3: Optional[int] = None,
        uniq2: Optional[int] = None,
        uniq3: Optional[int] = None,
        countries: Optional[str] = None,
        regions: Optional[str] = None,
        operators: Optional[str] = None,
        datefrom: Optional[str] = None,
        dateto: Optional[str] = None,
        stars: Optional[int] = None,
        meal: Optional[int] = None,
        rating: Optional[float] = None,
        max_days: Optional[int] = None,
        tour_type: int = 0,  # 0=все, 1=пляжные, 2=горнолыжные, 3=экскурсионные
        visa_free: bool = False,
        sort_by_price: bool = False,
        picturetype: int = 0,  # 0=130px, 1=250px
        currency: int = 0  # 0=RUB, 1=USD/EUR
    ) -> List[Dict]:
        """Получить горящие туры"""
        params = {
            "city": city,
            "items": count
        }
        
        # Дополнительные города вылета
        if city2:
            params["city2"] = city2
        if city3:
            params["city3"] = city3
        if uniq2 is not None:
            params["uniq2"] = uniq2
        if uniq3 is not None:
            params["uniq3"] = uniq3
        
        # Фильтры направлений
        if countries:
            params["countries"] = countries
        if regions:
            params["regions"] = regions
        if operators:
            params["operators"] = operators
        
        # Диапазон дат
        if datefrom:
            params["datefrom"] = datefrom
        if dateto:
            params["dateto"] = dateto
        
        # Фильтры отелей
        if stars:
            params["stars"] = stars
        if meal:
            params["meal"] = meal
        if rating:
            params["rating"] = rating
        if max_days:
            params["maxdays"] = max_days
        if tour_type:
            params["tourtype"] = tour_type
        if visa_free:
            params["visa"] = 1
        if sort_by_price:
            params["sort"] = 1
        if picturetype:
            params["picturetype"] = picturetype
        if currency:
            params["currency"] = currency
        
        data = await self._request("hottours.php", params)
        tours = data.get("hottours", {}).get("tour", [])
        return tours if isinstance(tours, list) else [tours]


# ==================== УТИЛИТЫ ====================

def calculate_total_price(
    base_price: int,
    visa_charge: int,
    adults: int,
    children: int,
    add_payments: Optional[List[Dict]] = None
) -> int:
    """
    Рассчитать полную стоимость тура
    
    ВАЖНО:
    - base_price уже включает топливный сбор
    - visa_charge и add_payments указаны ЗА ЧЕЛОВЕКА
    """
    total = base_price
    people = adults + children
    
    # Виза
    total += visa_charge * people
    
    # Доплаты
    if add_payments:
        for payment in add_payments:
            amount = int(payment.get("amount", 0))
            total += amount * people
    
    return total


def calculate_hot_tour_price(price_per_person: int, people: int = 2) -> int:
    """
    Рассчитать стоимость горящего тура
    
    ВАЖНО: Цена в горящих турах указана ЗА ЧЕЛОВЕКА (1/2 DBL)
    """
    return price_per_person * people


def calculate_discount(price: int, price_old: int) -> float:
    """Рассчитать процент скидки"""
    if price_old <= 0:
        return 0
    return round((price_old - price) / price_old * 100, 1)


# ==================== ТЕСТ ====================

async def main():
    """Тестовый запуск"""
    client = TourVisorClient()
    
    try:
        # Тест справочников
        print("Города вылета:")
        departures = await client.get_departures()
        for d in departures[:5]:
            print(f"  {d['id']}: {d['name']} (из {d.get('namefrom', '-')})")
        
        print("\nТипы питания:")
        meals = await client.get_meals()
        for m in meals:
            print(f"  {m['id']}: {m['name']} - {m.get('russianfull', m.get('russian', '-'))}")
        
        print("\n✅ Клиент работает!")
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

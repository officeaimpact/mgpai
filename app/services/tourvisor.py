"""
Сервис интеграции с Tourvisor API.

Поддерживает:
- Поиск туров по параметрам (страна, регион, курорт, отель)
- Получение горящих туров
- Информация об отелях
- Mock-режим для тестирования без API ключа
"""
from __future__ import annotations

import httpx
from datetime import date, timedelta
from typing import Optional
import uuid

from app.core.config import settings
from app.models.domain import (
    SearchRequest,
    TourOffer,
    TourFilters,
    HotelDetails,
    SearchResponse,
    FoodType,
    HotelType,
    HotelAmenity
)


class TourvisorService:
    """
    Сервис для работы с Tourvisor API.
    
    При TOURVISOR_MOCK=True возвращает тестовые данные.
    """
    
    def __init__(self):
        self.base_url = settings.TOURVISOR_BASE_URL
        self.api_key = settings.TOURVISOR_API_KEY
        self.mock_enabled = settings.TOURVISOR_MOCK
        self.client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получение HTTP клиента с ленивой инициализацией."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=settings.TOURVISOR_TIMEOUT,
                base_url=self.base_url
            )
        return self.client
    
    async def _request(self, endpoint: str, params: dict) -> dict:
        """
        Выполнение запроса к Tourvisor API.
        
        Args:
            endpoint: Путь к эндпоинту
            params: Параметры запроса
            
        Returns:
            Ответ API в формате dict
        """
        client = await self._get_client()
        params["authlogin"] = self.api_key
        
        response = await client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
    
    async def search_tours(
        self,
        params: SearchRequest,
        filters: Optional[TourFilters] = None
    ) -> SearchResponse:
        """
        Поиск туров по заданным параметрам.
        
        Иерархия поиска: Страна -> Регион -> Курорт -> Отель
        
        Args:
            params: Параметры поиска (направление, даты, туристы)
            filters: Дополнительные фильтры
            
        Returns:
            SearchResponse с 3-5 карточками предложений
        """
        if self.mock_enabled:
            return await self._mock_search_tours(params, filters)
        
        # Реальный запрос к Tourvisor API
        api_params = {
            "departure": params.departure_city,
            "country": params.destination.country,
            "datefrom": params.date_from.strftime("%d.%m.%Y"),
            "dateto": params.date_to.strftime("%d.%m.%Y"),
            "nightsfrom": params.nights or 7,
            "nightsto": params.nights or 14,
            "adults": params.adults,
        }
        
        # Добавляем детей
        if params.children:
            api_params["child"] = len(params.children)
            for i, age in enumerate(params.children, 1):
                api_params[f"childage{i}"] = age
        
        # Иерархия направления
        if params.destination.region:
            api_params["region"] = params.destination.region
        if params.destination.resort:
            api_params["resort"] = params.destination.resort
        if params.hotel_name:
            api_params["hotel"] = params.hotel_name
        
        # Фильтры
        if params.stars:
            api_params["stars"] = params.stars
        if params.food_type:
            api_params["meal"] = params.food_type.value
        
        if filters:
            if filters.min_stars:
                api_params["starsfrom"] = filters.min_stars
            if filters.max_stars:
                api_params["starsto"] = filters.max_stars
            if filters.food_types:
                api_params["meal"] = ",".join(f.value for f in filters.food_types)
        
        try:
            data = await self._request("/search.php", api_params)
            return self._parse_search_response(data)
        except Exception as e:
            # Fallback на mock при ошибке
            print(f"Tourvisor API error: {e}, using mock data")
            return await self._mock_search_tours(params, filters)
    
    async def get_hot_tours(
        self,
        adults: int = 2,
        country: Optional[str] = None
    ) -> SearchResponse:
        """
        Получение горящих туров.
        
        Args:
            adults: Количество взрослых (1-6)
            country: Страна для фильтрации (опционально)
            
        Returns:
            SearchResponse с горящими предложениями
        """
        if self.mock_enabled:
            return await self._mock_hot_tours(adults, country)
        
        api_params = {
            "type": "hot",
            "adults": min(max(adults, 1), 6),
        }
        
        if country:
            api_params["country"] = country
        
        try:
            data = await self._request("/hottours.php", api_params)
            return self._parse_search_response(data)
        except Exception as e:
            print(f"Tourvisor API error: {e}, using mock data")
            return await self._mock_hot_tours(adults, country)
    
    async def get_hotel_details(self, hotel_id: int) -> Optional[HotelDetails]:
        """
        Получение подробной информации об отеле.
        
        Args:
            hotel_id: ID отеля в системе Tourvisor
            
        Returns:
            HotelDetails или None если отель не найден
        """
        if self.mock_enabled:
            return await self._mock_hotel_details(hotel_id)
        
        try:
            data = await self._request("/hotel.php", {"hotelcode": hotel_id})
            return self._parse_hotel_details(data)
        except Exception as e:
            print(f"Tourvisor API error: {e}, using mock data")
            return await self._mock_hotel_details(hotel_id)
    
    def _parse_search_response(self, data: dict) -> SearchResponse:
        """Парсинг ответа API в SearchResponse."""
        offers = []
        
        tours = data.get("data", {}).get("tours", [])
        for tour in tours[:settings.MAX_TOUR_OFFERS]:
            offer = TourOffer(
                id=str(tour.get("tourid", uuid.uuid4())),
                hotel_name=tour.get("hotelname", "Unknown"),
                hotel_stars=int(tour.get("hotelstars", 3)),
                hotel_rating=float(tour.get("hotelrating")) if tour.get("hotelrating") else None,
                hotel_link=tour.get("hotellink"),
                country=tour.get("countryname", ""),
                region=tour.get("regionname"),
                resort=tour.get("resortname"),
                date_from=date.fromisoformat(tour.get("datefrom", str(date.today()))),
                date_to=date.fromisoformat(tour.get("dateto", str(date.today() + timedelta(days=7)))),
                nights=int(tour.get("nights", 7)),
                price=int(tour.get("price", 0)),
                price_per_person=int(tour.get("priceperperson")) if tour.get("priceperperson") else None,
                food_type=FoodType(tour.get("meal", "AI")),
                room_type=tour.get("roomtype"),
                departure_city=tour.get("departure", "Москва"),
                operator=tour.get("operatorname", "Unknown")
            )
            offers.append(offer)
        
        return SearchResponse(
            offers=offers,
            total_found=data.get("data", {}).get("total", len(offers)),
            search_id=data.get("data", {}).get("searchid")
        )
    
    def _parse_hotel_details(self, data: dict) -> HotelDetails:
        """Парсинг информации об отеле."""
        hotel = data.get("data", {}).get("hotel", {})
        
        return HotelDetails(
            id=hotel.get("hotelcode", 0),
            name=hotel.get("hotelname", "Unknown"),
            stars=int(hotel.get("hotelstars", 3)),
            rating=float(hotel.get("hotelrating")) if hotel.get("hotelrating") else None,
            country=hotel.get("countryname", ""),
            region=hotel.get("regionname"),
            resort=hotel.get("resortname"),
            address=hotel.get("address"),
            description=hotel.get("description"),
            photos=hotel.get("photos", [])
        )
    
    def _apply_filters(
        self,
        offers: list[TourOffer],
        filters: Optional[TourFilters]
    ) -> list[TourOffer]:
        """Применение фильтров к списку предложений."""
        if not filters:
            return offers
        
        filtered = offers
        
        if filters.food_types:
            filtered = [o for o in filtered if o.food_type in filters.food_types]
        
        if filters.min_stars:
            filtered = [o for o in filtered if o.hotel_stars >= filters.min_stars]
        
        if filters.max_stars:
            filtered = [o for o in filtered if o.hotel_stars <= filters.max_stars]
        
        if filters.min_price:
            filtered = [o for o in filtered if o.price >= filters.min_price]
        
        if filters.max_price:
            filtered = [o for o in filtered if o.price <= filters.max_price]
        
        if filters.min_rating:
            filtered = [o for o in filtered if o.hotel_rating and o.hotel_rating >= filters.min_rating]
        
        return filtered
    
    # ==================== MOCK DATA ====================
    
    async def _mock_search_tours(
        self,
        params: SearchRequest,
        filters: Optional[TourFilters] = None
    ) -> SearchResponse:
        """Mock-данные для поиска туров."""
        
        base_date = params.date_from
        nights = params.nights or 7
        
        # Определяем страну для mock-данных
        country = params.destination.country.lower()
        
        mock_offers = self._get_mock_offers_by_country(
            country=country,
            base_date=base_date,
            nights=nights,
            departure_city=params.departure_city,
            adults=params.adults
        )
        
        # Применяем фильтры
        filtered_offers = self._apply_filters(mock_offers, filters)
        
        # Если указан конкретный отель, фильтруем
        if params.hotel_name:
            filtered_offers = [
                o for o in filtered_offers 
                if params.hotel_name.lower() in o.hotel_name.lower()
            ]
        
        # Если указана звёздность
        if params.stars:
            filtered_offers = [o for o in filtered_offers if o.hotel_stars == params.stars]
        
        # Если указан тип питания
        if params.food_type:
            filtered_offers = [o for o in filtered_offers if o.food_type == params.food_type]
        
        return SearchResponse(
            offers=filtered_offers[:5],
            total_found=len(filtered_offers),
            search_id=f"mock-{uuid.uuid4().hex[:8]}"
        )
    
    async def _mock_hot_tours(
        self,
        adults: int = 2,
        country: Optional[str] = None
    ) -> SearchResponse:
        """Mock-данные для горящих туров."""
        
        base_date = date.today() + timedelta(days=3)  # Горящие - через 3 дня
        
        hot_offers = []
        
        # Турция - горящий
        hot_offers.append(TourOffer(
            id=f"hot-{uuid.uuid4().hex[:8]}",
            hotel_name="Rixos Premium Belek",
            hotel_stars=5,
            hotel_rating=9.2,
            hotel_link="https://tourvisor.ru/hotel/rixos-premium-belek",
            hotel_photo="https://images.tourvisor.ru/hotels/rixos-belek.jpg",
            country="Турция",
            region="Анталья",
            resort="Белек",
            date_from=base_date,
            date_to=base_date + timedelta(days=7),
            nights=7,
            price=89900,
            price_per_person=89900 // adults,
            food_type=FoodType.UAI,
            room_type="Standard Room",
            departure_city="Москва",
            operator="Anex Tour"
        ))
        
        # Египет - горящий
        hot_offers.append(TourOffer(
            id=f"hot-{uuid.uuid4().hex[:8]}",
            hotel_name="Steigenberger Alcazar",
            hotel_stars=5,
            hotel_rating=8.8,
            hotel_link="https://tourvisor.ru/hotel/steigenberger-alcazar",
            country="Египет",
            region="Красное море",
            resort="Шарм-эль-Шейх",
            date_from=base_date,
            date_to=base_date + timedelta(days=10),
            nights=10,
            price=72000,
            price_per_person=72000 // adults,
            food_type=FoodType.AI,
            room_type="Sea View Room",
            departure_city="Москва",
            operator="Coral Travel"
        ))
        
        # ОАЭ - горящий
        hot_offers.append(TourOffer(
            id=f"hot-{uuid.uuid4().hex[:8]}",
            hotel_name="Atlantis The Palm",
            hotel_stars=5,
            hotel_rating=9.5,
            hotel_link="https://tourvisor.ru/hotel/atlantis-palm",
            country="ОАЭ",
            region="Дубай",
            resort="Пальма Джумейра",
            date_from=base_date + timedelta(days=1),
            date_to=base_date + timedelta(days=8),
            nights=7,
            price=156000,
            price_per_person=156000 // adults,
            food_type=FoodType.BB,
            room_type="Ocean View",
            departure_city="Москва",
            operator="TUI Russia"
        ))
        
        # Фильтруем по стране если указана
        if country:
            country_lower = country.lower()
            hot_offers = [
                o for o in hot_offers 
                if country_lower in o.country.lower()
            ]
        
        return SearchResponse(
            offers=hot_offers[:5],
            total_found=len(hot_offers),
            search_id=f"hot-mock-{uuid.uuid4().hex[:8]}"
        )
    
    async def _mock_hotel_details(self, hotel_id: int) -> HotelDetails:
        """Mock-данные для информации об отеле."""
        
        mock_hotels = {
            1: HotelDetails(
                id=1,
                name="Rixos Premium Belek",
                stars=5,
                rating=9.2,
                country="Турция",
                region="Анталья",
                resort="Белек",
                address="Ileribasi Mevkii, Belek, Antalya",
                description="Роскошный курорт на берегу Средиземного моря с собственным "
                           "песчаным пляжем, аквапарком и множеством ресторанов.",
                amenities=[
                    HotelAmenity.SANDY_BEACH,
                    HotelAmenity.AQUAPARK,
                    HotelAmenity.FIRST_LINE,
                    HotelAmenity.KIDS_CLUB,
                    HotelAmenity.SPA,
                    HotelAmenity.POOL,
                    HotelAmenity.ANIMATION,
                    HotelAmenity.WIFI
                ],
                hotel_type=HotelType.FAMILY,
                available_food_types=[FoodType.UAI, FoodType.AI],
                photos=[
                    "https://images.tourvisor.ru/hotels/rixos-belek-1.jpg",
                    "https://images.tourvisor.ru/hotels/rixos-belek-2.jpg"
                ],
                beach_distance=0,
                airport_distance=35
            ),
            2: HotelDetails(
                id=2,
                name="Calista Luxury Resort",
                stars=5,
                rating=9.0,
                country="Турция",
                region="Анталья",
                resort="Белек",
                address="Kadriye Mah., Belek, Antalya",
                description="Пятизвёздочный курорт с концепцией Ultra All Inclusive, "
                           "идеально подходит для семейного отдыха.",
                amenities=[
                    HotelAmenity.SANDY_BEACH,
                    HotelAmenity.AQUAPARK,
                    HotelAmenity.FIRST_LINE,
                    HotelAmenity.KIDS_CLUB,
                    HotelAmenity.SPA,
                    HotelAmenity.HEATED_POOL,
                    HotelAmenity.WATER_SLIDES
                ],
                hotel_type=HotelType.FAMILY,
                available_food_types=[FoodType.UAI],
                photos=["https://images.tourvisor.ru/hotels/calista-1.jpg"],
                beach_distance=0,
                airport_distance=30
            )
        }
        
        return mock_hotels.get(hotel_id, HotelDetails(
            id=hotel_id,
            name=f"Hotel #{hotel_id}",
            stars=4,
            rating=8.0,
            country="Турция",
            region="Анталья",
            resort="Белек",
            amenities=[HotelAmenity.POOL, HotelAmenity.WIFI],
            available_food_types=[FoodType.AI, FoodType.HB]
        ))
    
    def _get_mock_offers_by_country(
        self,
        country: str,
        base_date: date,
        nights: int,
        departure_city: str,
        adults: int
    ) -> list[TourOffer]:
        """Генерация mock-предложений по стране."""
        
        offers = []
        
        if "турц" in country or "turkey" in country:
            offers = self._mock_turkey_offers(base_date, nights, departure_city, adults)
        elif "егип" in country or "egypt" in country:
            offers = self._mock_egypt_offers(base_date, nights, departure_city, adults)
        elif "оаэ" in country or "uae" in country or "эмират" in country:
            offers = self._mock_uae_offers(base_date, nights, departure_city, adults)
        elif "таи" in country or "thai" in country:
            offers = self._mock_thailand_offers(base_date, nights, departure_city, adults)
        else:
            # По умолчанию - Турция
            offers = self._mock_turkey_offers(base_date, nights, departure_city, adults)
        
        return offers
    
    def _mock_turkey_offers(
        self,
        base_date: date,
        nights: int,
        departure_city: str,
        adults: int
    ) -> list[TourOffer]:
        """Mock-туры в Турцию."""
        return [
            TourOffer(
                id=f"tr-{uuid.uuid4().hex[:8]}",
                hotel_name="Rixos Premium Belek",
                hotel_stars=5,
                hotel_rating=9.2,
                hotel_link="https://tourvisor.ru/hotel/rixos-premium-belek",
                hotel_photo="https://images.tourvisor.ru/hotels/rixos-belek.jpg",
                country="Турция",
                region="Анталья",
                resort="Белек",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=125000,
                price_per_person=125000 // adults,
                food_type=FoodType.UAI,
                room_type="Standard Room",
                departure_city=departure_city,
                operator="Anex Tour"
            ),
            TourOffer(
                id=f"tr-{uuid.uuid4().hex[:8]}",
                hotel_name="Calista Luxury Resort",
                hotel_stars=5,
                hotel_rating=9.0,
                hotel_link="https://tourvisor.ru/hotel/calista",
                country="Турция",
                region="Анталья",
                resort="Белек",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=118000,
                price_per_person=118000 // adults,
                food_type=FoodType.UAI,
                room_type="Land View",
                departure_city=departure_city,
                operator="Coral Travel"
            ),
            TourOffer(
                id=f"tr-{uuid.uuid4().hex[:8]}",
                hotel_name="Titanic Mardan Palace",
                hotel_stars=5,
                hotel_rating=9.4,
                country="Турция",
                region="Анталья",
                resort="Лара",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=145000,
                price_per_person=145000 // adults,
                food_type=FoodType.UAI,
                room_type="Deluxe Room",
                departure_city=departure_city,
                operator="Pegas Touristik"
            ),
            TourOffer(
                id=f"tr-{uuid.uuid4().hex[:8]}",
                hotel_name="Club Hotel Turan Prince World",
                hotel_stars=4,
                hotel_rating=8.2,
                country="Турция",
                region="Анталья",
                resort="Сиде",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=78000,
                price_per_person=78000 // adults,
                food_type=FoodType.AI,
                room_type="Standard",
                departure_city=departure_city,
                operator="TUI Russia"
            ),
            TourOffer(
                id=f"tr-{uuid.uuid4().hex[:8]}",
                hotel_name="Orange County Resort Kemer",
                hotel_stars=5,
                hotel_rating=8.6,
                country="Турция",
                region="Анталья",
                resort="Кемер",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=95000,
                price_per_person=95000 // adults,
                food_type=FoodType.UAI,
                room_type="Club Room",
                departure_city=departure_city,
                operator="Anex Tour"
            )
        ]
    
    def _mock_egypt_offers(
        self,
        base_date: date,
        nights: int,
        departure_city: str,
        adults: int
    ) -> list[TourOffer]:
        """Mock-туры в Египет."""
        return [
            TourOffer(
                id=f"eg-{uuid.uuid4().hex[:8]}",
                hotel_name="Rixos Sharm El Sheikh",
                hotel_stars=5,
                hotel_rating=8.9,
                country="Египет",
                region="Красное море",
                resort="Шарм-эль-Шейх",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=95000,
                price_per_person=95000 // adults,
                food_type=FoodType.UAI,
                room_type="Deluxe Room",
                departure_city=departure_city,
                operator="Coral Travel"
            ),
            TourOffer(
                id=f"eg-{uuid.uuid4().hex[:8]}",
                hotel_name="Steigenberger Alcazar",
                hotel_stars=5,
                hotel_rating=8.8,
                country="Египет",
                region="Красное море",
                resort="Шарм-эль-Шейх",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=82000,
                price_per_person=82000 // adults,
                food_type=FoodType.AI,
                room_type="Garden View",
                departure_city=departure_city,
                operator="Pegas Touristik"
            ),
            TourOffer(
                id=f"eg-{uuid.uuid4().hex[:8]}",
                hotel_name="Sunrise Arabian Beach Resort",
                hotel_stars=4,
                hotel_rating=8.4,
                country="Египет",
                region="Красное море",
                resort="Шарм-эль-Шейх",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=65000,
                price_per_person=65000 // adults,
                food_type=FoodType.AI,
                room_type="Standard",
                departure_city=departure_city,
                operator="TUI Russia"
            ),
            TourOffer(
                id=f"eg-{uuid.uuid4().hex[:8]}",
                hotel_name="Jaz Mirabel Beach",
                hotel_stars=5,
                hotel_rating=8.7,
                country="Египет",
                region="Красное море",
                resort="Шарм-эль-Шейх",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=78000,
                price_per_person=78000 // adults,
                food_type=FoodType.AI,
                room_type="Beach View",
                departure_city=departure_city,
                operator="Anex Tour"
            )
        ]
    
    def _mock_uae_offers(
        self,
        base_date: date,
        nights: int,
        departure_city: str,
        adults: int
    ) -> list[TourOffer]:
        """Mock-туры в ОАЭ."""
        return [
            TourOffer(
                id=f"uae-{uuid.uuid4().hex[:8]}",
                hotel_name="Atlantis The Palm",
                hotel_stars=5,
                hotel_rating=9.5,
                country="ОАЭ",
                region="Дубай",
                resort="Пальма Джумейра",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=185000,
                price_per_person=185000 // adults,
                food_type=FoodType.BB,
                room_type="Ocean King",
                departure_city=departure_city,
                operator="TUI Russia"
            ),
            TourOffer(
                id=f"uae-{uuid.uuid4().hex[:8]}",
                hotel_name="Jumeirah Beach Hotel",
                hotel_stars=5,
                hotel_rating=9.1,
                country="ОАЭ",
                region="Дубай",
                resort="Джумейра",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=165000,
                price_per_person=165000 // adults,
                food_type=FoodType.HB,
                room_type="Ocean Deluxe",
                departure_city=departure_city,
                operator="Coral Travel"
            ),
            TourOffer(
                id=f"uae-{uuid.uuid4().hex[:8]}",
                hotel_name="Rixos The Palm Dubai",
                hotel_stars=5,
                hotel_rating=9.0,
                country="ОАЭ",
                region="Дубай",
                resort="Пальма Джумейра",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=195000,
                price_per_person=195000 // adults,
                food_type=FoodType.UAI,
                room_type="Deluxe Room",
                departure_city=departure_city,
                operator="Anex Tour"
            ),
            TourOffer(
                id=f"uae-{uuid.uuid4().hex[:8]}",
                hotel_name="Hilton Dubai Jumeirah",
                hotel_stars=5,
                hotel_rating=8.6,
                country="ОАЭ",
                region="Дубай",
                resort="Джумейра",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=125000,
                price_per_person=125000 // adults,
                food_type=FoodType.BB,
                room_type="King Guest Room",
                departure_city=departure_city,
                operator="Pegas Touristik"
            )
        ]
    
    def _mock_thailand_offers(
        self,
        base_date: date,
        nights: int,
        departure_city: str,
        adults: int
    ) -> list[TourOffer]:
        """Mock-туры в Таиланд."""
        return [
            TourOffer(
                id=f"th-{uuid.uuid4().hex[:8]}",
                hotel_name="Centara Grand Beach Resort Phuket",
                hotel_stars=5,
                hotel_rating=8.9,
                country="Таиланд",
                region="Пхукет",
                resort="Карон",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=145000,
                price_per_person=145000 // adults,
                food_type=FoodType.BB,
                room_type="Deluxe Ocean Facing",
                departure_city=departure_city,
                operator="Coral Travel"
            ),
            TourOffer(
                id=f"th-{uuid.uuid4().hex[:8]}",
                hotel_name="Kata Beach Resort",
                hotel_stars=4,
                hotel_rating=8.2,
                country="Таиланд",
                region="Пхукет",
                resort="Ката",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=98000,
                price_per_person=98000 // adults,
                food_type=FoodType.BB,
                room_type="Superior",
                departure_city=departure_city,
                operator="TUI Russia"
            ),
            TourOffer(
                id=f"th-{uuid.uuid4().hex[:8]}",
                hotel_name="Phuket Marriott Resort",
                hotel_stars=5,
                hotel_rating=9.0,
                country="Таиланд",
                region="Пхукет",
                resort="Май Као",
                date_from=base_date,
                date_to=base_date + timedelta(days=nights),
                nights=nights,
                price=168000,
                price_per_person=168000 // adults,
                food_type=FoodType.HB,
                room_type="Pool Access",
                departure_city=departure_city,
                operator="Anex Tour"
            )
        ]
    
    async def close(self):
        """Закрытие HTTP клиента."""
        if self.client:
            await self.client.aclose()
            self.client = None


# Singleton экземпляр сервиса
tourvisor_service = TourvisorService()

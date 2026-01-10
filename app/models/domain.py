"""
Доменные модели для поиска туров.

Бизнес-логика согласно требованиям МГП:
- Не спрашивать повторно то, что уже понятно из фразы пользователя
- Если указаны даты, автоматически вычислять количество ночей
- Если указан конкретный отель, не запрашивать его звёздность
- Поддержка группы от 1 до 6 взрослых
- Дети: категории 0-2 года (младенцы) и 2-15 лет (дети)
- Иерархия поиска: Страна -> Регион -> Курорт -> Город -> Отель
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class FoodType(str, Enum):
    """Типы питания в отелях."""
    
    RO = "RO"   # Room Only - без питания
    BB = "BB"   # Bed & Breakfast - только завтрак
    HB = "HB"   # Half Board - завтрак и ужин
    FB = "FB"   # Full Board - трёхразовое питание
    AI = "AI"   # All Inclusive - всё включено
    UAI = "UAI" # Ultra All Inclusive - ультра всё включено


class HotelType(str, Enum):
    """Типы отелей по концепции."""
    
    FAMILY = "family"        # Семейный отдых
    VIP = "vip"              # VIP / Премиум
    ACTIVE = "active"        # Активный отдых
    ROMANTIC = "romantic"    # Романтический
    BUDGET = "budget"        # Бюджетный
    BEACH = "beach"          # Пляжный


class HotelAmenity(str, Enum):
    """Услуги и удобства отеля."""
    
    SANDY_BEACH = "sandy_beach"     # Песчаный пляж
    AQUAPARK = "aquapark"           # Аквапарк
    FIRST_LINE = "first_line"       # 1-я линия
    KIDS_CLUB = "kids_club"         # Детский клуб
    SPA = "spa"                     # СПА-центр
    GYM = "gym"                     # Фитнес-зал
    POOL = "pool"                   # Бассейн
    HEATED_POOL = "heated_pool"     # Подогреваемый бассейн
    WIFI = "wifi"                   # Wi-Fi
    ANIMATION = "animation"         # Анимация
    TRANSFER = "transfer"           # Трансфер
    WATER_SLIDES = "water_slides"   # Водные горки
    PRIVATE_BEACH = "private_beach" # Собственный пляж
    ALL_INCLUSIVE = "all_inclusive" # Всё включено 24/7


class Child(BaseModel):
    """
    Модель ребёнка с возрастом.
    
    Категории:
    - 0-2 года: младенцы (infants)
    - 2-15 лет: дети (kids)
    """
    
    age: int = Field(ge=0, le=15, description="Возраст ребёнка (0-15 лет)")
    
    @property
    def is_infant(self) -> bool:
        """Проверка: младенец (0-2 года)."""
        return self.age < 2
    
    @property
    def is_kid(self) -> bool:
        """Проверка: ребёнок (2-15 лет)."""
        return 2 <= self.age <= 15
    
    @property
    def category(self) -> str:
        """Категория ребёнка."""
        return "infant" if self.is_infant else "kid"


class Destination(BaseModel):
    """
    Направление поездки.
    
    Иерархия: Страна -> Регион -> Курорт -> Город
    """
    
    country: str = Field(description="Страна назначения")
    region: Optional[str] = Field(default=None, description="Регион")
    resort: Optional[str] = Field(default=None, description="Курорт")
    city: Optional[str] = Field(default=None, description="Город")


class SearchRequest(BaseModel):
    """
    Запрос на поиск тура.
    
    Реализует бизнес-логику:
    - adults: 1-6 взрослых
    - children: список возрастов с валидацией категорий
    - nights: автоматически вычисляется из дат
    - stars: игнорируется если указан hotel_name
    """
    
    # Туристы
    adults: int = Field(
        ge=1,
        le=6,
        description="Количество взрослых (1-6 человек)"
    )
    children: list[int] = Field(
        default_factory=list,
        description="Возрасты детей (0-15 лет)"
    )
    
    # Направление
    destination: Destination = Field(description="Направление поездки")
    
    # Конкретный отель (опционально)
    hotel_name: Optional[str] = Field(
        default=None,
        description="Название конкретного отеля"
    )
    
    # Категория отеля (игнорируется если указан hotel_name)
    stars: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Категория отеля (1-5 звёзд). Игнорируется если указан hotel_name"
    )
    
    # Даты поездки
    date_from: date = Field(description="Дата начала тура")
    date_to: date = Field(description="Дата окончания тура")
    
    # Количество ночей (автоматически вычисляется из дат)
    nights: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
        description="Количество ночей (вычисляется автоматически из дат)"
    )
    
    # Питание
    food_type: Optional[FoodType] = Field(
        default=None,
        description="Тип питания"
    )
    
    # Город вылета
    departure_city: str = Field(
        default="Москва",
        description="Город вылета"
    )

    @field_validator("children")
    @classmethod
    def validate_children_ages(cls, v: list[int]) -> list[int]:
        """Валидация возрастов детей (0-15 лет)."""
        for age in v:
            if age < 0 or age > 15:
                raise ValueError(f"Возраст ребёнка должен быть 0-15 лет, получено: {age}")
        if len(v) > 4:
            raise ValueError("Максимум 4 ребёнка")
        return v

    @model_validator(mode="after")
    def calculate_nights_and_validate(self) -> "SearchRequest":
        """
        Пост-валидация:
        1. Автоматический расчёт ночей из дат
        2. Игнорирование stars если указан hotel_name
        """
        # Автоматический расчёт количества ночей
        if self.date_from and self.date_to:
            calculated_nights = (self.date_to - self.date_from).days
            if calculated_nights <= 0:
                raise ValueError("date_to должна быть позже date_from")
            # Устанавливаем nights если не указано вручную
            if self.nights is None:
                object.__setattr__(self, "nights", calculated_nights)
        
        # Если указан конкретный отель, игнорируем stars
        if self.hotel_name is not None and self.stars is not None:
            object.__setattr__(self, "stars", None)
        
        return self

    @property
    def infants(self) -> list[int]:
        """Список возрастов младенцев (0-2 года)."""
        return [age for age in self.children if age < 2]
    
    @property
    def kids(self) -> list[int]:
        """Список возрастов детей (2-15 лет)."""
        return [age for age in self.children if 2 <= age <= 15]
    
    @property
    def infants_count(self) -> int:
        """Количество младенцев."""
        return len(self.infants)
    
    @property
    def kids_count(self) -> int:
        """Количество детей 2-15 лет."""
        return len(self.kids)
    
    @property
    def total_tourists(self) -> int:
        """Общее количество туристов."""
        return self.adults + len(self.children)


class TourOffer(BaseModel):
    """
    Карточка предложения тура (выдаётся 3-5 карточек).
    
    Содержит всю информацию для отображения пользователю.
    """
    
    # ID предложения
    id: str = Field(description="Уникальный ID предложения")
    
    # Информация об отеле
    hotel_name: str = Field(description="Название отеля")
    hotel_stars: int = Field(ge=1, le=5, description="Категория отеля (звёзды)")
    hotel_rating: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=10, 
        description="Рейтинг отеля"
    )
    hotel_link: Optional[str] = Field(
        default=None, 
        description="Ссылка на страницу отеля"
    )
    hotel_photo: Optional[str] = Field(
        default=None,
        description="URL фото отеля"
    )
    
    # Локация
    country: str = Field(description="Страна")
    region: Optional[str] = Field(default=None, description="Регион")
    resort: Optional[str] = Field(default=None, description="Курорт")
    
    # Даты и длительность
    date_from: date = Field(description="Дата заезда")
    date_to: date = Field(description="Дата выезда")
    nights: int = Field(ge=1, description="Количество ночей")
    
    # Стоимость
    price: int = Field(gt=0, description="Цена за весь тур (руб)")
    price_per_person: Optional[int] = Field(
        default=None,
        description="Цена за человека (руб)"
    )
    currency: str = Field(default="RUB", description="Валюта")
    
    # Питание и размещение
    food_type: FoodType = Field(description="Тип питания")
    room_type: Optional[str] = Field(
        default=None, 
        description="Тип номера"
    )
    
    # Перелёт
    departure_city: str = Field(description="Город вылета")
    flight_included: bool = Field(default=True, description="Перелёт включён")
    
    # Туроператор
    operator: str = Field(description="Название туроператора")
    
    # Туристы
    adults: int = Field(default=2, ge=1, description="Количество взрослых")
    children: int = Field(default=0, ge=0, description="Количество детей")
    
    # Изображение и ссылка
    image: Optional[str] = Field(default=None, description="URL изображения отеля")
    link: Optional[str] = Field(default=None, description="Ссылка на тур")
    
    @property
    def price_formatted(self) -> str:
        """Форматированная цена."""
        return f"{self.price:,} {self.currency}".replace(",", " ")
    
    @property
    def dates_formatted(self) -> str:
        """Форматированные даты."""
        return f"{self.date_from.strftime('%d.%m')} - {self.date_to.strftime('%d.%m.%Y')}"
    
    @property
    def duration_formatted(self) -> str:
        """Форматированная длительность."""
        nights_word = "ночь" if self.nights == 1 else "ночей" if self.nights >= 5 else "ночи"
        return f"{self.nights} {nights_word}"
    
    @property
    def meal_description(self) -> str:
        """Полное описание типа питания на русском."""
        meal_descriptions = {
            FoodType.RO: "Без питания",
            FoodType.BB: "Только завтрак",
            FoodType.HB: "Завтрак и ужин",
            FoodType.FB: "Полный пансион",
            FoodType.AI: "Всё включено",
            FoodType.UAI: "Ультра всё включено",
        }
        return meal_descriptions.get(self.food_type, self.food_type.value)
    
    @property
    def stars_display(self) -> str:
        """Звёзды для отображения (★★★★★)."""
        return "★" * self.hotel_stars
    
    @property
    def image_url(self) -> str:
        """URL изображения отеля с fallback на placeholder."""
        if self.hotel_photo and self.hotel_photo.startswith("http"):
            return self.hotel_photo
        # Tourvisor может возвращать относительные пути
        if self.hotel_photo:
            return f"https://images.tourvisor.ru{self.hotel_photo}"
        # Генерируем красивый placeholder на основе названия страны
        country_images = {
            "турция": "https://images.unsplash.com/photo-1524231757912-21f4fe3a7200?w=400&h=300&fit=crop",
            "египет": "https://images.unsplash.com/photo-1539768942893-daf53e448371?w=400&h=300&fit=crop",
            "оаэ": "https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=400&h=300&fit=crop",
            "таиланд": "https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?w=400&h=300&fit=crop",
            "мальдивы": "https://images.unsplash.com/photo-1514282401047-d79a71a590e8?w=400&h=300&fit=crop",
        }
        country_lower = self.country.lower()
        for key, url in country_images.items():
            if key in country_lower:
                return url
        # Default placeholder
        return "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&h=300&fit=crop"
    
    def model_dump(self, *args, **kwargs):
        """Переопределяем для включения computed полей."""
        data = super().model_dump(*args, **kwargs)
        # Добавляем computed поля для фронтенда
        data["meal_description"] = self.meal_description
        data["stars_display"] = self.stars_display
        data["image_url"] = self.image_url
        data["price_formatted"] = self.price_formatted
        data["dates_formatted"] = self.dates_formatted
        data["duration_formatted"] = self.duration_formatted
        return data


class TourFilters(BaseModel):
    """
    Фильтры для поиска туров.
    
    Позволяет фильтровать по:
    - Типу питания
    - Услугам отеля
    - Типу отеля (концепция)
    - Звёздности
    - Цене
    """
    
    food_types: Optional[list[FoodType]] = Field(
        default=None,
        description="Типы питания"
    )
    amenities: Optional[list[HotelAmenity]] = Field(
        default=None,
        description="Требуемые услуги отеля"
    )
    hotel_types: Optional[list[HotelType]] = Field(
        default=None,
        description="Типы отелей по концепции"
    )
    min_stars: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Минимальная звёздность"
    )
    max_stars: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Максимальная звёздность"
    )
    min_price: Optional[int] = Field(
        default=None,
        gt=0,
        description="Минимальная цена"
    )
    max_price: Optional[int] = Field(
        default=None,
        gt=0,
        description="Максимальная цена"
    )
    min_rating: Optional[float] = Field(
        default=None,
        ge=0,
        le=10,
        description="Минимальный рейтинг отеля"
    )


class HotelDetails(BaseModel):
    """
    Подробная информация об отеле.
    
    Используется для метода get_hotel_details.
    """
    
    id: int = Field(description="ID отеля в системе Tourvisor")
    name: str = Field(description="Название отеля")
    stars: int = Field(ge=1, le=5, description="Категория (звёзды)")
    rating: Optional[float] = Field(default=None, ge=0, le=10, description="Рейтинг")
    
    # Локация
    country: str = Field(description="Страна")
    region: Optional[str] = Field(default=None, description="Регион")
    resort: Optional[str] = Field(default=None, description="Курорт")
    address: Optional[str] = Field(default=None, description="Адрес")
    
    # Описание
    description: Optional[str] = Field(default=None, description="Описание отеля")
    
    # Услуги и особенности
    amenities: list[HotelAmenity] = Field(
        default_factory=list,
        description="Услуги отеля"
    )
    hotel_type: Optional[HotelType] = Field(
        default=None,
        description="Тип отеля"
    )
    available_food_types: list[FoodType] = Field(
        default_factory=list,
        description="Доступные типы питания"
    )
    
    # Медиа
    photos: list[str] = Field(
        default_factory=list,
        description="URL фотографий"
    )
    
    # Расстояния
    beach_distance: Optional[int] = Field(
        default=None,
        description="Расстояние до пляжа (метры)"
    )
    airport_distance: Optional[int] = Field(
        default=None,
        description="Расстояние до аэропорта (км)"
    )


class SearchResponse(BaseModel):
    """Ответ на поиск туров."""
    
    offers: list[TourOffer] = Field(
        default_factory=list,
        max_length=5,
        description="Список предложений (3-5 карточек)"
    )
    total_found: int = Field(
        default=0,
        description="Всего найдено предложений"
    )
    search_id: Optional[str] = Field(
        default=None,
        description="ID поиска для пагинации"
    )
    
    # Структурированный ответ при отсутствии результатов
    found: bool = Field(
        default=True,
        description="Найдены ли туры"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Причина отсутствия: no_flights, no_season, filters_too_strict"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Рекомендация: try_changing_dates, try_moscow_departure"
    )

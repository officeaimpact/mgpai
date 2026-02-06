"""
Yandex GPT Function Calling Handler (Responses API)
Связывает AI модель с TourVisor API
Миграция на Responses API с встроенным web_search
+ Поддержка Streaming и асинхронности
"""

import os
import json
import asyncio
import time
from typing import Optional, Dict, Any, List, Callable, AsyncIterator
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from tourvisor_client import (
    TourVisorClient,
    TourIdExpiredError,
    SearchNotFoundError,
    NoResultsError
)

load_dotenv()


# Тип для callback функции streaming
StreamCallback = Callable[[str], None]


class YandexGPTHandler:
    """Обработчик запросов к Yandex GPT с Function Calling (Responses API)"""
    
    def __init__(self):
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.model = os.getenv("YANDEX_MODEL", "yandexgpt")
        
        # OpenAI-совместимый клиент для Responses API
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://ai.api.cloud.yandex.net/v1",
            project=self.folder_id
        )
        
        self.model_uri = f"gpt://{self.folder_id}/{self.model}"
        
        self.tourvisor = TourVisorClient()
        self.tools = self._load_tools()
        
        # История сообщений для контекста (новый формат)
        self.input_list: List[Dict] = []
        
        # ID последнего ответа для контекста
        self.previous_response_id: Optional[str] = None
        
        # Системный промпт (теперь это instructions)
        self.instructions = self._load_system_prompt()
    
    def _load_tools(self) -> List[Dict]:
        """Загрузить описания функций из function_schemas.json"""
        schema_path = os.path.join(os.path.dirname(__file__), "..", "function_schemas.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Загружаем custom functions
        custom_tools = data.get("tools", [])
        
        # Добавляем встроенный web_search инструмент
        web_search_tool = {
            "type": "web_search",
            "search_context_size": "medium"  # low | medium | high
        }
        
        return custom_tools + [web_search_tool]
    
    def _load_system_prompt(self) -> str:
        """Загрузить системный промпт (теперь это instructions)"""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "system_prompt.md")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "Ты — AI-менеджер турагентства. Помогаешь клиентам найти и забронировать туры."
    
    async def _execute_function(self, name: str, arguments: str, call_id: str) -> Dict:
        """Выполнить функцию и вернуть результат в новом формате"""
        print(f"\n🔧 Вызов функции: {name}")
        
        try:
            # Парсим аргументы
            args = json.loads(arguments) if arguments else {}
            print(f"   Аргументы: {json.dumps(args, ensure_ascii=False, indent=2)}")
            
            result = await self._dispatch_function(name, args)
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            print(f"   ✅ Результат: {result_str[:500]}...")
            
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result_str
            }
        except (TourIdExpiredError, SearchNotFoundError, NoResultsError) as e:
            error_msg = f"Ошибка: {str(e)}"
            print(f"   ⚠️ {error_msg}")
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps({"error": error_msg}, ensure_ascii=False)
            }
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {str(e)}"
            print(f"   ❌ {error_msg}")
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps({"error": error_msg}, ensure_ascii=False)
            }
    
    async def _dispatch_function(self, name: str, args: Dict) -> Any:
        """Маршрутизация вызовов функций к TourVisor клиенту"""
        
        if name == "get_current_date":
            from datetime import datetime
            now = datetime.now()
            return {
                "date": now.strftime("%d.%m.%Y"),
                "time": now.strftime("%H:%M"),
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "weekday": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][now.weekday()],
                "hint": "Используй эту дату для datefrom/dateto. Формат: ДД.ММ.ГГГГ"
            }
        
        elif name == "search_tours":
            request_id = await self.tourvisor.search_tours(
                departure=args.get("departure"),
                country=args.get("country"),
                date_from=args.get("datefrom"),
                date_to=args.get("dateto"),
                nights_from=args.get("nightsfrom", 7),
                nights_to=args.get("nightsto", 10),
                adults=args.get("adults", 2),
                children=args.get("child", 0),
                child_ages=[args.get(f"childage{i}") for i in [1,2,3] if args.get(f"childage{i}")],
                stars=args.get("stars"),
                meal=args.get("meal"),
                rating=args.get("rating"),
                hotels=args.get("hotels"),
                regions=args.get("regions"),
                subregions=args.get("subregions"),
                operators=args.get("operators"),
                price_from=args.get("pricefrom"),
                price_to=args.get("priceto"),
                hotel_types=args.get("hoteltypes"),
                services=args.get("services"),
                tourid=args.get("tourid"),
                onrequest=args.get("onrequest"),
                directflight=args.get("directflight"),
                flightclass=args.get("flightclass"),
                currency=args.get("currency"),
                pricetype=args.get("pricetype"),
                starsbetter=args.get("starsbetter"),
                mealbetter=args.get("mealbetter"),
                hideregular=args.get("hideregular")
            )
            
            # Проверка на ошибку (прошлые даты и т.п.)
            if request_id is None:
                return {
                    "error": "Не удалось создать поиск. Проверьте даты — они должны быть в будущем (2026 год или позже).",
                    "hint": "Используйте формат ДД.ММ.ГГГГ, например 01.03.2026"
                }
            
            return {"requestid": str(request_id), "message": "Поиск запущен. ОБЯЗАТЕЛЬНО вызови get_search_status с этим requestid, затем get_search_results."}
        
        elif name == "get_search_status":
            return await self.tourvisor.get_search_status(args["requestid"])
        
        elif name == "get_search_results":
            full_results = await self.tourvisor.get_search_results(
                request_id=args["requestid"],
                page=args.get("page", 1),
                per_page=args.get("onpage", 10),  # Ограничиваем до 10 отелей
                include_operators=args.get("operatorstatus") == 1,
                no_description=args.get("nodescription") == 1
            )
            
            # Сокращаем результаты для AI — формат карточек с картинками
            hotels = full_results.get("result", {}).get("hotel", [])
            simplified = []
            for h in hotels[:5]:  # Максимум 5 отелей для AI
                tours = h.get("tours", {}).get("tour", [])
                best_tour = tours[0] if tours else {}
                
                # Проверяем картинку — не показываем заглушки регионов
                picture = h.get("picturelink", "")
                has_real_photo = h.get("isphoto") == 1 and picture and "/reg-" not in picture
                
                simplified.append({
                    "hotelcode": h.get("hotelcode"),
                    "hotelname": h.get("hotelname"),
                    "hotelstars": h.get("hotelstars"),
                    "hotelrating": h.get("hotelrating"),
                    "regionname": h.get("regionname"),
                    "countryname": h.get("countryname"),
                    "price": h.get("price"),
                    "seadistance": h.get("seadistance"),
                    "picturelink": picture if has_real_photo else None,  # Только реальные фото
                    "hoteldescription": h.get("hoteldescription"),  # Описание
                    "fulldesclink": h.get("fulldesclink"),  # Ссылка на подробности
                    "tour": {
                        "tourid": best_tour.get("tourid"),
                        "price": best_tour.get("price"),  # Цена конкретного тура
                        "flydate": best_tour.get("flydate"),
                        "nights": best_tour.get("nights"),
                        "meal": best_tour.get("mealrussian"),
                        "room": best_tour.get("room"),
                        "placement": best_tour.get("placement"),
                        "operatorname": best_tour.get("operatorname"),
                        "tourname": best_tour.get("tourname"),  # Название тура
                        # ⚠️ Важные статусы для предупреждений клиенту:
                        "promo": best_tour.get("promo"),
                        "regular": best_tour.get("regular"),
                        "onrequest": best_tour.get("onrequest"),
                        "flightstatus": best_tour.get("flightstatus"),
                        "hotelstatus": best_tour.get("hotelstatus"),
                        "nightflight": best_tour.get("nightflight")
                    } if best_tour else None
                })
            
            status = full_results.get("status", {})
            return {
                "hotels_found": status.get("hotelsfound", len(hotels)),
                "tours_found": status.get("toursfound", 0),
                "min_price": status.get("minprice", 0),
                "hotels": simplified
            }
        
        elif name == "get_dictionaries":
            # Определяем какой справочник запрашивается
            dict_type = args.get("type", "")
            
            if "departure" in dict_type:
                return await self.tourvisor.get_departures()
            elif "country" in dict_type:
                return await self.tourvisor.get_countries(args.get("cndep"))
            elif "subregion" in dict_type:
                return await self.tourvisor.get_subregions(args.get("regcountry"))
            elif "region" in dict_type:
                return await self.tourvisor.get_regions(args.get("regcountry"))
            elif "meal" in dict_type:
                return await self.tourvisor.get_meals()
            elif "stars" in dict_type:
                return await self.tourvisor.get_stars()
            elif "operator" in dict_type:
                return await self.tourvisor.get_operators(
                    args.get("flydeparture"),
                    args.get("flycountry")
                )
            elif "services" in dict_type:
                return await self.tourvisor.get_services()
            elif "flydate" in dict_type:
                return await self.tourvisor.get_flydates(
                    args.get("flydeparture"),
                    args.get("flycountry")
                )
            elif "hotel" in dict_type:
                # Собираем типы отелей
                hotel_types = []
                for ht in ["active", "relax", "family", "health", "city", "beach", "deluxe"]:
                    if args.get(f"hot{ht}") == 1:
                        hotel_types.append(ht)
                
                hotels = await self.tourvisor.get_hotels(
                    country_id=args.get("hotcountry"),
                    region_id=args.get("hotregion"),
                    stars=args.get("hotstars"),
                    rating=args.get("hotrating"),
                    hotel_types=hotel_types if hotel_types else None
                )
                # Фильтруем по названию если указано
                name_filter = args.get("name", "").lower()
                if name_filter:
                    hotels = [h for h in hotels if name_filter in h.get("name", "").lower()]
                return hotels[:20]  # Максимум 20 отелей
            elif "currency" in dict_type:
                # Курсы валют туроператоров
                return await self.tourvisor.get_currencies()
            else:
                return {"error": f"Неизвестный тип справочника: {dict_type}"}
        
        elif name == "actualize_tour":
            return await self.tourvisor.actualize_tour(
                tour_id=args["tourid"],
                request_mode=args.get("request", 2),
                currency=args.get("currency", 0)
            )
        
        elif name == "get_tour_details":
            return await self.tourvisor.get_tour_details(
                tour_id=args["tourid"],
                currency=args.get("currency", 0)
            )
        
        elif name == "get_hotel_info":
            hotel = await self.tourvisor.get_hotel_info(
                hotel_code=args["hotelcode"],
                big_images=True,  # Всегда большие картинки
                remove_tags=True,  # Без HTML тегов
                include_reviews=args.get("reviews") == 1
            )
            
            # Форматируем для карточки с полным описанием
            images = hotel.get("images", {})
            if isinstance(images, dict):
                images = images.get("image", [])
            if isinstance(images, str):
                images = [images]
            
            reviews = hotel.get("reviews", {})
            if isinstance(reviews, dict):
                reviews = reviews.get("review", [])
            
            return {
                "name": hotel.get("name"),
                "stars": hotel.get("stars"),
                "rating": hotel.get("rating"),
                "country": hotel.get("country"),
                "region": hotel.get("region"),
                "placement": hotel.get("placement"),
                "seadistance": hotel.get("seadistance"),
                "build": hotel.get("build"),
                "description": hotel.get("description"),
                "territory": hotel.get("territory"),
                "inroom": hotel.get("inroom"),
                "roomtypes": hotel.get("roomtypes"),
                "beach": hotel.get("beach"),
                "child": hotel.get("child"),
                "services": hotel.get("services"),
                "servicefree": hotel.get("servicefree"),
                "servicepay": hotel.get("servicepay"),
                "meallist": hotel.get("meallist"),
                "mealtypes": hotel.get("mealtypes"),
                "animation": hotel.get("animation"),
                "images": images[:5] if images else [],  # Первые 5 фото
                "images_count": hotel.get("imagescount"),
                "coordinates": {
                    "lat": hotel.get("coord1"),
                    "lon": hotel.get("coord2")
                },
                "reviews": [
                    {
                        "name": r.get("name"),
                        "rate": r.get("rate"),
                        "content": r.get("content", "")[:300] + "..." if len(r.get("content", "")) > 300 else r.get("content", ""),
                        "traveltime": r.get("traveltime"),
                        "sourcelink": r.get("sourcelink", "")  # ВАЖНО для указания источника!
                    } for r in (reviews[:3] if reviews else [])
                ] if args.get("reviews") == 1 else []
            }
        
        elif name == "get_hot_tours":
            tours = await self.tourvisor.get_hot_tours(
                city=args["city"],
                count=args.get("items", 10),
                city2=args.get("city2"),
                city3=args.get("city3"),
                uniq2=args.get("uniq2"),
                uniq3=args.get("uniq3"),
                countries=args.get("countries"),
                regions=args.get("regions"),
                operators=args.get("operators"),
                datefrom=args.get("datefrom"),
                dateto=args.get("dateto"),
                stars=args.get("stars"),
                meal=args.get("meal"),
                rating=args.get("rating"),
                max_days=args.get("maxdays"),
                tour_type=args.get("tourtype", 0),
                visa_free=args.get("visa") == 1,
                sort_by_price=args.get("sort") == 1,
                picturetype=args.get("picturetype", 0),
                currency=args.get("currency", 0)
            )
            
            # Сокращаем результаты для AI — формат карточек с картинками
            simplified = []
            for t in tours[:7]:  # Максимум 7 горящих туров
                # Вычисляем скидку
                price = int(t.get("price", 0))
                price_old = int(t.get("priceold", 0))
                discount = round((price_old - price) / price_old * 100) if price_old > 0 else 0
                
                # Проверяем картинку — не показываем заглушки
                picture = t.get("hotelpicture", "")
                has_real_photo = picture and "/reg-" not in picture
                
                simplified.append({
                    "hotelcode": t.get("hotelcode"),
                    "hotelname": t.get("hotelname"),
                    "hotelstars": t.get("hotelstars"),
                    "hotelrating": t.get("hotelrating"),
                    "countryname": t.get("countryname"),
                    "regionname": t.get("hotelregionname"),
                    "departurename": t.get("departurename"),  # Город вылета
                    "departurenamefrom": t.get("departurenamefrom"),  # "из Москвы"
                    "operatorname": t.get("operatorname"),  # Туроператор
                    "price_per_person": price,
                    "price_old": price_old,
                    "discount_percent": discount,
                    "currency": t.get("currency", "RUB"),  # Валюта
                    "flydate": t.get("flydate"),
                    "nights": t.get("nights"),
                    "meal": t.get("meal"),
                    "tourid": t.get("tourid"),
                    "picturelink": picture if has_real_photo else None,  # Только реальные фото
                    "fulldesclink": t.get("fulldesclink")  # Ссылка
                })
            
            return {
                "total_found": len(tours),
                "note": "ВАЖНО: Цены указаны ЗА ЧЕЛОВЕКА! Для двоих умножай на 2.",
                "tours": simplified
            }
        
        elif name == "continue_search":
            # Вызываем search.php?continue=requestid
            request_id = args["requestid"]
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "authlogin": self.tourvisor.auth_login,
                    "authpass": self.tourvisor.auth_pass,
                    "format": "json",
                    "continue": request_id
                }
                response = await client.get(f"{self.tourvisor.base_url}/search.php", params=params)
                data = response.json()
                
                page = data.get("result", {}).get("page", "2")
                return {
                    "page": page,
                    "message": f"Продолжение поиска запущено (страница {page}). Подождите 5-7 секунд и запросите результаты."
                }
        
        else:
            return {"error": f"Неизвестная функция: {name}"}
    
    def _call_api_sync(self, stream: bool = False):
        """
        Синхронный вызов Responses API.
        Используется через asyncio.to_thread() для неблокирующего выполнения.
        """
        return self.client.responses.create(
            model=self.model_uri,
            input=self.input_list,
            instructions=self.instructions,
            tools=self.tools,
            temperature=0.3,
            max_output_tokens=2000,
            previous_response_id=self.previous_response_id,
            stream=stream
        )
    
    async def _call_api(self, stream: bool = False):
        """
        Асинхронный вызов API через to_thread().
        Не блокирует event loop!
        """
        return await asyncio.to_thread(self._call_api_sync, stream)
    
    async def chat(self, user_message: str) -> str:
        """
        Отправить сообщение и получить ответ.
        Обрабатывает Function Calling автоматически (Responses API).
        Асинхронный — не блокирует event loop.
        """
        # Добавляем сообщение пользователя в новом формате
        self.input_list.append({
            "role": "user",
            "content": user_message
        })
        
        print(f"\n👤 Пользователь: {user_message}")
        
        # Цикл Function Calling
        max_iterations = 15
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Итерация {iteration} ---")
            
            try:
                # Асинхронный вызов API (не блокирует event loop!)
                response = await self._call_api(stream=False)
                
                # Сохраняем ID для контекста
                self.previous_response_id = response.id
                
            except Exception as e:
                error_str = str(e)
                
                # 403 Forbidden — content moderation или проблема с правами
                if "403" in error_str or "Forbidden" in error_str:
                    print(f"   [WARN] 403 Forbidden - возможно content moderation")
                    self.previous_response_id = None
                    graceful_response = "Извините, я не могу обсуждать эту тему. Давайте поговорим о турах и путешествиях! Куда бы вы хотели поехать?"
                    self.input_list.append({"role": "assistant", "content": graceful_response})
                    return graceful_response
                
                # 429 Too Many Requests
                if "429" in error_str or "Too Many" in error_str:
                    print(f"   [WARN] 429 Rate limiting")
                    return "Сервис временно перегружен. Пожалуйста, подождите несколько секунд и повторите запрос."
                
                # Если предыдущий response был failed — сбрасываем и пробуем снова
                if "status failed" in error_str and self.previous_response_id:
                    print(f"   [WARN] Previous response failed, resetting context...")
                    self.previous_response_id = None
                    try:
                        response = await self._call_api(stream=False)
                        self.previous_response_id = response.id
                    except Exception as retry_e:
                        error_retry_str = str(retry_e)
                        if "403" in error_retry_str or "Forbidden" in error_retry_str:
                            return "Извините, я не могу обсуждать эту тему. Чем ещё могу помочь с планированием путешествия?"
                        print(f"❌ API Error (retry): {retry_e}")
                        return "Произошла временная ошибка. Пожалуйста, попробуйте ещё раз."
                else:
                    print(f"❌ API Error: {e}")
                    self.previous_response_id = None
                    return "Произошла временная ошибка связи. Пожалуйста, попробуйте ещё раз или начните новый чат."
            
            # Проверяем есть ли function calls в output
            has_function_calls = False
            function_results = []
            
            for item in response.output:
                # Проверяем тип элемента
                item_type = getattr(item, 'type', None)
                
                if item_type == "function_call":
                    has_function_calls = True
                    
                    # Получаем данные function call
                    func_name = getattr(item, 'name', '')
                    func_args = getattr(item, 'arguments', '{}')
                    call_id = getattr(item, 'call_id', func_name)
                    
                    # Выполняем функцию
                    result = await self._execute_function(func_name, func_args, call_id)
                    function_results.append(result)
            
            if has_function_calls:
                # Добавляем output модели в историю
                self.input_list.extend(response.output)
                
                # Добавляем результаты функций
                self.input_list.extend(function_results)
            else:
                # Финальный текстовый ответ
                final_text = getattr(response, 'output_text', '')
                
                if not final_text:
                    # Пробуем извлечь текст из output
                    for item in response.output:
                        item_type = getattr(item, 'type', None)
                        if item_type == "message":
                            content = getattr(item, 'content', [])
                            for c in content:
                                if getattr(c, 'type', None) == "output_text":
                                    final_text = getattr(c, 'text', '')
                                    break
                
                # Добавляем ответ в историю
                self.input_list.append({
                    "role": "assistant",
                    "content": final_text
                })
                
                print(f"\n🤖 Ассистент: {final_text}")
                return final_text
        
        return "Ошибка: превышено количество итераций Function Calling"
    
    async def chat_stream(
        self, 
        user_message: str, 
        on_token: Optional[StreamCallback] = None
    ) -> str:
        """
        Отправить сообщение и получить ответ со STREAMING.
        Текст появляется по частям — как в ChatGPT.
        
        Args:
            user_message: Сообщение пользователя
            on_token: Callback функция, вызывается при получении каждого токена.
                      Пример: on_token=lambda text: print(text, end="", flush=True)
        
        Returns:
            Полный текст ответа
        
        Пример использования:
            # Простой вывод в консоль
            response = await handler.chat_stream(
                "Привет!",
                on_token=lambda t: print(t, end="", flush=True)
            )
            
            # Для веб-приложения (WebSocket/SSE)
            async def send_to_client(text):
                await websocket.send(text)
            
            response = await handler.chat_stream("Привет!", on_token=send_to_client)
        """
        # Добавляем сообщение пользователя
        self.input_list.append({
            "role": "user",
            "content": user_message
        })
        
        print(f"\n👤 Пользователь: {user_message}")
        
        # Сбрасываем счётчик пустых итераций
        self._empty_iterations = 0
        
        # Цикл Function Calling со streaming
        max_iterations = 15
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Итерация {iteration} (streaming) ---")
            
            try:
                # Вызываем API со streaming
                # Для streaming используем синхронный вызов в потоке
                stream_response = await asyncio.to_thread(
                    lambda: self.client.responses.create(
                        model=self.model_uri,
                        input=self.input_list,
                        instructions=self.instructions,
                        tools=self.tools,
                        temperature=0.3,
                        max_output_tokens=2000,
                        previous_response_id=self.previous_response_id,
                        stream=True
                    )
                )
                
            except Exception as e:
                error_str = str(e)
                
                # 403 Forbidden — content moderation или проблема с правами
                # Возвращаем вежливый ответ вместо ошибки
                if "403" in error_str or "Forbidden" in error_str:
                    print(f"   [WARN] 403 Forbidden - возможно content moderation")
                    self.previous_response_id = None  # Сброс контекста
                    graceful_response = "Извините, я не могу обсуждать эту тему. Давайте поговорим о турах и путешествиях! Куда бы вы хотели поехать?"
                    self.input_list.append({
                        "role": "assistant",
                        "content": graceful_response
                    })
                    return graceful_response
                
                # 429 Too Many Requests — rate limiting
                if "429" in error_str or "Too Many" in error_str:
                    print(f"   [WARN] 429 Rate limiting")
                    graceful_response = "Сервис временно перегружен. Пожалуйста, подождите несколько секунд и повторите запрос."
                    return graceful_response
                
                # Если response ещё in_progress — подождать и попробовать снова
                if "in_progress" in error_str:
                    print(f"   [WARN] Previous response still in_progress, waiting...")
                    time.sleep(2)  # Ждём завершения
                    continue  # Повторяем итерацию
                
                # Если предыдущий response был failed — сбрасываем и пробуем снова
                if "status failed" in error_str and self.previous_response_id:
                    print(f"   [WARN] Previous response failed, resetting context...")
                    self.previous_response_id = None
                    # Пробуем снова без previous_response_id
                    try:
                        stream_response = await asyncio.to_thread(
                            lambda: self.client.responses.create(
                                model=self.model_uri,
                                input=self.input_list,
                                instructions=self.instructions,
                                tools=self.tools,
                                temperature=0.3,
                                max_output_tokens=2000,
                                previous_response_id=None,
                                stream=True
                            )
                        )
                    except Exception as retry_e:
                        error_retry_str = str(retry_e)
                        # Graceful handling для retry ошибок тоже
                        if "403" in error_retry_str or "Forbidden" in error_retry_str:
                            print(f"   [WARN] 403 on retry - content moderation")
                            return "Извините, я не могу обсуждать эту тему. Чем ещё могу помочь с планированием путешествия?"
                        print(f"❌ API Error (retry): {retry_e}")
                        return "Произошла временная ошибка. Пожалуйста, попробуйте ещё раз."
                else:
                    print(f"❌ API Error: {e}")
                    # Graceful fallback для любых других ошибок
                    self.previous_response_id = None
                    return "Произошла временная ошибка связи. Пожалуйста, попробуйте ещё раз или начните новый чат."
            
            # Обрабатываем streaming ответ
            full_text = ""
            has_function_calls = False
            function_calls_data = []
            output_items = []  # Собираем все output items
            response_id = None
            
            # Итерируем по событиям streaming
            for event in stream_response:
                event_type = getattr(event, 'type', None)
                
                # Сохраняем response_id
                if hasattr(event, 'response') and event.response:
                    response_id = getattr(event.response, 'id', None)
                
                # Текстовый контент (delta)
                if event_type == "response.output_text.delta":
                    delta_text = getattr(event, 'delta', '')
                    if delta_text:
                        full_text += delta_text
                        # Вызываем callback для каждого токена
                        if on_token:
                            on_token(delta_text)
                
                # Output item - собираем все items (function_call, message, web_search, etc)
                elif event_type == "response.output_item.done":
                    event_data = event.model_dump() if hasattr(event, 'model_dump') else {}
                    item = event_data.get('item', {})
                    item_type = item.get('type', '')
                    
                    # Сохраняем item для истории
                    output_items.append(item)
                    
                    if item_type == 'function_call':
                        has_function_calls = True
                        function_calls_data.append({
                            "name": item.get('name', ''),
                            "arguments": item.get('arguments', '{}'),
                            "call_id": item.get('call_id', item.get('id', ''))
                        })
                    elif item_type in ('web_search_call', 'web_search_result'):
                        # web_search обрабатывается автоматически — продолжаем цикл
                        print(f"   [DEBUG] web_search: {item_type}")
                
                # Завершение ответа
                elif event_type == "response.done":
                    if hasattr(event, 'response'):
                        response_id = getattr(event.response, 'id', None)
            
            # Сохраняем ID для контекста
            if response_id:
                self.previous_response_id = response_id
            
            # DEBUG
            print(f"   [DEBUG] has_function_calls={has_function_calls}, full_text={len(full_text)} chars, output_items={len(output_items)}")
            
            if has_function_calls:
                # Сбрасываем счётчик пустых итераций
                self._empty_iterations = 0
                
                # Добавляем output модели в историю (включая function_call)
                self.input_list.extend(output_items)
                
                # Выполняем функции
                function_results = []
                for fc in function_calls_data:
                    result = await self._execute_function(
                        fc["name"], 
                        fc["arguments"], 
                        fc["call_id"]
                    )
                    function_results.append(result)
                
                # Добавляем результаты функций
                self.input_list.extend(function_results)
            elif full_text:
                # Сбрасываем счётчик
                self._empty_iterations = 0
                
                # Есть текстовый ответ — финал
                # Также добавляем output_items если они есть (например message item)
                if output_items:
                    self.input_list.extend(output_items)
                else:
                    self.input_list.append({
                        "role": "assistant",
                        "content": full_text
                    })
                
                print(f"\n🤖 Ассистент (streaming): {full_text[:100]}...")
                return full_text
            elif output_items:
                # Есть output_items (web_search, etc) но нет текста — продолжаем цикл
                # НО! Проверяем, есть ли в items текстовое сообщение
                has_text_message = any(
                    item.get('type') == 'message' and item.get('content')
                    for item in output_items
                )
                
                if has_text_message:
                    # Извлекаем текст из message item
                    for item in output_items:
                        if item.get('type') == 'message':
                            content = item.get('content', [])
                            if isinstance(content, list):
                                for c in content:
                                    if c.get('type') == 'output_text':
                                        text = c.get('text', '')
                                        if text:
                                            self._empty_iterations = 0
                                            self.input_list.extend(output_items)
                                            print(f"\n🤖 Ассистент (streaming): {text[:100]}...")
                                            return text
                
                # Нет текста — проверяем что это за items
                # web_search_call НЕ добавляем в историю — это внутренний вызов API
                has_web_search_call = any(
                    item.get('type') == 'web_search_call' 
                    for item in output_items
                )
                
                if has_web_search_call:
                    # web_search в процессе — просто ждём, НЕ добавляем в историю
                    # и НЕ сбрасываем previous_response_id
                    print(f"   [DEBUG] web_search в процессе, ждём результат...")
                    time.sleep(1)  # Даём время на выполнение web_search
                else:
                    # Другие items (не web_search) — добавляем в историю
                    self._empty_iterations = 0
                    self.input_list.extend(output_items)
                    print(f"   [DEBUG] Добавлено {len(output_items)} output_items в историю, продолжаем...")
            else:
                # Совсем пустой ответ — AI "думает" или проблема
                # Считаем пустые итерации подряд
                if not hasattr(self, '_empty_iterations'):
                    self._empty_iterations = 0
                self._empty_iterations += 1
                
                print(f"   [DEBUG] Пустой ответ #{self._empty_iterations}, продолжаем цикл...")
                
                # После 3 пустых итераций подряд — выходим
                if self._empty_iterations >= 3:
                    print(f"\n🤖 Ассистент (streaming): (пустой ответ после {self._empty_iterations} попыток)...")
                    self._empty_iterations = 0
                    return "(Не удалось получить ответ. Попробуйте переформулировать вопрос.)"
        
        return "Ошибка: превышено количество итераций Function Calling"
    
    async def chat_stream_generator(self, user_message: str) -> AsyncIterator[str]:
        """
        Генератор для streaming ответа.
        Удобен для использования с async for.
        
        Пример:
            async for token in handler.chat_stream_generator("Привет!"):
                print(token, end="", flush=True)
        """
        # Очередь для передачи токенов из callback в генератор
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        full_response = ""
        
        async def token_callback(token: str):
            await queue.put(token)
        
        # Запускаем chat_stream в фоне
        async def run_chat():
            nonlocal full_response
            try:
                # Для streaming используем синхронный callback
                # так как on_token не async
                tokens = []
                
                def sync_callback(token: str):
                    tokens.append(token)
                    # Синхронно добавляем в очередь через call_soon_threadsafe
                    asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: queue.put_nowait(token)
                    )
                
                full_response = await self.chat_stream(user_message, on_token=sync_callback)
            finally:
                await queue.put(None)  # Сигнал завершения
        
        # Запускаем задачу
        task = asyncio.create_task(run_chat())
        
        # Читаем токены из очереди
        while True:
            token = await queue.get()
            if token is None:
                break
            yield token
        
        # Ждём завершения задачи
        await task
    
    async def close(self):
        """Закрыть соединения"""
        await self.tourvisor.close()
    
    def reset(self):
        """Сбросить историю диалога"""
        self.input_list = []
        self.previous_response_id = None


# ==================== ТЕСТ ====================

async def test_scenario_1():
    """Сценарий 1: Простой поиск тура (ГОТОВО)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 1: Простой поиск тура")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Привет! Хотим с женой слетать в Турцию в марте, бюджет около 150 тысяч рублей. Вылет из Москвы."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_2():
    """Сценарий 2: Горящие туры (ГОТОВО)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 2: Горящие туры")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Покажи горящие туры из Москвы, желательно на море, 4-5 звёзд"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_3():
    """Сценарий 3: Поиск с детьми + фильтры (питание, услуги)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 3: Поиск с детьми + фильтры")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хотим в Турцию из Москвы в марте, семья с ребёнком 5 лет. "
            "Обязательно всё включено, 4-5 звёзд. Бюджет до 200 тысяч."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_4():
    """Сценарий 4: Справочники (города, страны)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 4: Справочники")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Я из Казани. Куда можно полететь на море в марте? Какие страны доступны?"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_5():
    """Сценарий 5: Подробная информация об отеле"""
    print("=" * 60)
    print("СЦЕНАРИЙ 5: Информация об отеле")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        # Сначала поиск
        print("\n--- Поиск туров ---")
        await handler.chat("Найди туры в Турцию из Москвы в марте до 100 тысяч")
        
        # Потом подробности
        print("\n--- Запрос деталей ---")
        response = await handler.chat(
            "Расскажи подробнее про первый отель — что там есть, какой пляж, для детей"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_6():
    """Сценарий 6: Актуализация цены и детали рейса"""
    print("=" * 60)
    print("СЦЕНАРИЙ 6: Актуализация + детали рейса")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        # Сначала поиск
        print("\n--- Поиск туров ---")
        await handler.chat("Найди туры в Турцию из Москвы в марте до 100 тысяч")
        
        # Потом актуализация
        print("\n--- Запрос точной цены ---")
        response = await handler.chat(
            "Мне интересен первый вариант. Какая точная цена сейчас и какой рейс?"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_7():
    """Сценарий 7: Продолжение поиска (ещё варианты)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 7: Продолжение поиска")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        # Сначала поиск
        print("\n--- Первый поиск ---")
        await handler.chat("Туры в Турцию из Москвы в марте до 150 тысяч")
        
        # Потом ещё
        print("\n--- Запрос ещё вариантов ---")
        response = await handler.chat("Покажи ещё варианты")
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_8():
    """Сценарий 8: Веб-поиск (визы, погода) — теперь работает!"""
    print("=" * 60)
    print("СЦЕНАРИЙ 8: Вопросы про визы/погоду (web_search)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Нужна ли виза в Египет для россиян? И какая погода там в феврале?"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_9():
    """Сценарий 9: Поиск без результатов"""
    print("=" * 60)
    print("СЦЕНАРИЙ 9: Пустой результат поиска")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди тур на Мальдивы из Москвы на завтра, бюджет 50 тысяч, 5 звёзд, UAI"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_10():
    """Сценарий 10: Полный диалог — от поиска до бронирования"""
    print("=" * 60)
    print("СЦЕНАРИЙ 10: Полный диалог")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        print("\n--- Шаг 1: Начало диалога ---")
        await handler.chat("Привет! Хотим отдохнуть в Турции в марте, двое взрослых.")
        
        print("\n--- Шаг 2: Уточнение ---")
        await handler.chat("Бюджет около 100 тысяч, вылет из Москвы, 7-10 ночей, хотелось бы всё включено")
        
        print("\n--- Шаг 3: Выбор отеля ---")
        await handler.chat("Расскажи подробнее про второй вариант")
        
        print("\n--- Шаг 4: Бронирование ---")
        response = await handler.chat("Хотим забронировать этот тур. Какая точная цена?")
        
        print("\n✅ ФИНАЛЬНЫЙ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


# ==================== НОВЫЕ ТЕСТЫ ДЛЯ ДОПОЛНИТЕЛЬНЫХ ПАРАМЕТРОВ ====================

async def test_scenario_11():
    """Сценарий 11: Тип отеля (hoteltypes) — только пляжные семейные"""
    print("=" * 60)
    print("СЦЕНАРИЙ 11: Фильтр по типу отеля (beach, family)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди семейный пляжный отель в Турции из Москвы в марте. "
            "Важно чтобы отель был ориентирован на семьи с детьми и на пляже."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_12():
    """Сценарий 12: Прямые рейсы (directflight)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 12: Только прямые рейсы")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хочу в Турцию из Москвы в марте, но обязательно прямой рейс без пересадок!"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_13():
    """Сценарий 13: Фильтр по оператору"""
    print("=" * 60)
    print("СЦЕНАРИЙ 13: Конкретный туроператор")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в Турцию из Москвы в марте, только от Anex Tour или Coral Travel."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_14():
    """Сценарий 14: Конкретный отель"""
    print("=" * 60)
    print("СЦЕНАРИЙ 14: Поиск конкретного отеля")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в отель Rixos в Турции из Москвы в марте."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_15():
    """Сценарий 15: Только подтверждённые туры (onrequest=1)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 15: Только подтверждённые туры (без 'под запрос')")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в Турцию из Москвы в марте, "
            "но только те которые точно есть, без 'под запрос'."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_16():
    """Сценарий 16: Бизнес-класс"""
    print("=" * 60)
    print("СЦЕНАРИЙ 16: Перелёт бизнес-классом")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хочу в Турцию из Москвы в марте, перелёт бизнес-классом."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_17():
    """Сценарий 17: Конкретный курорт (regions) — проверка правильных кодов"""
    print("=" * 60)
    print("СЦЕНАРИЙ 17: Конкретный курорт (Аланья)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в Аланью (Турция) из Москвы в марте."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_18():
    """Сценарий 18: Получение текущей даты"""
    print("=" * 60)
    print("СЦЕНАРИЙ 18: Текущая дата")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Какая сейчас дата? Найди туры в Турцию на ближайшие выходные."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_19():
    """Сценарий 19: Бизнес-класс перелёта"""
    print("=" * 60)
    print("СЦЕНАРИЙ 19: Бизнес-класс")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди тур в Турцию из Москвы в марте, перелёт бизнес-классом."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_20():
    """Сценарий 20: Двое детей разного возраста"""
    print("=" * 60)
    print("СЦЕНАРИЙ 20: Двое детей")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хотим в Турцию из Москвы в марте, двое взрослых и двое детей — 5 и 12 лет. Всё включено."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_21():
    """Сценарий 21: Проверка visacharge — Египет"""
    print("=" * 60)
    print("СЦЕНАРИЙ 21: Визовые расходы (Египет)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        # Сначала поиск в Египет
        print("\n--- Поиск в Египет ---")
        await handler.chat("Найди тур в Египет из Москвы в марте, 4-5 звёзд")
        
        # Потом актуализация для проверки visacharge
        print("\n--- Актуализация для проверки визы ---")
        response = await handler.chat(
            "Какая точная цена первого варианта? И нужно ли доплачивать за визу?"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_22():
    """Сценарий 22: Конкретный район курорта (subregions)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 22: Подкурорт (subregions)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в Кемер, район Бельдиби, из Москвы в марте."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


# ==================== ФИНАЛЬНЫЕ ТЕСТЫ ДЛЯ 100% ПОКРЫТИЯ ====================

async def test_scenario_23():
    """Сценарий 23: Трое детей (childage3)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 23: Трое детей")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хотим в Турцию из Москвы в марте, 2 взрослых и 3 детей — 3, 7 и 14 лет."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_24():
    """Сценарий 24: Валюта (currency)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 24: Цены в долларах")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Найди туры в Турцию из Москвы в марте. Цены покажи в долларах."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_25():
    """Сценарий 25: 'А можно дешевле?'"""
    print("=" * 60)
    print("СЦЕНАРИЙ 25: Запрос на удешевление")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        print("\n--- Первый поиск ---")
        await handler.chat("Туры в Турцию из Москвы в марте, 5 звёзд, UAI, бюджет 100 тысяч")
        
        print("\n--- Запрос дешевле ---")
        response = await handler.chat("Слишком дорого. А можно дешевле?")
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_26():
    """Сценарий 26: Сравнить два отеля"""
    print("=" * 60)
    print("СЦЕНАРИЙ 26: Сравнение отелей")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        print("\n--- Поиск ---")
        await handler.chat("Туры в Турцию из Москвы в марте до 150 тысяч")
        
        print("\n--- Сравнение ---")
        response = await handler.chat("Сравни первый и второй отель — какой лучше для семьи с детьми?")
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_27():
    """Сценарий 27: Неизвестный город"""
    print("=" * 60)
    print("СЦЕНАРИЙ 27: Неизвестный город вылета")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хочу в Турцию в марте из Владивостока"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_28():
    """Сценарий 28: Диапазон дат > 14 дней"""
    print("=" * 60)
    print("СЦЕНАРИЙ 28: Большой диапазон дат")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хочу в Турцию из Москвы в период с 1 марта по 30 апреля, гибкие даты."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_29():
    """Сценарий 29: 6+ взрослых"""
    print("=" * 60)
    print("СЦЕНАРИЙ 29: Большая группа (7 взрослых)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хотим в Турцию из Москвы в марте, нас 7 человек взрослых."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_30():
    """Сценарий 30: Ломаный русский"""
    print("=" * 60)
    print("СЦЕНАРИЙ 30: Ломаный русский")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "хочу турция море дети март москва дешево"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_31():
    """Сценарий 31: Стресс-тест — много требований"""
    print("=" * 60)
    print("СЦЕНАРИЙ 31: Стресс-тест (много требований)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Хочу в Турцию из Москвы в марте, 2 взрослых и ребёнок 5 лет. "
            "Только 5 звёзд, UAI, первая линия, песчаный пляж, аквапарк, "
            "прямой рейс, без пересадок, бюджет до 200 тысяч, "
            "желательно Белек или Аланья."
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_32():
    """Сценарий 32: Вопрос про отмену (FAQ)"""
    print("=" * 60)
    print("СЦЕНАРИЙ 32: Вопрос про отмену")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        response = await handler.chat(
            "Если я забронирую тур, можно ли потом отменить? Какие условия отмены?"
        )
        print("\n✅ РЕЗУЛЬТАТ:\n" + response)
    finally:
        await handler.close()


async def test_scenario_33():
    """Сценарий 33: STREAMING — ответ по частям"""
    print("=" * 60)
    print("СЦЕНАРИЙ 33: Streaming (ответ появляется по частям)")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        print("\n🌊 Streaming ответ:")
        print("-" * 40)
        
        response = await handler.chat_stream(
            "Расскажи кратко про 3 популярных курорта Турции",
            on_token=lambda t: print(t, end="", flush=True)
        )
        
        print("\n" + "-" * 40)
        print(f"\n✅ Полный ответ получен ({len(response)} символов)")
    finally:
        await handler.close()


async def test_scenario_34():
    """Сценарий 34: STREAMING + Function Calling"""
    print("=" * 60)
    print("СЦЕНАРИЙ 34: Streaming с вызовом функций")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    try:
        print("\n🌊 Streaming с функциями:")
        print("-" * 40)
        
        response = await handler.chat_stream(
            "Найди горящие туры из Москвы и расскажи о лучшем варианте",
            on_token=lambda t: print(t, end="", flush=True)
        )
        
        print("\n" + "-" * 40)
        print(f"\n✅ Ответ получен")
    finally:
        await handler.close()


async def run_all_scenarios():
    """Запустить все сценарии последовательно"""
    scenarios = [
        ("1", test_scenario_1),
        ("2", test_scenario_2),
        ("3", test_scenario_3),
        ("4", test_scenario_4),
        ("5", test_scenario_5),
        ("6", test_scenario_6),
        ("7", test_scenario_7),
        ("8", test_scenario_8),
        ("9", test_scenario_9),
        ("10", test_scenario_10),
        ("11", test_scenario_11),
        ("12", test_scenario_12),
        ("13", test_scenario_13),
        ("14", test_scenario_14),
        ("15", test_scenario_15),
        ("16", test_scenario_16),
        ("17", test_scenario_17),
        ("18", test_scenario_18),
        ("19", test_scenario_19),
        ("20", test_scenario_20),
        ("21", test_scenario_21),
        ("22", test_scenario_22),
        ("23", test_scenario_23),
        ("24", test_scenario_24),
        ("25", test_scenario_25),
        ("26", test_scenario_26),
        ("27", test_scenario_27),
        ("28", test_scenario_28),
        ("29", test_scenario_29),
        ("30", test_scenario_30),
        ("31", test_scenario_31),
        ("32", test_scenario_32),
    ]
    
    results = {}
    
    for name, func in scenarios:
        print(f"\n\n{'🚀' * 30}")
        print(f"ЗАПУСК СЦЕНАРИЯ {name}")
        print(f"{'🚀' * 30}\n")
        
        try:
            await func()
            results[name] = "✅ УСПЕХ"
        except Exception as e:
            results[name] = f"❌ ОШИБКА: {str(e)[:100]}"
            print(f"\n❌ ОШИБКА: {e}")
        
        print("\n" + "-" * 60)
        input("Нажмите Enter для следующего сценария...")
    
    # Итоги
    print("\n\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    for name, result in results.items():
        print(f"Сценарий {name}: {result}")


async def interactive_chat():
    """Интерактивный режим — реальный агент для общения"""
    print("=" * 60)
    print("🤖 AI МЕНЕДЖЕР ПО ТУРАМ (Responses API)")
    print("=" * 60)
    print("Напишите ваш запрос. Для выхода введите 'exit' или 'выход'.")
    print("Теперь работает поиск в интернете для вопросов о визах, погоде и т.д.")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    
    try:
        while True:
            # Ввод от пользователя
            user_input = input("\n👤 Вы: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'выход', 'quit', 'q']:
                print("\n👋 До свидания!")
                break
            
            # Ответ агента
            try:
                response = await handler.chat(user_input)
                print(f"\n🤖 Ассистент:\n{response}")
            except Exception as e:
                print(f"\n❌ Ошибка: {e}")
    
    finally:
        await handler.close()


async def interactive_chat_stream():
    """
    Интерактивный режим со STREAMING.
    Ответ появляется по частям — как в ChatGPT!
    """
    print("=" * 60)
    print("🌊 AI МЕНЕДЖЕР ПО ТУРАМ (STREAMING MODE)")
    print("=" * 60)
    print("Ответы появляются по частям — как в ChatGPT!")
    print("Напишите запрос. Для выхода: 'exit' или 'выход'.")
    print("=" * 60)
    
    handler = YandexGPTHandler()
    
    try:
        while True:
            # Ввод от пользователя
            user_input = input("\n👤 Вы: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'выход', 'quit', 'q']:
                print("\n👋 До свидания!")
                break
            
            # Ответ агента со streaming
            try:
                print("\n🤖 Ассистент: ", end="", flush=True)
                response = await handler.chat_stream(
                    user_input,
                    on_token=lambda t: print(t, end="", flush=True)
                )
                print()  # Новая строка после ответа
            except Exception as e:
                print(f"\n❌ Ошибка: {e}")
    
    finally:
        await handler.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        # Интерактивный режим
        if arg in ["chat", "run", "agent"]:
            asyncio.run(interactive_chat())
        elif arg in ["stream", "streaming"]:
            asyncio.run(interactive_chat_stream())
        # Тесты
        else:
            scenarios_map = {
                "1": test_scenario_1,
                "2": test_scenario_2,
                "3": test_scenario_3,
                "4": test_scenario_4,
                "5": test_scenario_5,
                "6": test_scenario_6,
                "7": test_scenario_7,
                "8": test_scenario_8,
                "9": test_scenario_9,
                "10": test_scenario_10,
                "11": test_scenario_11,
                "12": test_scenario_12,
                "13": test_scenario_13,
                "14": test_scenario_14,
                "15": test_scenario_15,
                "16": test_scenario_16,
                "17": test_scenario_17,
                "18": test_scenario_18,
                "19": test_scenario_19,
                "20": test_scenario_20,
                "21": test_scenario_21,
                "22": test_scenario_22,
                "23": test_scenario_23,
                "24": test_scenario_24,
                "25": test_scenario_25,
                "26": test_scenario_26,
                "27": test_scenario_27,
                "28": test_scenario_28,
                "29": test_scenario_29,
                "30": test_scenario_30,
                "31": test_scenario_31,
                "32": test_scenario_32,
                "33": test_scenario_33,
                "34": test_scenario_34,
                "all": run_all_scenarios,
            }
            if arg in scenarios_map:
                asyncio.run(scenarios_map[arg]())
            else:
                print(f"Неизвестная команда: {arg}")
                print("Доступные: chat, stream, 1-34, all")
    else:
        # По умолчанию — интерактивный режим со streaming
        asyncio.run(interactive_chat_stream())

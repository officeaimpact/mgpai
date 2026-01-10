"""
Клиент YandexGPT для ИИ-ассистента МГП.

Предоставляет методы для:
- Извлечения сущностей из текста (страна, даты, туристы)
- Определения намерения пользователя
- Ответов на FAQ вопросы
"""
from __future__ import annotations

import json
import httpx
from typing import Optional
from datetime import date

from app.core.config import settings


# Системный промпт для извлечения сущностей
ENTITY_EXTRACTION_PROMPT = """Ты — ИИ-ассистент туристического агентства. Твоя задача — извлечь информацию о туре из сообщения пользователя.

Извлеки следующие данные (если они указаны):
- destination_country: страна назначения
- destination_region: регион (если указан)
- destination_resort: курорт (если указан)
- date_from: дата начала в формате YYYY-MM-DD
- date_to: дата окончания в формате YYYY-MM-DD
- nights: количество ночей (вычисли из дат, если указаны обе даты)
- adults: количество взрослых (1-6)
- children: список возрастов детей (каждый возраст 0-15)
- hotel_name: название отеля (если указан конкретный отель)
- food_type: тип питания (RO, BB, HB, FB, AI, UAI)
- departure_city: город вылета

Также определи намерение (intent):
- "search_tour" — пользователь ищет тур (указывает параметры: страна, даты, количество людей)
- "hot_tours" — пользователь интересуется горящими турами
- "general_chat" — общий вопрос о погоде, советы, сравнения стран, рекомендации по отелям (БЕЗ конкретного запроса на поиск тура)
- "faq_visa" — вопрос о визах
- "faq_payment" — вопрос об оплате
- "faq_cancel" — вопрос об отмене/возврате
- "faq_insurance" — вопрос о страховке
- "faq_documents" — вопрос о документах
- "greeting" — приветствие
- "other" — другое

ВАЖНО для определения intent:
- Если пользователь СПРАШИВАЕТ о погоде, климате, отелях, сравнивает страны — это "general_chat"
- Если пользователь ПРОСИТ найти/подобрать тур с конкретными параметрами — это "search_tour"
- Пример "general_chat": "Какая погода в Турции?", "Какой отель лучше для детей?", "Что посмотреть в Египте?"
- Пример "search_tour": "Хочу в Турцию на двоих в июне", "Найди тур в Египет на 7 ночей"

ВАЖНЫЕ ПРАВИЛА:
1. Если указаны две даты — вычисли количество ночей автоматически.
2. Если указан отель — НЕ требуй звёздность, её можно найти по названию.
3. Дети делятся на категории: младенцы (0-2 года) и дети (2-15 лет).
4. Если количество взрослых не указано, но есть слова "вдвоём", "вместе" — это 2 взрослых.
5. Текущий год: {current_year}. Если год не указан, используй ближайшую подходящую дату.

Верни ТОЛЬКО валидный JSON без комментариев:
{{
  "intent": "search_tour",
  "entities": {{
    "destination_country": "Турция",
    "date_from": "2026-02-15",
    "adults": 2
  }}
}}"""

# База знаний FAQ
FAQ_KNOWLEDGE_BASE = """
# База знаний туристического агентства МГП

## Визы и въезд

### Безвизовые страны для граждан РФ:
- **Турция** — до 60 дней без визы
- **Египет** — виза по прилёту (25$) или безвизовый въезд в Шарм-эль-Шейх до 15 дней
- **ОАЭ** — до 90 дней без визы
- **Таиланд** — до 30 дней без визы (можно продлить до 60)
- **Мальдивы** — до 30 дней без визы
- **Индонезия (Бали)** — до 30 дней без визы
- **Шри-Ланка** — электронная виза (ETA)
- **Куба** — до 30 дней без визы
- **Доминикана** — до 30 дней без визы
- **Черногория** — до 30 дней без визы

### Страны, требующие визу:
- **Шенген** (Греция, Испания, Италия, Франция и др.) — требуется шенгенская виза
- **Кипр** — бесплатная провиза онлайн (для граждан РФ)
- **США, Великобритания, Австралия** — требуется виза

### Требования к загранпаспорту:
- Срок действия: минимум 6 месяцев после даты возвращения
- Наличие чистых страниц для штампов

## Оплата туров

### Способы оплаты:
- Банковские карты (Visa, MasterCard, МИР)
- Наличные в офисе агентства
- Банковский перевод
- Система быстрых платежей (СБП)

### Рассрочка:
- Рассрочка 0% на 4-6 месяцев от банков-партнёров
- Первоначальный взнос от 10%

### Бронирование:
- Предоплата от 30% для подтверждения бронирования
- Полная оплата за 14 дней до вылета (для раннего бронирования)
- Горящие туры — полная оплата сразу

## Отмена и возврат

### Условия отмены тура:
- **Более 30 дней до вылета** — возврат 90-100% (за вычетом фактических расходов)
- **15-30 дней** — удержание до 25%
- **7-14 дней** — удержание до 50%
- **3-7 дней** — удержание до 75%
- **Менее 3 дней** — возврат не гарантирован

### Страховка от невыезда:
- Покрывает отмену по болезни, отказу в визе, вызову в суд и др.
- Стоимость: 3-5% от стоимости тура
- Рекомендуем оформлять при раннем бронировании

## Страхование

### Обязательная медицинская страховка:
- Включена в стоимость большинства пакетных туров
- Покрытие от 30 000 до 50 000 USD
- Покрывает: экстренную мед. помощь, госпитализацию, эвакуацию

### Дополнительные страховки:
- **Страховка от невыезда** — отмена по уважительным причинам
- **Страховка багажа** — потеря, повреждение багажа
- **Страховка от несчастных случаев** — травмы во время отдыха
- **Страховка активного отдыха** — дайвинг, серфинг, лыжи

## Документы для поездки

### Взрослые:
- Загранпаспорт (срок действия 6+ месяцев)
- Авиабилеты и ваучер отеля
- Страховой полис
- Копия внутреннего паспорта

### Дети:
- Загранпаспорт ребёнка (или запись в паспорте родителя для детей до 14 лет)
- Свидетельство о рождении (копия)
- Согласие на выезд от второго родителя (если едет с одним родителем)

### Для отдельных стран:
- Обратные билеты (подтверждение выезда)
- Бронирование отеля
- Подтверждение финансовой состоятельности
"""

# Промпт для ответов на FAQ
FAQ_ANSWER_PROMPT = """Ты — вежливый ИИ-ассистент туристического агентства МГП.
Используй ТОЛЬКО информацию из базы знаний для ответа на вопрос.
Отвечай кратко, по существу, дружелюбно.
Если информации нет в базе знаний — скажи, что нужно уточнить у менеджера.

База знаний:
{knowledge_base}

Вопрос пользователя: {question}

Дай полезный ответ:"""


class YandexGPTClient:
    """
    Клиент для работы с YandexGPT API.
    """
    
    BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1"
    
    def __init__(self):
        self.folder_id = settings.YANDEX_FOLDER_ID
        self.api_key = settings.YANDEX_API_KEY
        self.model = settings.YANDEX_MODEL
        self.enabled = settings.YANDEX_GPT_ENABLED
        self.client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Ленивая инициализация HTTP клиента."""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client
    
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1000
    ) -> str:
        """
        Вызов YandexGPT API.
        
        Args:
            system_prompt: Системный промпт
            user_prompt: Сообщение пользователя
            temperature: Температура генерации (0-1)
            max_tokens: Максимум токенов в ответе
            
        Returns:
            Текст ответа модели
        """
        if not self.enabled or not self.api_key or not self.folder_id:
            raise ValueError("YandexGPT не настроен. Проверьте YANDEX_API_KEY и YANDEX_FOLDER_ID")
        
        client = await self._get_client()
        
        model_uri = f"gpt://{self.folder_id}/{self.model}"
        
        payload = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens)
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt}
            ]
        }
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        response = await client.post(
            f"{self.BASE_URL}/completion",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["result"]["alternatives"][0]["message"]["text"]
    
    async def extract_entities(self, user_message: str) -> dict:
        """
        Извлечение сущностей из сообщения пользователя.
        
        Args:
            user_message: Текст сообщения
            
        Returns:
            Словарь с intent и entities
        """
        if not self.enabled:
            # Возвращаем пустой результат если LLM отключен
            return {"intent": "search_tour", "entities": {}}
        
        try:
            current_year = date.today().year
            system_prompt = ENTITY_EXTRACTION_PROMPT.format(current_year=current_year)
            
            response = await self._call_api(
                system_prompt=system_prompt,
                user_prompt=user_message,
                temperature=0.1,
                max_tokens=500
            )
            
            # Парсим JSON из ответа
            # Убираем возможные markdown блоки
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()
            
            result = json.loads(response)
            return result
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}, response: {response}")
            return {"intent": "search_tour", "entities": {}}
        except Exception as e:
            print(f"YandexGPT error: {e}")
            return {"intent": "search_tour", "entities": {}}
    
    async def answer_faq(self, question: str) -> str:
        """
        Ответ на FAQ вопрос с использованием базы знаний.
        
        Args:
            question: Вопрос пользователя
            
        Returns:
            Ответ на основе базы знаний
        """
        if not self.enabled:
            return ""
        
        try:
            prompt = FAQ_ANSWER_PROMPT.format(
                knowledge_base=FAQ_KNOWLEDGE_BASE,
                question=question
            )
            
            response = await self._call_api(
                system_prompt="Ты — полезный ассистент турагентства.",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=800
            )
            
            return response.strip()
            
        except Exception as e:
            print(f"YandexGPT FAQ error: {e}")
            return ""
    
    async def generate_conversational_response(
        self,
        user_message: str,
        search_params: dict,
        conversation_history: list
    ) -> str:
        """
        Генерация разговорного ответа на общий вопрос.
        
        Отвечает на вопросы о погоде, советы по отелям, сравнения стран
        и мягко подводит к сбору информации для поиска тура.
        
        Args:
            user_message: Вопрос пользователя
            search_params: Уже известные параметры поиска
            conversation_history: История сообщений
            
        Returns:
            Ответ с информацией + мягкий вопрос о планах
        """
        if not self.enabled:
            return ""
        
        try:
            # Импортируем промпт здесь, чтобы избежать циклических импортов
            from app.agent.prompts import get_general_chat_prompt, get_system_prompt
            
            # Формируем промпт с контекстом
            chat_prompt = get_general_chat_prompt(user_message, search_params)
            system_prompt = get_system_prompt()
            
            # Формируем историю для контекста (последние 4 сообщения)
            recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
            history_text = "\n".join([
                f"{'Пользователь' if msg['role'] == 'user' else 'Ассистент'}: {msg['content']}"
                for msg in recent_history[:-1]  # Исключаем текущее сообщение
            ])
            
            if history_text:
                chat_prompt = f"История диалога:\n{history_text}\n\n{chat_prompt}"
            
            response = await self._call_api(
                system_prompt=system_prompt,
                user_prompt=chat_prompt,
                temperature=0.7,  # Более творческие ответы для разговора
                max_tokens=600
            )
            
            return response.strip()
            
        except Exception as e:
            print(f"YandexGPT conversational error: {e}")
            return ""
    
    async def close(self):
        """Закрытие HTTP клиента."""
        if self.client:
            await self.client.aclose()
            self.client = None


# Глобальный экземпляр клиента
llm_client = YandexGPTClient()

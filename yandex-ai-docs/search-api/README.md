# Search API Documentation

Веб-поиск и генеративный поиск — инструменты для AI-агентов.

## Структура папки (34 файла)

```
search-api/
├── quickstart/
│   └── index.md                    # Быстрый старт
│
├── concepts/
│   ├── index.md                    # О сервисе
│   ├── generative-response.md      # Генеративный поиск ⭐
│   ├── web-search.md               # Веб-поиск
│   ├── limits.md                   # Лимиты
│   ├── get-request.md              # GET-запросы
│   ├── post-request.md             # POST-запросы
│   ├── response.md                 # Формат ответа (XML)
│   ├── html-response.md            # Формат ответа (HTML)
│   └── search-operators.md         # Операторы поиска
│
├── api-ref/
│   ├── index.md                    # Обзор API
│   ├── authentication.md           # Авторизация
│   ├── GenSearch/                  # Генеративный поиск API ⭐
│   │   ├── index.md
│   │   └── search.md
│   ├── WebSearch/                  # Синхронный веб-поиск
│   │   ├── index.md
│   │   └── search.md
│   ├── WebSearchAsync/             # Асинхронный веб-поиск
│   │   ├── index.md
│   │   └── search.md
│   └── Operation/                  # Операции
│
├── operations/
│   ├── index.md                    # Обзор операций
│   ├── auth.md                     # Авторизация
│   ├── web-search.md               # Веб-поиск
│   ├── web-search-sync.md          # Синхронный поиск
│   ├── web-search-geo.md           # Поиск с геолокацией
│   ├── searching.md                # Принципы поиска
│   ├── test-request.md             # Тестовый запрос
│   ├── request-limits.md           # Лимиты запросов
│   └── workaround.md               # Обходные решения
│
├── reference/
│   └── error-codes.md              # Коды ошибок
│
├── security/
│   └── index.md                    # Безопасность
│
└── pricing.md                      # Цены
```

---

## Детальное описание ключевых файлов

### `concepts/generative-response.md` — Генеративный поиск ⭐

**Когда использовать:** Когда AI-агенту нужно искать актуальную информацию в интернете.

**Что это:**
Генеративный ответ = YandexGPT + результаты поиска Яндекса. Модель анализирует результаты поиска и генерирует единый ёмкий ответ.

**Формат запроса:**
```json
{
  "messages": [
    {"content": "Какая погода в Москве?", "role": "ROLE_USER"}
  ],
  "searchOptions": {
    "searchType": "WEB",
    "site": []
  }
}
```

**Параметры:**
| Параметр | Описание |
|----------|----------|
| `searchType` | `WEB` — поиск по интернету |
| `site` | Ограничение по сайтам (до 5) |
| `region` | Регион поиска |
| `maxResults` | Максимум результатов |

**Использование как инструмент агента:**
- Web Search Tool в AI Studio
- См. `ai-studio/concepts/agents/tools/websearch.md`

**Лимиты:**
- 1 синхронный запрос в секунду (по умолчанию)
- Требуется роль `search-api.webSearch.user`

---

### `concepts/web-search.md` — Веб-поиск

**Когда использовать:** Для получения результатов поиска без генерации.

**Содержание:**
- Параметры поискового запроса
- Фильтрация результатов
- Сортировка
- Регионы поиска

---

### `concepts/search-operators.md` — Операторы поиска

**Когда использовать:** Для точной настройки поисковых запросов.

**Операторы:**
| Оператор | Пример | Описание |
|----------|--------|----------|
| `site:` | `site:example.com` | Поиск только на сайте |
| `inurl:` | `inurl:blog` | URL содержит слово |
| `-` | `-spam` | Исключить слово |
| `""` | `"точная фраза"` | Точное совпадение |

---

### `api-ref/GenSearch/search.md` — API генеративного поиска

**Когда использовать:** Для прямых API-вызовов генеративного поиска.

**Endpoint:**
```
POST /search-api/v2/gensearch
```

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Api-Key <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"content": "Что такое AI?", "role": "ROLE_USER"}],
    "searchOptions": {"searchType": "WEB"}
  }' \
  "https://searchapi.api.cloud.yandex.net/v2/gensearch"
```

---

### `operations/auth.md` — Авторизация

**Когда использовать:** Для настройки авторизации в Search API.

**Методы:**
- API-ключ (рекомендуется)
- IAM-токен

---

## Интеграция с AI-агентом

### Способ 1: Web Search Tool (рекомендуется)

AI Studio предоставляет встроенный инструмент Web Search:

```python
# Через Responses API с инструментом web_search
# См. ai-studio/concepts/agents/tools/websearch.md
```

### Способ 2: Прямой вызов GenSearch API

```python
import requests

response = requests.post(
    "https://searchapi.api.cloud.yandex.net/v2/gensearch",
    headers={
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "messages": [{"content": "Новости AI сегодня", "role": "ROLE_USER"}],
        "searchOptions": {"searchType": "WEB"}
    }
)
```

---

## Типичные сценарии

### Поиск актуальной информации
- AI-агент ищет новости, курсы валют, погоду
- Использовать: GenSearch API или Web Search Tool

### Поиск по конкретным сайтам
- Ограничить поиск документацией или базой знаний
- Использовать: параметр `site` в GenSearch

### RAG с веб-поиском
- Агент дополняет знания актуальной информацией из интернета
- Комбинировать: Vector Store + Web Search Tool

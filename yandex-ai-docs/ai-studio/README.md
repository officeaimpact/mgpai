# AI Studio Documentation

Ядро документации для создания AI-агентов на Yandex Cloud.

## Структура

### Концепции (`concepts/`)
| Файл/Папка | Когда использовать |
|------------|-------------------|
| `agents/` | Архитектура AI-агентов, инструменты (File Search, Web Search, MCP) |
| `assistant/` | Assistants API (устаревает, но работает) |
| `generation/` | Генерация текста, function calling, structured output, токены |
| `mcp-hub/` | MCP Hub — подключение внешних API через MCP-серверы |
| `classifier/` | Классификация текста |
| `embeddings.md` | Эмбеддинги для семантического поиска |
| `search/` | Поисковые индексы, Vector Store |
| `openai-compatibility.md` | Совместимость с OpenAI API |
| `api.md` | Обзор всех API |
| `limits.md` | Лимиты и квоты |

### API Reference

| Папка | Когда использовать |
|-------|-------------------|
| `text-generation/` | Генерация текста (YandexGPT) — основной API |
| `embeddings/` | Создание эмбеддингов |
| `chat/` | Chat Completions API (OpenAI-совместимый) |
| `conversations/` | Управление диалогами и контекстом |
| `responses/` | Responses API (новый API для агентов) |
| `assistants/` | Assistants API (создание ассистентов) |
| `threads/` | Треды (история диалога) |
| `runs/` | Запуски ассистентов |
| `files/` | Files API (загрузка файлов) |
| `vectorStores/` | Vector Store API (RAG) |
| `searchindex/` | Search Index API (RAG) |
| `mcp-gateway/` | MCP Gateway API |
| `text-classification/` | Классификация текста |
| `models/` | Список моделей |
| `users/` | Users API |

### SDK (`sdk/`, `sdk-ref/`)
| Файл | Когда использовать |
|------|-------------------|
| `sdk/index.md` | Обзор Yandex AI Studio SDK |
| `sdk-ref/auth.md` | Методы аутентификации в SDK |
| `sdk-ref/async/` | Асинхронные методы SDK |
| `sdk-ref/sync/` | Синхронные методы SDK |
| `sdk-ref/types/` | Типы данных SDK |

### Операции (`operations/`)
| Папка | Когда использовать |
|-------|-------------------|
| `agents/` | Создание агентов (file search, web search, function calling) |
| `assistant/` | Операции с ассистентами |
| `generation/` | Генерация текста, function call |
| `embeddings/` | Работа с эмбеддингами |
| `classifier/` | Классификация текста |
| `mcp-servers/` | Управление MCP-серверами |
| `get-api-key.md` | Получение API-ключа |
| `disable-logging.md` | Отключение логирования |

### Промпты и гайды
| Папка | Когда использовать |
|-------|-------------------|
| `gpt-prompting-guide/` | Техники промпт-инжиниринга (CoT, few-shot, zero-shot) |
| `prompts/yandexgpt/` | Готовые промпты для разных задач |

### Туториалы (`tutorials/`)
| Файл | Описание |
|------|----------|
| `pdf-searchindex-ai-assistant.md` | AI-ассистент с RAG (поиск по PDF) |
| `create-ai-agent-function.md` | Агент с function calling |
| `streaming-openai-agent.md` | Стриминг через OpenAI SDK |
| `ai-model-ide-integration.md` | Интеграция с IDE |
| `tg-bot-assistant.md` | Telegram-бот с RAG |
| `telegram-ai-bot-workflows.md` | Telegram + Workflows |

### Прочее
| Файл | Когда использовать |
|------|-------------------|
| `quickstart/index.md` | Быстрый старт |
| `security/index.md` | Роли и права доступа |
| `qa/` | FAQ |
| `troubleshooting/` | Решение проблем |

## Типичные сценарии

### Простой чат-бот
```
text-generation/ → chat/ → operations/generation/create-chat.md
```

### Агент с RAG (поиск по документам)
```
files/ → vectorStores/ → searchindex/ → assistants/ → operations/agents/create-filesearch-text-agent.md
```

### Агент с Function Calling
```
concepts/generation/function-call.md → operations/generation/function-call.md → operations/agents/create-function-text-agent.md
```

### Агент с веб-поиском
```
concepts/agents/tools/websearch.md → operations/agents/create-websearch-text-agent.md
```

### Агент с MCP (внешние API)
```
concepts/mcp-hub/ → mcp-gateway/ → operations/mcp-servers/
```

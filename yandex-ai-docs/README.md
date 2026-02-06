# Yandex AI Documentation

Отфильтрованная документация Yandex Cloud для создания AI-агентов с внешним хостингом.

## Структура документации (485 файлов)

| Папка | Файлов | Описание | Когда использовать |
|-------|--------|----------|-------------------|
| [ai-studio/](./ai-studio/) | 386 | **Ядро** — AI Studio, YandexGPT, агенты, RAG, MCP | Создание AI-агентов |
| [iam/](./iam/) | 12 | Авторизация — API-ключи, IAM-токены | Настройка доступа к API |
| [search-api/](./search-api/) | 34 | Веб-поиск и генеративный поиск | Поиск информации в интернете |
| [vision/](./vision/) | 33 | OCR — распознавание текста | Извлечение текста из изображений |
| [billing/](./billing/) | 4 | Биллинг — тарификация, расходы | Контроль затрат |
| [glossary/](./glossary/) | 13 | Глоссарий — LLM, MCP, gRPC, JWT | Понимание терминов |
| [_tutorials/](./_tutorials/) | 3 | Практические туториалы | Примеры и обучение |

---

## Быстрый старт

### 1. Авторизация

```python
pip install yandex-ai-studio-sdk
```

```python
from yandex_ai_studio_sdk import AIStudio

sdk = AIStudio(
    folder_id="<folder_id>",
    auth="<api_key>"  # API-ключ сервисного аккаунта
)
```

**Как получить API-ключ:**
1. Создать сервисный аккаунт → [iam/operations/sa/create.md](./iam/operations/sa/create.md)
2. Назначить роль `ai.languageModels.user` → [iam/operations/sa/assign-role-for-sa.md](./iam/operations/sa/assign-role-for-sa.md)
3. Создать API-ключ → [iam/operations/authentication/manage-api-keys.md](./iam/operations/authentication/manage-api-keys.md)

### 2. Генерация текста

```python
model = sdk.models.completions("yandexgpt")
result = model.run("Привет, как дела?")
print(result[0].text)
```

**Документация:** [ai-studio/text-generation/](./ai-studio/text-generation/)

### 3. Создание агента с инструментами

```python
# Function Calling — ai-studio/concepts/generation/function-call.md
# RAG с Vector Store — ai-studio/vectorStores/
# MCP Gateway — ai-studio/mcp-gateway/
# Web Search — search-api/concepts/generative-response.md
```

---

## Карта документации

### Основные задачи

| Задача | Документация |
|--------|--------------|
| Создать API-ключ | `iam/operations/authentication/manage-api-keys.md` |
| Генерация текста | `ai-studio/text-generation/` |
| Создать AI-агента | `ai-studio/concepts/agents/` |
| RAG (поиск по документам) | `ai-studio/vectorStores/`, `ai-studio/searchindex/` |
| Function Calling | `ai-studio/concepts/generation/function-call.md` |
| Веб-поиск | `search-api/concepts/generative-response.md` |
| OCR (текст из изображений) | `vision/operations/ocr/` |
| MCP-серверы | `ai-studio/mcp-gateway/` |
| Промпт-инжиниринг | `ai-studio/gpt-prompting-guide/` |

### Компоненты AI-агента

| Компонент | Описание | Документация |
|-----------|----------|--------------|
| **LLM** | Языковая модель | `ai-studio/concepts/generation/models.md` |
| **Инструкция** | Промпт и поведение | `ai-studio/gpt-prompting-guide/` |
| **Инструменты** | File Search, Web Search, MCP | `ai-studio/concepts/agents/tools/` |
| **Память** | Треды и контекст | `ai-studio/threads/`, `ai-studio/conversations/` |

### API для агентов

| API | Описание | Документация |
|-----|----------|--------------|
| Responses API | Новый API для агентов | `ai-studio/responses/` |
| Assistants API | Классический API | `ai-studio/assistants/` |
| Chat Completions | Простая генерация | `ai-studio/chat/` |
| Conversations | Диалоги с контекстом | `ai-studio/conversations/` |

---

## Модели YandexGPT

| Модель | Описание |
|--------|----------|
| `yandexgpt` | Основная модель |
| `yandexgpt-lite` | Быстрая модель |
| `yandexgpt-32k` | Расширенный контекст |

**Документация:** [ai-studio/concepts/generation/models.md](./ai-studio/concepts/generation/models.md)

---

## Глоссарий ключевых терминов

| Термин | Описание | Файл |
|--------|----------|------|
| LLM | Большие языковые модели | `glossary/llm.md` |
| MCP | Model Context Protocol | `glossary/mcp.md` |
| RAG | Retrieval Augmented Generation | `ai-studio/concepts/assistant/` |
| Function Calling | Вызов внешних функций | `ai-studio/concepts/generation/function-call.md` |
| Токены | Единицы текста для модели | `ai-studio/concepts/generation/tokens.md` |
| Эмбеддинги | Векторные представления | `ai-studio/concepts/embeddings.md` |

---

## Туториалы

| Туториал | Описание |
|----------|----------|
| [pdf-searchindex-ai-assistant.md](./ai-studio/tutorials/pdf-searchindex-ai-assistant.md) | AI-ассистент с RAG (поиск по PDF) |
| [create-ai-agent-function.md](./ai-studio/tutorials/create-ai-agent-function.md) | Агент с Function Calling |
| [tg-bot-assistant.md](./ai-studio/tutorials/tg-bot-assistant.md) | Telegram-бот с AI |
| [streaming-openai-agent.md](./ai-studio/tutorials/streaming-openai-agent.md) | Стриминг через OpenAI SDK |

---

## Ссылки

- [Yandex AI Studio SDK (GitHub)](https://github.com/yandex-cloud/yandex-ai-studio-sdk)
- [Yandex Cloud Console](https://console.yandex.cloud/)
- [OpenAI-совместимый API](./ai-studio/concepts/openai-compatibility.md)

---

## Cursor Rules

При работе в Cursor используется правило `.cursor/rules/yandex-ai-assistant.md`, которое автоматически направляет к этой документации при создании AI-ассистентов.

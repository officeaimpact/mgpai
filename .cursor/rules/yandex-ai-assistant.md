# Yandex AI Assistant Development Rules

## Описание

Правила для разработки AI-ассистентов и агентов на базе Yandex Cloud AI Studio.
При создании AI-агентов **ОБЯЗАТЕЛЬНО** использовать локальную документацию.

---

## Документация

**КРИТИЧЕСКИ ВАЖНО:** При создании AI-ассистентов, агентов или работе с Yandex AI API — **ВСЕГДА** проверяй и используй документацию в папке `yandex-ai-docs/`.

### Структура документации

```
yandex-ai-docs/
├── ai-studio/      # 386 файлов — ЯДРО: генерация, агенты, RAG, MCP
├── iam/            # 12 файлов — Авторизация: API-ключи, IAM-токены
├── search-api/     # 34 файла — Веб-поиск и генеративный поиск
├── vision/         # 33 файла — OCR: распознавание текста
├── billing/        # 4 файла — Биллинг и тарификация
├── glossary/       # 13 файлов — Термины: LLM, MCP, gRPC, JWT
└── _tutorials/     # 3 файла — Практические примеры
```

### Когда какую документацию использовать

| Задача | Папка/Файл |
|--------|------------|
| Создать API-ключ | `iam/operations/authentication/manage-api-keys.md` |
| Генерация текста | `ai-studio/text-generation/` |
| Создать агента | `ai-studio/concepts/agents/` |
| RAG (поиск по документам) | `ai-studio/vectorStores/`, `ai-studio/searchindex/` |
| Function Calling | `ai-studio/concepts/generation/function-call.md` |
| Веб-поиск для агента | `search-api/concepts/generative-response.md` |
| OCR (текст из изображений) | `vision/operations/ocr/` |
| MCP-серверы (внешние API) | `ai-studio/mcp-gateway/` |
| Промпт-инжиниринг | `ai-studio/gpt-prompting-guide/` |
| Понять термины | `glossary/` |

---

## Авторизация

### Рекомендуемый способ: API-ключ

```python
from yandex_ai_studio_sdk import AIStudio

sdk = AIStudio(
    folder_id="<folder_id>",
    auth="<api_key>"  # API-ключ сервисного аккаунта
)
```

**Документация:**
- `iam/concepts/authorization/api-key.md` — что такое API-ключ
- `iam/operations/authentication/manage-api-keys.md` — как создать

### Создание API-ключа (шаги)

1. Создать сервисный аккаунт → `iam/operations/sa/create.md`
2. Назначить роль `ai.languageModels.user` → `iam/operations/sa/assign-role-for-sa.md`
3. Создать API-ключ → `iam/operations/authentication/manage-api-keys.md`

### Области действия (scopes)

| Scope | Описание |
|-------|----------|
| `yc.ai.foundationModels.execute` | Все AI API (рекомендуется) |
| `yc.ai.languageModels.execute` | Только генерация текста |

---

## SDK

**Предпочтительно** использовать `yandex-ai-studio-sdk`:

```bash
pip install yandex-ai-studio-sdk
```

**Документация:** `ai-studio/sdk/index.md`

### Базовый пример

```python
from yandex_ai_studio_sdk import AIStudio

sdk = AIStudio(
    folder_id="<folder_id>",
    auth="<api_key>"
)

# Генерация текста
model = sdk.models.completions("yandexgpt")
result = model.run("Привет, как дела?")
print(result[0].text)
```

---

## Создание AI-агентов

### Архитектура агента

Агент состоит из 4 компонентов:
1. **LLM** — языковая модель (YandexGPT)
2. **Инструкция** (prompt) — описание поведения
3. **Инструменты** (tools) — внешние возможности
4. **Память** (memory) — контекст и история

**Документация:** `ai-studio/concepts/agents/index.md`

### Доступные инструменты

| Инструмент | Описание | Документация |
|------------|----------|--------------|
| File Search | RAG — поиск по документам | `ai-studio/concepts/agents/tools/filesearch.md` |
| Web Search | Поиск в интернете | `ai-studio/concepts/agents/tools/websearch.md` |
| MCP Tool | Внешние API через MCP | `ai-studio/concepts/mcp-hub/` |
| Function Calling | Вызов функций | `ai-studio/concepts/generation/function-call.md` |

### API для агентов

| API | Описание | Документация |
|-----|----------|--------------|
| Responses API | Новый API для текстовых агентов | `ai-studio/responses/` |
| Assistants API | Старый API (работает) | `ai-studio/assistants/` |
| Chat Completions | Простая генерация | `ai-studio/chat/` |
| Conversations | Диалоги с контекстом | `ai-studio/conversations/` |

---

## RAG (Retrieval Augmented Generation)

### Компоненты RAG

1. **Files API** — загрузка файлов
   - `ai-studio/files/`
   
2. **Vector Store API** — векторное хранилище
   - `ai-studio/vectorStores/`
   
3. **Search Index** — поисковый индекс
   - `ai-studio/searchindex/`

### Пошаговые инструкции

- `ai-studio/operations/agents/create-filesearch-text-agent.md`
- `ai-studio/tutorials/pdf-searchindex-ai-assistant.md`

---

## Function Calling

**Документация:**
- `ai-studio/concepts/generation/function-call.md` — концепция
- `ai-studio/operations/generation/function-call.md` — пошаговая инструкция

### Формат описания функции

```json
{
  "tools": [{
    "function": {
      "name": "get_weather",
      "description": "Получает прогноз погоды",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {"type": "string", "description": "Название города"}
        },
        "required": ["city"]
      }
    }
  }]
}
```

---

## MCP (Model Context Protocol)

**Когда использовать:** Для подключения внешних API к агенту.

**Документация:**
- `ai-studio/concepts/mcp-hub/index.md` — концепция
- `ai-studio/mcp-gateway/` — API
- `ai-studio/operations/mcp-servers/` — операции
- `glossary/mcp.md` — термин

---

## Веб-поиск для агента

**Документация:**
- `search-api/concepts/generative-response.md` — генеративный поиск
- `ai-studio/concepts/agents/tools/websearch.md` — Web Search Tool

---

## OCR (распознавание текста)

**Когда использовать:** Для извлечения текста из изображений/PDF.

**Документация:**
- `vision/operations/ocr/text-detection-image.md`
- `vision/concepts/ocr/index.md`

**Рекомендуемая модель для AI:** `markdown` — возвращает текст в Markdown.

---

## Промпт-инжиниринг

**Документация:**
- `ai-studio/gpt-prompting-guide/` — техники промптинга
- `ai-studio/prompts/yandexgpt/` — готовые промпты

### Техники

| Техника | Документация |
|---------|--------------|
| Zero-shot | `gpt-prompting-guide/techniques/zero-shot.md` |
| Few-shot | `gpt-prompting-guide/techniques/few-shot.md` |
| Chain of Thought | `gpt-prompting-guide/techniques/CoT.md` |
| Self-consistency | `gpt-prompting-guide/techniques/self-consistency.md` |

---

## Модели YandexGPT

| Модель | Описание |
|--------|----------|
| `yandexgpt` | Основная модель |
| `yandexgpt-lite` | Быстрая модель |
| `yandexgpt-32k` | Расширенный контекст |

**Документация:** `ai-studio/concepts/generation/models.md`

---

## Проверка перед разработкой

При разработке AI-ассистента **ОБЯЗАТЕЛЬНО**:

1. ✅ Прочитать соответствующую документацию в `yandex-ai-docs/`
2. ✅ Проверить актуальные методы API
3. ✅ Проверить лимиты: `ai-studio/concepts/limits.md`
4. ✅ Использовать правильную авторизацию
5. ✅ Проверить примеры в `ai-studio/tutorials/`

---

## Глоссарий

При непонятных терминах — смотреть `glossary/`:

| Термин | Файл |
|--------|------|
| LLM | `glossary/llm.md` |
| MCP | `glossary/mcp.md` |
| Чат-бот | `glossary/chat-bot.md` |
| gRPC | `glossary/grpc.md` |
| REST API | `glossary/rest-api.md` |
| JWT | `glossary/jwt.md` |

---

## Примеры и туториалы

| Туториал | Файл |
|----------|------|
| AI-ассистент с RAG | `ai-studio/tutorials/pdf-searchindex-ai-assistant.md` |
| Агент с function calling | `ai-studio/tutorials/create-ai-agent-function.md` |
| Telegram-бот | `ai-studio/tutorials/tg-bot-assistant.md` |
| Стриминг агент | `ai-studio/tutorials/streaming-openai-agent.md` |
| Интеграция с IDE | `ai-studio/tutorials/ai-model-ide-integration.md` |

---

## OpenAI-совместимость

Yandex AI Studio поддерживает OpenAI-совместимый API:

**Документация:** `ai-studio/concepts/openai-compatibility.md`

Можно использовать OpenAI SDK с Yandex endpoint.

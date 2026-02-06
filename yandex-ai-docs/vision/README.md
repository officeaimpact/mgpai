# Vision Documentation — OCR

Распознавание текста из изображений и PDF для AI-агентов.

## Структура папки (33 файла)

```
vision/
├── quickstart.md                       # Быстрый старт
├── pricing.md                          # Цены
│
├── concepts/
│   ├── ocr/
│   │   ├── index.md                    # О сервисе OCR ⭐
│   │   ├── supported-languages.md      # Поддерживаемые языки
│   │   ├── template-recognition.md     # Шаблонные документы
│   │   └── known-issues.md             # Известные проблемы
│   ├── classification/
│   │   ├── index.md                    # Классификация изображений
│   │   └── supported-models.md         # Модели классификации
│   └── limits.md                       # Лимиты
│
├── ocr/
│   └── api-ref/
│       ├── index.md                    # Обзор OCR API
│       ├── TextRecognition/            # Синхронное распознавание
│       │   ├── index.md
│       │   └── recognize.md
│       ├── TextRecognitionAsync/       # Асинхронное распознавание
│       │   ├── index.md
│       │   ├── recognize.md
│       │   └── getRecognition.md
│       └── Operation/
│
├── operations/
│   ├── index.md                        # Обзор операций
│   ├── base64-encode.md                # Кодирование в base64
│   ├── sa-api-key.md                   # Авторизация
│   ├── ocr/
│   │   ├── text-detection-image.md     # Распознавание с изображения ⭐
│   │   ├── text-detection-pdf.md       # Распознавание из PDF
│   │   ├── text-detection-table.md     # Распознавание таблиц
│   │   ├── text-detection-handwritten.md # Рукописный текст
│   │   └── text-detection-single-line.md # Одна строка
│   └── classification/
│       ├── moderation.md               # Модерация изображений
│       └── quality.md                  # Оценка качества
│
├── api-ref/
│   ├── authentication.md               # Авторизация API
│   ├── errors-handling.md              # Обработка ошибок
│   └── support-headers.md              # Заголовки
│
├── security/
│   └── index.md                        # Безопасность
│
└── qa/
    └── index.md                        # FAQ
```

---

## Детальное описание ключевых файлов

### `concepts/ocr/index.md` — О сервисе OCR ⭐

**Когда использовать:** Для понимания возможностей OCR.

**Что это:**
OCR (Optical Character Recognition) — распознавание текста на изображениях и в PDF-файлах.

**Режимы работы:**
| Режим | Описание | Когда использовать |
|-------|----------|-------------------|
| Синхронный | Мгновенный результат | Небольшие изображения |
| Асинхронный | Через операцию | Большие PDF, много страниц |

**Модели распознавания:**

| Модель | Описание | Когда использовать |
|--------|----------|-------------------|
| `page` | Обычный текст | По умолчанию |
| `page-column-sort` | Многоколоночный текст | Газеты, журналы |
| `handwritten` | Рукописный текст | Рукописные документы |
| `table` | Таблицы | Документы с таблицами |
| `markdown` | Возвращает Markdown ⭐ | Для AI-обработки |
| `math-markdown` | Формулы в LaTeX | Математические документы |

**Модель `markdown` — рекомендуется для AI:**
- Возвращает текст в формате Markdown
- Удобно для передачи в LLM
- Сохраняет структуру документа

---

### `operations/ocr/text-detection-image.md` — Распознавание с изображения ⭐

**Когда использовать:** Пошаговая инструкция распознавания текста.

**Шаги:**
1. Кодировать изображение в base64
2. Отправить запрос к OCR API
3. Получить распознанный текст

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Api-Key <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "mimeType": "image/jpeg",
    "languageCodes": ["ru", "en"],
    "model": "page",
    "content": "<base64_encoded_image>"
  }' \
  "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
```

---

### `operations/ocr/text-detection-pdf.md` — Распознавание из PDF

**Когда использовать:** Для извлечения текста из PDF-документов.

**Особенности:**
- Асинхронный режим для больших файлов
- Поддержка многостраничных документов
- Возможность указать диапазон страниц

---

### `operations/ocr/text-detection-table.md` — Распознавание таблиц

**Когда использовать:** Для извлечения структурированных данных из таблиц.

**Модель:** `table`

**Особенности:**
- Сохраняет структуру таблицы
- Поддержка русского и английского языков

---

### `operations/ocr/text-detection-handwritten.md` — Рукописный текст

**Когда использовать:** Для распознавания рукописных документов.

**Модель:** `handwritten`

**Особенности:**
- Поддержка смешанного текста (печатный + рукописный)
- Русский и английский языки

---

### `operations/base64-encode.md` — Кодирование в base64

**Когда использовать:** Подготовка изображений для API.

**Python:**
```python
import base64

with open("image.jpg", "rb") as f:
    encoded = base64.b64encode(f.read()).decode()
```

---

### `concepts/classification/index.md` — Классификация изображений

**Когда использовать:** Для модерации или оценки качества изображений.

**Модели:**
| Модель | Описание |
|--------|----------|
| `moderation` | Определение взрослого контента |
| `quality` | Оценка качества изображения |

**Примечание:** Есть `deprecation-warning`, но пока работает.

---

## Интеграция с AI-агентом

### Сценарий: Анализ документов

```python
import base64
import requests
from yandex_ai_studio_sdk import AIStudio

# 1. Распознать текст с изображения
with open("document.jpg", "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

ocr_response = requests.post(
    "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
    headers={
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "mimeType": "image/jpeg",
        "languageCodes": ["ru", "en"],
        "model": "markdown",  # Markdown для AI
        "content": image_base64
    }
)

extracted_text = ocr_response.json()["result"]["textAnnotation"]["fullText"]

# 2. Передать в LLM для анализа
sdk = AIStudio(folder_id="...", auth=api_key)
model = sdk.models.completions("yandexgpt")
result = model.run(f"Проанализируй этот документ:\n\n{extracted_text}")
print(result[0].text)
```

---

## Типичные сценарии

### Извлечение текста из документов для RAG
1. Загрузить изображение/PDF
2. Распознать текст через OCR (модель `markdown`)
3. Загрузить текст в Vector Store
4. Использовать в RAG-сценарии

### Анализ изображений в чат-боте
1. Пользователь отправляет фото
2. OCR извлекает текст
3. LLM анализирует и отвечает

### Модерация контента
1. Пользователь загружает изображение
2. Classification API проверяет на взрослый контент
3. При необходимости — блокировка

---

## Выбор модели OCR

| Тип документа | Модель |
|---------------|--------|
| Обычный текст | `page` |
| Многоколоночный | `page-column-sort` |
| Рукописный | `handwritten` |
| Таблицы | `table` |
| **Для AI-агента** | `markdown` ⭐ |
| Формулы | `math-markdown` |

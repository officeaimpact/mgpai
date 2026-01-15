# DEBUG BUNDLE — Заметки

## 📋 Назначение

Этот бандл содержит диагностические данные для воспроизведения и анализа диалогов с ИИ-ассистентом.

## 📁 Структура

```
debug_bundle/
├── LOGS/           # JSONL логи всех событий
│   └── app.jsonl   # Главный лог-файл (turn events + API traces)
├── API_TRACES/     # Экспортированные трассировки Tourvisor API
│   └── trace_<conversation_id>.json
├── CASES/          # Экспортированные диалоги
│   └── case_<conversation_id>.json
├── NOTES.md        # Этот файл
└── SCENARIOS.md    # Сценарии тестирования
```

## 🔧 Включение логирования

Логирование **отключено по умолчанию**. Для включения:

```bash
export DEBUG_LOGS=1
uvicorn app.main:app --reload
```

Или в `.env`:
```
DEBUG_LOGS=1
```

## 📊 Формат логов (app.jsonl)

### Turn Event (каждое сообщение)
```json
{
  "type": "turn",
  "conversation_id": "abc-123",
  "turn_id": 1,
  "timestamp": "2026-01-13T12:00:00.000Z",
  "user_text": "Хочу в Египет",
  "assistant_text": "Из какого города вылетаете?",
  "detected_intent": "search_tour",
  "search_mode": "package",
  "cascade_stage": 2,
  "missing_params": ["departure_city"],
  "search_params": {"destination_country": "египет"},
  "last_question_type": "departure"
}
```

### API Trace Event (каждый вызов Tourvisor)
```json
{
  "type": "api_trace",
  "conversation_id": "abc-123",
  "turn_id": 1,
  "timestamp": "2026-01-13T12:00:01.000Z",
  "endpoint": "search.php",
  "request_params": {"country": 1, "departure": 1},
  "status_code": 200,
  "elapsed_ms": 1523,
  "result_count": 15,
  "error": null,
  "response_summary": "requestid=ABC123, found tours"
}
```

## 🔐 Безопасность

- **Секреты НЕ логируются**: authlogin, authpass, api_key — маскируются
- Файлы .jsonl **НЕ коммитятся** в git (добавьте в .gitignore)

## 📤 Экспорт

```bash
python debug_bundle/export_traces.py
```

Это сгруппирует логи по conversation_id и создаст:
- `CASES/case_<id>.json` — диалог (messages + metadata)
- `API_TRACES/trace_<id>.json` — все API вызовы

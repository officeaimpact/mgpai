#!/usr/bin/env python3
"""
Export Traces Script
====================

Читает debug_bundle/LOGS/app.jsonl, группирует по conversation_id и экспортирует:
- debug_bundle/CASES/case_<conversation_id>.json (диалог: сообщения + метаданные)
- debug_bundle/API_TRACES/trace_<conversation_id>.json (все Tourvisor API события)

Использование:
    python debug_bundle/export_traces.py
    
    # Экспорт только конкретной сессии
    python debug_bundle/export_traces.py --conversation-id abc-123
    
    # Вывод сводки без экспорта
    python debug_bundle/export_traces.py --summary-only

Автор: MGP AI Team
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# Пути
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR / "LOGS"
CASES_DIR = SCRIPT_DIR / "CASES"
API_TRACES_DIR = SCRIPT_DIR / "API_TRACES"
LOG_FILE = LOGS_DIR / "app.jsonl"


def read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    """Чтение JSONL файла."""
    if not file_path.exists():
        print(f"❌ Файл не найден: {file_path}")
        return []
    
    events = []
    line_num = 0
    errors = 0
    
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_num += 1
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError as e:
                errors += 1
                if errors <= 5:
                    print(f"⚠️ Ошибка парсинга строки {line_num}: {e}")
    
    if errors > 5:
        print(f"⚠️ ... и ещё {errors - 5} ошибок парсинга")
    
    return events


def group_by_conversation(events: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """
    Группировка событий по conversation_id.
    
    Returns:
        dict: {
            conversation_id: {
                "turns": [...],
                "api_traces": [...],
                "errors": [...]
            }
        }
    """
    grouped = defaultdict(lambda: {
        "turns": [],
        "api_traces": [],
        "errors": []
    })
    
    for event in events:
        conv_id = event.get("conversation_id", "unknown")
        event_type = event.get("type", "unknown")
        
        if event_type == "turn":
            grouped[conv_id]["turns"].append(event)
        elif event_type == "api_trace":
            grouped[conv_id]["api_traces"].append(event)
        elif event_type == "error":
            grouped[conv_id]["errors"].append(event)
        else:
            # Неизвестный тип — в api_traces
            grouped[conv_id]["api_traces"].append(event)
    
    return dict(grouped)


def export_case(conv_id: str, data: dict[str, list[dict]], output_dir: Path) -> Path:
    """
    Экспорт диалога в CASES/case_<conversation_id>.json
    
    Args:
        conv_id: ID диалога
        data: {"turns": [...], "api_traces": [...], "errors": [...]}
        output_dir: Директория для сохранения
        
    Returns:
        Path: Путь к созданному файлу
    """
    turns = data["turns"]
    errors = data["errors"]
    
    # Сортируем по turn_id
    turns_sorted = sorted(turns, key=lambda x: (x.get("turn_id", 0), x.get("timestamp", "")))
    
    # Формируем структуру case
    case = {
        "conversation_id": conv_id,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_turns": len(turns_sorted),
            "total_errors": len(errors),
            "first_message": turns_sorted[0].get("timestamp") if turns_sorted else None,
            "last_message": turns_sorted[-1].get("timestamp") if turns_sorted else None,
        },
        "messages": [],
        "metadata_per_turn": []
    }
    
    for turn in turns_sorted:
        # Сообщения
        case["messages"].append({
            "turn_id": turn.get("turn_id"),
            "user": turn.get("user_text"),
            "assistant": turn.get("assistant_text")
        })
        
        # Метаданные
        case["metadata_per_turn"].append({
            "turn_id": turn.get("turn_id"),
            "timestamp": turn.get("timestamp"),
            "search_mode": turn.get("search_mode"),
            "cascade_stage": turn.get("cascade_stage"),
            "search_params": turn.get("search_params"),
            "missing_params": turn.get("missing_params"),
            "detected_intent": turn.get("detected_intent"),
            "last_question_type": turn.get("last_question_type"),
            "extra": turn.get("extra")
        })
    
    # Добавляем ошибки если есть
    if errors:
        case["errors"] = errors
    
    # Записываем файл
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"case_{conv_id}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    
    return output_path


def export_api_trace(conv_id: str, data: dict[str, list[dict]], output_dir: Path) -> Path:
    """
    Экспорт API трассировки в API_TRACES/trace_<conversation_id>.json
    
    Args:
        conv_id: ID диалога
        data: {"turns": [...], "api_traces": [...], "errors": [...]}
        output_dir: Директория для сохранения
        
    Returns:
        Path: Путь к созданному файлу
    """
    api_traces = data["api_traces"]
    
    # Сортируем по timestamp
    traces_sorted = sorted(api_traces, key=lambda x: x.get("timestamp", ""))
    
    # Статистика
    total_calls = len(traces_sorted)
    total_errors = sum(1 for t in traces_sorted if t.get("error"))
    total_elapsed = sum(t.get("elapsed_ms", 0) for t in traces_sorted)
    
    endpoints_count = defaultdict(int)
    for t in traces_sorted:
        endpoints_count[t.get("endpoint", "unknown")] += 1
    
    # Формируем структуру trace
    trace = {
        "conversation_id": conv_id,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_api_calls": total_calls,
            "total_errors": total_errors,
            "total_elapsed_ms": round(total_elapsed, 2),
            "avg_elapsed_ms": round(total_elapsed / total_calls, 2) if total_calls > 0 else 0,
            "endpoints": dict(endpoints_count)
        },
        "traces": traces_sorted
    }
    
    # Записываем файл
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"trace_{conv_id}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
    
    return output_path


def print_summary(grouped: dict[str, dict[str, list[dict]]]) -> None:
    """Вывод сводки по логам."""
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    total_conversations = len(grouped)
    total_turns = sum(len(d["turns"]) for d in grouped.values())
    total_api_calls = sum(len(d["api_traces"]) for d in grouped.values())
    total_errors = sum(len(d["errors"]) for d in grouped.values())
    total_api_errors = sum(
        1 for d in grouped.values() 
        for t in d["api_traces"] 
        if t.get("error")
    )
    
    print(f"   Диалогов (conversation_id): {total_conversations}")
    print(f"   Сообщений (turns): {total_turns}")
    print(f"   API вызовов: {total_api_calls}")
    print(f"   Ошибок (error events): {total_errors}")
    print(f"   API ошибок: {total_api_errors}")
    
    if grouped:
        print("\n📝 Диалоги:")
        for conv_id, data in sorted(grouped.items(), key=lambda x: len(x[1]["turns"]), reverse=True)[:10]:
            turns = len(data["turns"])
            api_calls = len(data["api_traces"])
            errors = len(data["errors"]) + sum(1 for t in data["api_traces"] if t.get("error"))
            print(f"   {conv_id}: {turns} turns, {api_calls} API calls, {errors} errors")
        
        if total_conversations > 10:
            print(f"   ... и ещё {total_conversations - 10} диалогов")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Экспорт диагностических логов")
    parser.add_argument(
        "--conversation-id", "-c",
        type=str,
        help="Экспортировать только конкретный диалог"
    )
    parser.add_argument(
        "--summary-only", "-s",
        action="store_true",
        help="Только вывести сводку, без экспорта"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(LOG_FILE),
        help=f"Путь к JSONL файлу (по умолчанию: {LOG_FILE})"
    )
    
    args = parser.parse_args()
    
    print("🔍 Export Traces Script")
    print(f"   Источник: {args.input}")
    
    # Читаем логи
    log_path = Path(args.input)
    events = read_jsonl(log_path)
    
    if not events:
        print("❌ Нет событий для обработки")
        sys.exit(1)
    
    print(f"   Загружено событий: {len(events)}")
    
    # Группируем по conversation_id
    grouped = group_by_conversation(events)
    
    # Фильтруем если указан конкретный conversation_id
    if args.conversation_id:
        if args.conversation_id in grouped:
            grouped = {args.conversation_id: grouped[args.conversation_id]}
        else:
            print(f"❌ Диалог не найден: {args.conversation_id}")
            print(f"   Доступные ID: {list(grouped.keys())[:10]}")
            sys.exit(1)
    
    # Выводим сводку
    print_summary(grouped)
    
    # Экспортируем если не только сводка
    if not args.summary_only:
        print("\n📤 Экспорт...")
        
        cases_exported = 0
        traces_exported = 0
        
        for conv_id, data in grouped.items():
            # Экспорт case (диалог)
            if data["turns"]:
                case_path = export_case(conv_id, data, CASES_DIR)
                cases_exported += 1
                print(f"   ✅ {case_path}")
            
            # Экспорт API trace
            if data["api_traces"]:
                trace_path = export_api_trace(conv_id, data, API_TRACES_DIR)
                traces_exported += 1
                print(f"   ✅ {trace_path}")
        
        print(f"\n✅ Экспортировано:")
        print(f"   Cases: {cases_exported}")
        print(f"   API Traces: {traces_exported}")
    
    print("\n✅ Готово!")


if __name__ == "__main__":
    main()

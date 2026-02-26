#!/usr/bin/env python3
"""Migration test: gpt-4.1-mini comprehensive testing"""

import requests
import time
import json
import sys

BASE = "http://localhost:8080/api/v1/chat"

def chat(conv_id: str, message: str) -> dict:
    start = time.time()
    r = requests.post(BASE, json={"message": message, "conversation_id": conv_id})
    elapsed = time.time() - start
    data = r.json()
    return {
        "reply": data.get("reply", ""),
        "cards": len(data.get("tour_cards", [])),
        "time": round(elapsed, 1),
        "tour_cards": data.get("tour_cards", []),
    }

def run_test(name, conv_id, steps):
    print(f"\n{'='*60}")
    print(f"ТЕСТ: {name}")
    print(f"{'='*60}")
    issues = []
    for i, (msg, checks) in enumerate(steps, 1):
        print(f"\n  --- Шаг {i} ---")
        print(f"  USER: {msg}")
        result = chat(conv_id, msg)
        print(f"  REPLY ({result['time']}s): {result['reply']}")
        print(f"  CARDS: {result['cards']}")
        
        for check_name, check_fn in checks.items():
            passed = check_fn(result)
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
            if not passed:
                issues.append(f"{name} шаг {i}: {check_name}")
    return issues

all_issues = []

# T1: Каскадный тест
issues = run_test("T1: Каскад (Турция, из Москвы)", "t1-cascade", [
    ("Привет! Хочу в Турцию из Москвы", {
        "нет карточек": lambda r: r["cards"] == 0,
        "ответ < 300 символов": lambda r: len(r["reply"]) < 300,
        "не спрашивает направление": lambda r: "направлен" not in r["reply"].lower() and "стран" not in r["reply"].lower(),
    }),
    ("в начале июня на 7 ночей", {
        "нет карточек": lambda r: r["cards"] == 0,
        "спрашивает состав/звёзды": lambda r: any(w in r["reply"].lower() for w in ["взросл", "человек", "едет", "путешеств", "звёзд", "звезд", "питан"]),
    }),
    ("двое взрослых", {
        "нет карточек": lambda r: r["cards"] == 0,
        "спрашивает звёзды или питание": lambda r: any(w in r["reply"].lower() for w in ["звёзд", "звезд", "питан", "категори"]),
    }),
    ("4-5 звезд, все включено", {
        "есть карточки": lambda r: r["cards"] > 0,
        "ответ < 300 символов": lambda r: len(r["reply"]) < 300,
        "нет дублирования карточек": lambda r: not any(w in r["reply"].lower() for w in ["rixos", "delphin", "₽", "руб", "uai", " ai "]),
    }),
])
all_issues.extend(issues)

# T2: Полный запрос за 1 шаг
issues = run_test("T2: Полный запрос (одно сообщение)", "t2-full", [
    ("Турция, Москва, 10 июня на 7 ночей, двое взрослых, 5 звезд, всё включено", {
        "есть карточки": lambda r: r["cards"] > 0,
        "ответ < 300 символов": lambda r: len(r["reply"]) < 300,
        "нет дублирования карточек": lambda r: not any(w in r["reply"].lower() for w in ["₽", "руб"]),
        "время < 25с": lambda r: r["time"] < 25,
    }),
    ("Расскажи подробнее о первом отеле", {
        "ответ содержательный": lambda r: len(r["reply"]) > 50,
        "ответ < 700 символов": lambda r: len(r["reply"]) < 700,
    }),
])
all_issues.extend(issues)

# T3: Горящие туры
issues = run_test("T3: Горящие туры (Египет)", "t3-hot", [
    ("Покажи горящие туры в Египет", {
        "упоминает цены за человека": lambda r: "за человека" in r["reply"].lower() or "за чел" in r["reply"].lower(),
        "упоминает фиксированные даты": lambda r: "фиксирован" in r["reply"].lower(),
        "ответ < 500 символов": lambda r: len(r["reply"]) < 500,
    }),
])
all_issues.extend(issues)

# T4: Россия без перелёта
issues = run_test("T4: Россия (Сочи без перелёта)", "t4-russia", [
    ("Сочи без перелёта, в конце мая, 5 ночей, 2 взрослых и ребёнок 5 лет, 3 звезды, завтраки", {
        "есть карточки": lambda r: r["cards"] > 0,
        "ответ < 300 символов": lambda r: len(r["reply"]) < 300,
        "нет дублирования карточек": lambda r: not any(w in r["reply"].lower() for w in ["₽", "руб"]),
    }),
])
all_issues.extend(issues)

# T5: Эмодзи в обычном режиме (формальный запрос)
issues = run_test("T5: Формальный запрос (без эмодзи)", "t5-formal", [
    ("Добрый день! Подскажите, пожалуйста, варианты отдыха в Египте из Санкт-Петербурга", {
        "нет карточек": lambda r: r["cards"] == 0,
        "ответ < 300 символов": lambda r: len(r["reply"]) < 300,
    }),
])
all_issues.extend(issues)

# T6: Даты — «в начале марта»
issues = run_test("T6: Даты (в начале марта)", "t6-dates", [
    ("Хочу в Турцию из Москвы в начале марта на 10 дней, я один, 4 звезды, завтраки", {
        "есть карточки или уточнение": lambda r: r["cards"] > 0 or len(r["reply"]) > 20,
    }),
])
all_issues.extend(issues)

# T7: Конкретный отель
issues = run_test("T7: Конкретный отель (Rixos)", "t7-hotel", [
    ("Хочу в Rixos Premium Belek, из Москвы, в июне на 7 ночей, двое взрослых, все включено", {
        "есть карточки или поиск": lambda r: r["cards"] > 0 or len(r["reply"]) > 20,
    }),
])
all_issues.extend(issues)

# T8: Актуализация (если есть карточки от T2)
issues = run_test("T8: Актуализация тура", "t2-full", [
    ("Актуализируй первый вариант", {
        "ответ содержательный": lambda r: len(r["reply"]) > 30,
    }),
])
all_issues.extend(issues)

# T9: Детали рейса
issues = run_test("T9: Детали рейса", "t2-full", [
    ("Покажи детали рейса для первого варианта", {
        "ответ содержательный": lambda r: len(r["reply"]) > 30,
    }),
])
all_issues.extend(issues)

# T10: Ещё варианты
issues = run_test("T10: Ещё варианты", "t2-full", [
    ("Покажи ещё варианты", {
        "ответ есть": lambda r: len(r["reply"]) > 10,
    }),
])
all_issues.extend(issues)

print(f"\n{'='*60}")
print(f"ИТОГО")
print(f"{'='*60}")
if all_issues:
    print(f"\n❌ Найдено проблем: {len(all_issues)}")
    for issue in all_issues:
        print(f"  - {issue}")
else:
    print("\n✅ Все проверки пройдены!")

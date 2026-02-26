#!/usr/bin/env python3
"""Full migration test suite: gpt-4.1-mini with prompt reinforcements (25 tests)"""

import requests
import time
import json
import re

BASE = "http://localhost:8080/api/v1/chat"
RESULTS = []

def chat(conv_id, msg):
    s = time.time()
    r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=120)
    d = r.json()
    return {
        "reply": d.get("reply", ""),
        "cards": len(d.get("tour_cards", [])),
        "time": round(time.time() - s, 1),
    }

def test(name, conv_id, steps):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    issues = []
    for i, (msg, checks) in enumerate(steps, 1):
        print(f"\n  Step {i}: USER: {msg[:80]}")
        result = chat(conv_id, msg)
        print(f"  REPLY ({result['time']}s, {len(result['reply'])}ch, {result['cards']}cards):")
        print(f"    {result['reply'][:200]}")
        if len(result['reply']) > 200:
            print(f"    ...({len(result['reply'])} total)")
        for check_name, check_fn in checks.items():
            ok = check_fn(result)
            print(f"  {'PASS' if ok else 'FAIL'} {check_name}")
            if not ok:
                issues.append(f"{name} step {i}: {check_name}")
    RESULTS.append({"name": name, "issues": issues})
    return issues

def no_date_confirm(r):
    bad = ["верно?", "правильно?", "с 1 по", "с 10 по", "с 20 по", "это примерно"]
    return not any(b in r["reply"].lower() for b in bad)

def no_param_echo(r):
    bad = ["вы выбрали", "ваш запрос:", "вы указали", "параметры:"]
    return not any(b in r["reply"].lower() for b in bad)

def no_card_dup(r):
    bad_patterns = ["₽", "руб.", "руб ", "рублей"]
    return not any(b in r["reply"].lower() for b in bad_patterns)

all_issues = []

# ═══ GROUP A: CASCADE (5 tests) ═══

issues = test("A1: Каскад Турция из Москвы", "a1", [
    ("Привет! Хочу в Турцию из Москвы", {
        "no cards": lambda r: r["cards"] == 0,
        "< 300 chars": lambda r: len(r["reply"]) < 300,
    }),
    ("в начале июня на 7 ночей", {
        "no cards": lambda r: r["cards"] == 0,
        "NO date confirmation": no_date_confirm,
        "asks composition": lambda r: any(w in r["reply"].lower() for w in ["взросл", "человек", "едет", "путешеств", "состав"]),
    }),
    ("двое взрослых", {
        "no cards": lambda r: r["cards"] == 0,
        "asks QC": lambda r: any(w in r["reply"].lower() for w in ["звёзд", "звезд", "питан", "категори"]),
    }),
    ("4-5 звезд, все включено", {
        "has cards or search": lambda r: r["cards"] > 0 or "нашёл" in r["reply"].lower() or "найд" in r["reply"].lower() or "не найд" in r["reply"].lower(),
        "< 300 chars": lambda r: len(r["reply"]) < 300,
        "NO card duplication": no_card_dup,
    }),
])
all_issues.extend(issues)

issues = test("A2: Египет Шарм середина апреля", "a2", [
    ("Хочу в Египет, Шарм-эль-Шейх, из Москвы, середина апреля, 10 ночей, двое взрослых, 5 звезд, ультра все включено", {
        "NO date confirmation": no_date_confirm,
        "NO param echo": no_param_echo,
        "search initiated": lambda r: r["cards"] > 0 or r["time"] > 5,
    }),
])
all_issues.extend(issues)

issues = test("A3: Неформальный стиль", "a3", [
    ("бро, хочу на пляж в турцию)))", {
        "no cards": lambda r: r["cards"] == 0,
        "informal tone": lambda r: "планируешь" in r["reply"].lower() or "хочешь" in r["reply"].lower() or "когда" in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

issues = test("A4: One-shot полный запрос", "a4", [
    ("Турция, Москва, начало июня, 7 ночей, 2 взрослых, 4 звезды, все включено", {
        "NO param echo": no_param_echo,
        "NO date confirmation": no_date_confirm,
        "search happens": lambda r: r["cards"] > 0 or r["time"] > 5,
    }),
])
all_issues.extend(issues)

issues = test("A5: Конфликтующие направления", "a5", [
    ("Хочу в Турцию, Сочи", {
        "asks clarification": lambda r: any(w in r["reply"].lower() for w in ["уточн", "интересует", "какой"]),
        "no cards": lambda r: r["cards"] == 0,
    }),
])
all_issues.extend(issues)

# ═══ GROUP B: SEARCH + CARDS (5 tests) ═══

issues = test("B1: Полный поиск 5* AI", "b1", [
    ("Турция, Москва, 15 июня на 7 ночей, двое взрослых, 5 звезд, всё включено", {
        "has cards": lambda r: r["cards"] > 0,
        "NO card duplication": no_card_dup,
        "< 300 chars": lambda r: len(r["reply"]) < 300,
    }),
])
all_issues.extend(issues)

issues = test("B2: Поиск без курорта (regions check)", "b2", [
    ("Египет из Москвы, 20 апреля, 10 ночей, двое, 4 звезды, полупансион", {
        "has cards or search": lambda r: r["cards"] > 0 or r["time"] > 5,
    }),
])
all_issues.extend(issues)

issues = test("B3: Россия без перелёта + ребёнок", "b3", [
    ("Сочи без перелёта, в конце мая, 5 ночей, 2 взрослых и ребёнок 5 лет, 3 звезды, завтраки", {
        "has cards": lambda r: r["cards"] > 0,
        "< 300 chars": lambda r: len(r["reply"]) < 300,
    }),
])
all_issues.extend(issues)

issues = test("B4: Skip QC — любое питание", "b4", [
    ("Турция из Москвы, 10 июня, 7 ночей, двое взрослых, 4 звезды", {
        "asks meal": lambda r: "питан" in r["reply"].lower(),
    }),
    ("любое питание", {
        "has cards": lambda r: r["cards"] > 0,
    }),
])
all_issues.extend(issues)

issues = test("B5: Ещё варианты", "b1", [
    ("Покажи ещё варианты", {
        "response exists": lambda r: len(r["reply"]) > 10,
    }),
])
all_issues.extend(issues)

# ═══ GROUP C: HOT TOURS (3 tests) ═══

issues = test("C1: Горящие Турция из Москвы", "c1", [
    ("Покажи горящие туры в Турцию из Москвы", {
        "per-person pricing": lambda r: "за человека" in r["reply"].lower(),
        "fixed dates": lambda r: "фиксирован" in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

issues = test("C2: Горящие — несуществующее направление", "c2", [
    ("Горящие туры на Мальдивы из Казани", {
        "honest response": lambda r: "нет" in r["reply"].lower() or "не нашёл" in r["reply"].lower() or "не найд" in r["reply"].lower() or "к сожалению" in r["reply"].lower() or "город" in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

issues = test("C3: Горящие без города вылета", "c3", [
    ("Покажи горящие туры в Египет", {
        "asks departure": lambda r: any(w in r["reply"].lower() for w in ["город", "вылет", "откуда"]),
    }),
])
all_issues.extend(issues)

# ═══ GROUP D: CONSULTATION (5 tests) ═══

issues = test("D1: Подробнее об отеле (после B1)", "b1", [
    ("Расскажи подробнее о первом отеле", {
        "substantive": lambda r: len(r["reply"]) > 50,
        "< 700 chars": lambda r: len(r["reply"]) < 700,
    }),
])
all_issues.extend(issues)

issues = test("D2: Актуализация (после B1)", "b1", [
    ("Актуализируй первый вариант", {
        "substantive": lambda r: len(r["reply"]) > 30,
        "mentions price": lambda r: "₽" in r["reply"] or "руб" in r["reply"].lower() or "стоимость" in r["reply"].lower() or "цена" in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

issues = test("D3: Детали рейса (detailavailable check)", "b1", [
    ("Покажи детали рейса для этого тура", {
        "substantive": lambda r: len(r["reply"]) > 30,
    }),
])
all_issues.extend(issues)

issues = test("D5: Конкретный отель Rixos", "d5", [
    ("Хочу в Rixos Premium Belek, из Москвы, в июне на 7 ночей, двое взрослых, все включено", {
        "response exists": lambda r: len(r["reply"]) > 10,
    }),
])
all_issues.extend(issues)

# ═══ GROUP E: EDGE CASES (5 tests) ═══

issues = test("E1: Праздник — майские", "e1", [
    ("На майские из Питера, 7 ночей, двое, 4 звезды, все включено", {
        "asks specific dates": lambda r: any(w in r["reply"].lower() for w in ["дат", "когда", "удобн", "майск", "апрел"]),
    }),
])
all_issues.extend(issues)

issues = test("E2: Ребёнок без возраста", "e2", [
    ("Турция из Москвы, июнь, 7 ночей, 2 взрослых и ребёнок, 4 звезды, AI", {
        "asks child age": lambda r: any(w in r["reply"].lower() for w in ["возраст", "сколько лет", "лет ребён"]),
    }),
])
all_issues.extend(issues)

issues = test("E3: Формальный — без эмодзи", "e3", [
    ("Добрый день. Подскажите, пожалуйста, варианты отдыха в Турции из Санкт-Петербурга.", {
        "formal tone": lambda r: "вы" in r["reply"].lower() or "пожалуйста" in r["reply"].lower() or "планируете" in r["reply"].lower() or "когда" in r["reply"].lower(),
        "< 300 chars": lambda r: len(r["reply"]) < 300,
    }),
])
all_issues.extend(issues)

issues = test("E4: 0 результатов поиска", "e4", [
    ("Мальдивы из Казани, 1 марта, 3 ночи, 1 взрослый, 5 звезд, UAI", {
        "offers alternatives": lambda r: len(r["reply"]) > 20,
    }),
])
all_issues.extend(issues)

issues = test("E5: Длинный диалог", "e5", [
    ("Привет, хочу в Египет из Москвы", {"ok": lambda r: r["cards"] == 0}),
    ("в середине мая на 10 ночей", {"ok": lambda r: r["cards"] == 0}),
    ("двое взрослых и ребёнок 7 лет", {"ok": lambda r: r["cards"] == 0}),
    ("4 звезды, всё включено", {
        "has cards or search": lambda r: r["cards"] > 0 or r["time"] > 5,
    }),
    ("Расскажи про первый отель", {
        "substantive": lambda r: len(r["reply"]) > 50,
    }),
    ("А можно дешевле?", {
        "suggests alternatives": lambda r: len(r["reply"]) > 20,
    }),
])
all_issues.extend(issues)

# ═══ GROUP F: SPEED (2 tests) ═══

issues = test("F1: Скорость каскада", "f1", [
    ("Привет, хочу в Турцию из Москвы", {
        "< 5 seconds": lambda r: r["time"] < 5,
    }),
])
all_issues.extend(issues)

issues = test("F2: Скорость полного поиска", "f2", [
    ("Турция, Москва, 20 июня, 7 ночей, двое взрослых, 5 звезд, все включено", {
        "< 25 seconds": lambda r: r["time"] < 25,
        "has cards": lambda r: r["cards"] > 0,
    }),
])
all_issues.extend(issues)

# ═══ SUMMARY ═══

print(f"\n{'='*60}")
print("ИТОГО: РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
print(f"{'='*60}")

passed = sum(1 for r in RESULTS if not r["issues"])
failed = sum(1 for r in RESULTS if r["issues"])
total = len(RESULTS)

print(f"\nПройдено: {passed}/{total}")
print(f"С проблемами: {failed}/{total}")

if all_issues:
    print(f"\nВсе проблемы ({len(all_issues)}):")
    for issue in all_issues:
        print(f"  FAIL: {issue}")
else:
    print("\nВсе тесты пройдены!")

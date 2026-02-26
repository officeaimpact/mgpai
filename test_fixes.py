#!/usr/bin/env python3
"""Test suite: verify 5 fixes + 7 regression tests"""

import requests
import time

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
        print(f"    {result['reply'][:250]}")
        if len(result['reply']) > 250:
            print(f"    ...({len(result['reply'])} total)")
        for check_name, check_fn in checks.items():
            ok = check_fn(result)
            status = "PASS" if ok else "FAIL"
            print(f"  {status} {check_name}")
            if not ok:
                issues.append(f"{name} step {i}: {check_name}")
    RESULTS.append({"name": name, "issues": issues})
    return issues

all_issues = []

# ═══ FIX VERIFICATION (5 tests) ═══
print("\n" + "█"*60)
print("█  FIX VERIFICATION (5 tests)")
print("█"*60)

# Fix A: A1 cascade — model must NOT search, must ask QC
issues = test("FIX-A1: Каскад — НЕ искать без QC", "fix_a1", [
    ("Привет! Хочу в Турцию из Москвы", {
        "no cards": lambda r: r["cards"] == 0,
    }),
    ("в начале июня на 7 ночей", {
        "no cards": lambda r: r["cards"] == 0,
    }),
    ("двое взрослых", {
        "NO cards (must ask QC)": lambda r: r["cards"] == 0,
        "asks QC": lambda r: any(w in r["reply"].lower() for w in ["звёзд", "звезд", "питан", "категори"]),
    }),
    ("4 звезды, все включено", {
        "has cards": lambda r: r["cards"] > 0,
    }),
])
all_issues.extend(issues)

# Fix A: B4 — must ask meal before searching
issues = test("FIX-A2: 4 звезды без питания — спросить meal", "fix_b4", [
    ("Турция из Москвы, 10 июня, 7 ночей, двое взрослых, 4 звезды", {
        "NO cards (must ask meal)": lambda r: r["cards"] == 0,
        "asks meal": lambda r: "питан" in r["reply"].lower(),
    }),
    ("все включено", {
        "has cards": lambda r: r["cards"] > 0,
    }),
])
all_issues.extend(issues)

# Fix C: C3 — hot tours without departure must ask
issues = test("FIX-C: Горящие без города — спросить город", "fix_c3", [
    ("Покажи горящие туры в Египет", {
        "no cards": lambda r: r["cards"] == 0,
        "asks departure": lambda r: any(w in r["reply"].lower() for w in ["город", "вылет", "откуда"]),
    }),
])
all_issues.extend(issues)

# Fix B: F2 — must search immediately, not ask for resort
issues = test("FIX-B: One-shot — сразу искать, не спрашивать курорт", "fix_f2", [
    ("Турция, Москва, 20 июня, 7 ночей, двое взрослых, 5 звезд, все включено", {
        "has cards or long search": lambda r: r["cards"] > 0 or r["time"] > 8,
        "NO param echo": lambda r: not any(w in r["reply"].lower() for w in ["вы выбрали", "вы указали", "ваш запрос:"]),
        "NO asks resort": lambda r: "какой курорт" not in r["reply"].lower() and "какой регион" not in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

# Fix E: E4 — must complete pipeline to get_search_results
issues = test("FIX-E: Мальдивы — pipeline до get_search_results", "fix_e4", [
    ("Мальдивы из Казани, 1 марта, 3 ночи, 1 взрослый, 5 звезд, UAI", {
        "NO fake 'found'": lambda r: "нашёл варианты" not in r["reply"].lower() or r["cards"] > 0,
        "response exists": lambda r: len(r["reply"]) > 10,
    }),
])
all_issues.extend(issues)

# ═══ REGRESSION TESTS (7 tests) ═══
print("\n" + "█"*60)
print("█  REGRESSION TESTS (7 tests)")
print("█"*60)

# A2: One-shot Egypt Sharm
issues = test("REG-A2: One-shot Египет Шарм", "reg_a2", [
    ("Хочу в Египет, Шарм-эль-Шейх, из Москвы, середина апреля, 10 ночей, двое взрослых, 5 звезд, ультра все включено", {
        "has cards": lambda r: r["cards"] > 0,
        "NO param echo": lambda r: not any(w in r["reply"].lower() for w in ["вы выбрали", "вы указали"]),
        "NO date confirm": lambda r: "верно?" not in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

# A4: One-shot Turkey
issues = test("REG-A4: One-shot Турция", "reg_a4", [
    ("Турция, Москва, начало июня, 7 ночей, 2 взрослых, 4 звезды, все включено", {
        "has cards": lambda r: r["cards"] > 0,
        "NO param echo": lambda r: not any(w in r["reply"].lower() for w in ["вы выбрали", "вы указали"]),
    }),
])
all_issues.extend(issues)

# B1: Full search 5* AI
issues = test("REG-B1: Полный поиск 5* AI", "reg_b1", [
    ("Турция, Москва, 15 июня на 7 ночей, двое взрослых, 5 звезд, всё включено", {
        "has cards": lambda r: r["cards"] > 0,
        "NO card dup": lambda r: not any(w in r["reply"].lower() for w in ["₽", "руб.", "рублей"]),
        "< 300 chars": lambda r: len(r["reply"]) < 300,
    }),
])
all_issues.extend(issues)

# C1: Hot tours with results
issues = test("REG-C1: Горящие с результатами", "reg_c1", [
    ("Покажи горящие туры в Турцию из Москвы", {
        "has cards or honest": lambda r: r["cards"] > 0 or "нет" in r["reply"].lower() or "к сожалению" in r["reply"].lower(),
        "per-person price": lambda r: "за человека" in r["reply"].lower() or "к сожалению" in r["reply"].lower(),
    }),
])
all_issues.extend(issues)

# D3: Flight details
issues = test("REG-D3: Детали рейса", "reg_b1", [
    ("Расскажи подробнее о первом отеле", {"ok": lambda r: len(r["reply"]) > 30}),
    ("Актуализируй первый вариант", {"ok": lambda r: len(r["reply"]) > 30}),
    ("Покажи детали рейса для этого тура", {
        "substantive": lambda r: len(r["reply"]) > 30,
    }),
])
all_issues.extend(issues)

# E1: Holiday — must ask specific date
issues = test("REG-E1: Майские (праздник)", "reg_e1", [
    ("На майские из Питера, 7 ночей, двое, 4 звезды, все включено", {
        "asks date": lambda r: any(w in r["reply"].lower() for w in ["дат", "когда", "удобн", "майск"]),
    }),
])
all_issues.extend(issues)

# E5: Long dialogue — context preserved
issues = test("REG-E5: Длинный диалог", "reg_e5", [
    ("Привет, хочу в Египет из Москвы", {"ok": lambda r: r["cards"] == 0}),
    ("в середине мая на 10 ночей", {"ok": lambda r: r["cards"] == 0}),
    ("двое взрослых и ребёнок 7 лет", {
        "asks QC": lambda r: any(w in r["reply"].lower() for w in ["звёзд", "звезд", "питан", "категори"]),
    }),
    ("4 звезды, всё включено", {
        "has cards": lambda r: r["cards"] > 0,
    }),
    ("Расскажи про первый отель", {
        "substantive": lambda r: len(r["reply"]) > 50,
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

"""
Test: Prefetch ALL 5 tours — ask about 1st, 2nd, 3rd, 4th, 5th tour flights.
Each scenario is a fresh conversation with a different destination.
"""
import requests, time, uuid

BASE = "http://localhost:8080/api/v1/chat"

def chat(conv_id, msg):
    t0 = time.time()
    r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=180)
    elapsed = round(time.time() - t0, 1)
    data = r.json()
    return {
        "reply": data.get("reply", ""),
        "cards": data.get("tour_cards", []),
        "n_cards": len(data.get("tour_cards", [])),
        "time": elapsed,
    }

SCENARIOS = [
    {
        "name": "Турция — перелёт 1-го тура",
        "search": "хочу в турцию из москвы, 5 марта на неделю, 2 взрослых, 5 звезд все включено",
        "flight_q": "какой перелёт в первом варианте?",
        "tour_pos": 1,
    },
    {
        "name": "Египет — перелёт 2-го тура",
        "search": "египет из москвы, 20 марта на 7 ночей, 2 взрослых, 5 звезд все включено",
        "flight_q": "а какой перелёт во втором варианте?",
        "tour_pos": 2,
    },
    {
        "name": "ОАЭ — перелёт 3-го тура",
        "search": "оаэ из москвы, 10 апреля на 5 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "расскажи про перелёт в третьем варианте",
        "tour_pos": 3,
    },
    {
        "name": "Таиланд — перелёт 4-го тура",
        "search": "тайланд из москвы, начало мая на 10 ночей, 2 взрослых, 4 звезды",
        "flight_q": "какой перелёт в четвёртом варианте?",
        "tour_pos": 4,
    },
    {
        "name": "Сочи — перелёт 5-го тура",
        "search": "сочи из москвы, 15 июня на 7 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "а какой перелёт в пятом варианте?",
        "tour_pos": 5,
    },
]

print("=" * 70)
print("  ТЕСТ: PREFETCH ВСЕХ 5 ТУРОВ")
print("  Каждый сценарий спрашивает про разный тур (1-5)")
print("=" * 70)

results = []

for sc in SCENARIOS:
    conv_id = str(uuid.uuid4())
    print(f"\n{'='*65}")
    print(f"  Сценарий: {sc['name']}")
    print(f"{'='*65}")

    r = chat(conv_id, sc["search"])
    print(f"  Поиск ({r['time']}с, {r['n_cards']} карточек): {r['reply'][:100]}")

    if r["n_cards"] == 0:
        followups = ["любой район", "любое питание", "да, подбирайте"]
        for fu in followups:
            if r["n_cards"] > 0:
                break
            time.sleep(1)
            r = chat(conv_id, fu)
            print(f"  Уточнение: {fu} → ({r['time']}с, {r['n_cards']} карточек)")

    if r["n_cards"] == 0:
        print(f"  SKIP — карточки не получены")
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": "no_cards"})
        continue

    if r["n_cards"] < sc["tour_pos"]:
        print(f"  SKIP — получено {r['n_cards']} карточек, нужна позиция {sc['tour_pos']}")
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": f"only_{r['n_cards']}_cards"})
        continue

    for i, c in enumerate(r["cards"], 1):
        mark = " ← СПРОСИМ" if i == sc["tour_pos"] else ""
        print(f"    {i}. {c.get('hotelName','?')} | {c.get('price','?')}₽{mark}")

    print(f"\n  Ждём 20с для prefetch всех 5 туров...")
    time.sleep(20)

    print(f"  >>> Вопрос: {sc['flight_q']}")
    r_f = chat(conv_id, sc["flight_q"])
    print(f"  <<< Ответ ({r_f['time']}с): {r_f['reply'][:250]}")

    has_flight = any(w in r_f["reply"].lower() for w in [
        "рейс", "вылет", "авиа", "аэро", "прилёт", "прилет", "dp", "победа", "аэрофлот"
    ])
    has_manager = "менеджер" in r_f["reply"].lower() or "555-35-35" in r_f["reply"]

    results.append({
        "scenario": sc["name"],
        "tour_pos": sc["tour_pos"],
        "search_time": r["time"],
        "flight_time": r_f["time"],
        "has_flight": has_flight,
        "has_manager": has_manager,
        "status": "ok",
    })

print(f"\n{'='*70}")
print(f"  РЕЗУЛЬТАТЫ: PREFETCH ВСЕХ 5 ТУРОВ")
print(f"{'='*70}")
print(f"  {'Сценарий':<40} {'Позиция':>8} {'Время':>8} {'Статус'}")
print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*20}")

flight_times = []
for r in results:
    if r["status"] == "ok":
        tags = []
        if r.get("has_flight"): tags.append("рейс")
        if r.get("has_manager"): tags.append("менеджер")
        status_str = ", ".join(tags) if tags else "нет данных"
        print(f"  {r['scenario']:<40} {r['tour_pos']:>8} {r['flight_time']:>7}с {status_str}")
        flight_times.append(r["flight_time"])
    else:
        print(f"  {r['scenario']:<40} {r['tour_pos']:>8} {'—':>8} {r['status']}")

if flight_times:
    avg = round(sum(flight_times) / len(flight_times), 1)
    fast = [t for t in flight_times if t < 15]
    print(f"\n  Среднее время: {avg}с")
    print(f"  Быстрых (<15с): {len(fast)}/{len(flight_times)}")
    print(f"  Самый быстрый: {min(flight_times)}с")
    print(f"  Самый медленный: {max(flight_times)}с")

"""
Test: Parallel fallback + 2-tour prefetch speed improvement.
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
        "name": "Сочи из Москвы",
        "msg": "Хочу в Сочи из Москвы, 15 июня на 7 ночей, 2 взрослых, 4 звезды, завтрак",
        "flight_q": "какой перелёт в первом отеле?",
    },
    {
        "name": "Турция из Москвы (worst case тест)",
        "msg": "хочу в турцию из москвы, 5 марта на неделю, 2 взр, 5 звезд все включено",
        "flight_q": "а какой перелёт в первом варианте?",
    },
    {
        "name": "Египет из Москвы",
        "msg": "египет из москвы, 20 марта на 7 ночей, 2 взрослых, 5 звезд все включено",
        "flight_q": "какой перелёт в первом?",
    },
]

print("=" * 70)
print("  ТЕСТ: Параллельный fallback + 2-tour prefetch")
print("=" * 70)

results = []

for sc in SCENARIOS:
    conv_id = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"  {sc['name']}")
    print(f"{'='*60}")

    r = chat(conv_id, sc["msg"])
    print(f"  User: {sc['msg'][:80]}")
    print(f"  Bot ({r['time']}s, {r['n_cards']} cards): {r['reply'][:120]}")

    if r["n_cards"] == 0:
        print(f"  ⚠️ SKIP — no cards")
        results.append({"scenario": sc["name"], "flight_time": None})
        continue

    for c in r["cards"][:3]:
        print(f"    card: {c.get('hotelName','?')} | {c.get('price','?')}₽")

    print(f"  ... waiting 15s for prefetch ...")
    time.sleep(15)

    print(f"\n  >>> {sc['flight_q']}")
    r_f = chat(conv_id, sc["flight_q"])
    print(f"  <<< ({r_f['time']}s): {r_f['reply'][:250]}")

    has_flight = any(w in r_f["reply"].lower() for w in ["рейс", "вылет", "авиа", "аэро", "прилёт", "прилет"])
    has_manager = "менеджер" in r_f["reply"].lower() or "555-35-35" in r_f["reply"]

    results.append({
        "scenario": sc["name"],
        "search_time": r["time"],
        "flight_time": r_f["time"],
        "has_flight": has_flight,
        "has_manager": has_manager,
    })

print(f"\n{'='*70}")
print(f"  РЕЗУЛЬТАТЫ")
print(f"{'='*70}")
for r in results:
    if r.get("flight_time") is not None:
        tags = []
        if r.get("has_flight"): tags.append("рейс найден")
        if r.get("has_manager"): tags.append("менеджер указан")
        status = ", ".join(tags) if tags else "нет данных"
        print(f"  {r['scenario']}: поиск {r['search_time']}с, перелёт {r['flight_time']}с ({status})")
    else:
        print(f"  {r['scenario']}: ❌ карточки не получены")

flight_times = [r["flight_time"] for r in results if r.get("flight_time")]
if flight_times:
    print(f"\n  Среднее время перелёт: {round(sum(flight_times)/len(flight_times), 1)}с")
    print(f"  (было 47с worst-case, ожидаем ≤15с)")

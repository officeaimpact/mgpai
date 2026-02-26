"""
Test: Prefetch flight details — international destinations.
Measures time for flight question with and without cache hit.
"""
import requests, time, json, uuid

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
        "name": "Египет из Москвы",
        "msg": "хочу в египет из москвы, 20 марта на 7 ночей, 2 взрослых, 5 звезд все включено",
        "flight_q": "какой перелёт в первом отеле?",
    },
    {
        "name": "ОАЭ из Питера",
        "msg": "ОАЭ из Санкт-Петербурга, 10 апреля на 5 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "какой рейс в первом варианте?",
    },
    {
        "name": "Таиланд из Москвы",
        "msg": "тайланд из москвы, начало мая на 10 ночей, 2 взрослых, 4 звезды всё включено",
        "flight_q": "расскажи про перелёт в первом отеле",
    },
    {
        "name": "Мальдивы из Москвы",
        "msg": "мальдивы из москвы, июнь на неделю, 2 взрослых, 5 звезд",
        "flight_q": "а какой перелёт туда?",
    },
    {
        "name": "Абхазия из Москвы",
        "msg": "абхазия из москвы, июль на 7 ночей, 2 взрослых, 3 звезды все включено",
        "flight_q": "какой перелёт в первом?",
    },
]

print("=" * 70)
print("  ТЕСТ PREFETCH: МЕЖДУНАРОДНЫЕ НАПРАВЛЕНИЯ")
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
    got_cards = r["n_cards"] > 0
    if got_cards:
        for c in r["cards"][:2]:
            print(f"    card: {c.get('hotelName','?')} | {c.get('price','?')}₽")

    if not got_cards:
        # Try answering cascade questions
        followups = ["любой район", "любое питание", "да, подбирайте", "4 звезды всё включено"]
        for fu in followups:
            if got_cards:
                break
            time.sleep(1)
            r2 = chat(conv_id, fu)
            print(f"  User: {fu}")
            print(f"  Bot ({r2['time']}s, {r2['n_cards']} cards): {r2['reply'][:120]}")
            if r2["n_cards"] > 0:
                got_cards = True
                for c in r2["cards"][:2]:
                    print(f"    card: {c.get('hotelName','?')} | {c.get('price','?')}₽")

    if not got_cards:
        print(f"  ⚠️ SKIP — no cards")
        results.append({"scenario": sc["name"], "got_cards": False, "flight_time": None})
        continue

    # Wait for prefetch to complete
    print(f"  ... waiting 15s for prefetch ...")
    time.sleep(15)

    # Ask flight question
    print(f"\n  >>> {sc['flight_q']}")
    r_f = chat(conv_id, sc["flight_q"])
    print(f"  <<< ({r_f['time']}s): {r_f['reply'][:200]}")

    results.append({
        "scenario": sc["name"],
        "got_cards": True,
        "flight_time": r_f["time"],
        "reply_len": len(r_f["reply"]),
        "has_flight_info": any(w in r_f["reply"].lower() for w in ["рейс", "вылет", "авиа", "аэро", "прилёт", "прилет"]),
    })

print(f"\n{'='*70}")
print(f"  РЕЗУЛЬТАТЫ — МЕЖДУНАРОДНЫЕ НАПРАВЛЕНИЯ")
print(f"{'='*70}")
flight_times = []
for r in results:
    if r.get("flight_time") is not None:
        status = "✅" if r.get("has_flight_info") else "⚠️ нет данных"
        print(f"  {r['scenario']}: {r['flight_time']}с {status}")
        flight_times.append(r["flight_time"])
    else:
        print(f"  {r['scenario']}: ❌ карточки не получены")

if flight_times:
    avg = round(sum(flight_times) / len(flight_times), 1)
    fast = [t for t in flight_times if t < 20]
    print(f"\n  Среднее время: {avg}с")
    print(f"  Быстрых (<20с, cache hit): {len(fast)}/{len(flight_times)}")
    print(f"  (было ~45с без prefetch)")

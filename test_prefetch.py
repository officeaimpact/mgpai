"""
Test: Prefetch flight details speed improvement.
Runs 3 scenarios end-to-end, measures time for flight question.
"""
import requests, time, json, uuid

BASE = "http://localhost:8080/api/v1/chat"

def chat(conv_id, msg):
    t0 = time.time()
    r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=120)
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
        "id": "prefetch_test_1",
        "name": "Сочи из Москвы (стандарт)",
        "messages": [
            "Привет! Хочу в Сочи из Москвы, 15 июня на 7 ночей, 2 взрослых, 4 звезды, завтрак",
        ],
        "flight_q": "какой перелёт в первом отеле?",
    },
    {
        "id": "prefetch_test_2",
        "name": "Турция из Москвы",
        "messages": [
            "хочу в турцию из москвы, 5 марта на неделю, 2 взр, 5 звезд все включено",
        ],
        "flight_q": "а какой перелёт в первом варианте?",
    },
    {
        "id": "prefetch_test_3",
        "name": "Крым из Питера",
        "messages": [
            "Крым из Питера, начало августа на 10 ночей, 2 взр, 3 звезды все включено",
        ],
        "flight_q": "какой перелёт в первом?",
    },
]

print("=" * 70)
print("  ТЕСТ PREFETCH: скорость ответа на вопрос о перелёте")
print("=" * 70)

results = []

for sc in SCENARIOS:
    conv_id = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"  {sc['name']}")
    print(f"{'='*60}")

    got_cards = False
    for msg in sc["messages"]:
        r = chat(conv_id, msg)
        print(f"  User: {msg[:80]}")
        print(f"  Bot ({r['time']}s, {r['n_cards']} cards): {r['reply'][:120]}")
        if r["n_cards"] > 0:
            got_cards = True
            for c in r["cards"][:3]:
                print(f"    card: {c.get('hotelName','?')} | {c.get('price','?')}₽")
        time.sleep(1)

    if not got_cards:
        # Need followups
        followups = ["4 звезды, завтрак", "2 взрослых", "да, подбирайте"]
        for fu in followups:
            if got_cards:
                break
            r = chat(conv_id, fu)
            print(f"  User: {fu}")
            print(f"  Bot ({r['time']}s, {r['n_cards']} cards): {r['reply'][:120]}")
            if r["n_cards"] > 0:
                got_cards = True
                for c in r["cards"][:3]:
                    print(f"    card: {c.get('hotelName','?')} | {c.get('price','?')}₽")
            time.sleep(1)

    if not got_cards:
        print(f"  SKIP — no cards received")
        continue

    # Wait for prefetch to complete (actdetail needs 5-20s)
    print(f"  ... waiting 10s for prefetch to complete ...")
    time.sleep(10)

    # Ask about flight
    print(f"\n  >>> FLIGHT QUESTION: {sc['flight_q']}")
    r_flight = chat(conv_id, sc["flight_q"])
    print(f"  <<< FLIGHT ANSWER ({r_flight['time']}s): {r_flight['reply'][:200]}")

    results.append({
        "scenario": sc["name"],
        "got_cards": got_cards,
        "flight_time": r_flight["time"],
        "flight_reply_len": len(r_flight["reply"]),
    })

print(f"\n{'='*70}")
print(f"  РЕЗУЛЬТАТЫ")
print(f"{'='*70}")
for r in results:
    print(f"  {r['scenario']}: перелёт за {r['flight_time']}с ({r['flight_reply_len']} символов)")

if results:
    avg = round(sum(r["flight_time"] for r in results) / len(results), 1)
    print(f"\n  СРЕДНЕЕ ВРЕМЯ НА ПЕРЕЛЁТ: {avg}с")
    print(f"  (было ~45с, ожидаем ~5-10с с prefetch)")

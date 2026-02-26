"""
Test: Prefetch top-3 tours — 10 international scenarios.
Different Tourvisor countries, asks about 1st/2nd/3rd tour flights.
"""
import requests, time, uuid, sys

BASE = "http://localhost:8080/api/v1/chat"

def chat(conv_id, msg, retries=2):
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=180)
            elapsed = round(time.time() - t0, 1)
            data = r.json()
            return {
                "reply": data.get("reply", ""),
                "cards": data.get("tour_cards", []),
                "n_cards": len(data.get("tour_cards", [])),
                "time": elapsed,
                "error": None,
            }
        except Exception as e:
            if attempt < retries:
                print(f"    [RETRY {attempt+1}] Connection error, waiting 5s...", flush=True)
                time.sleep(5)
            else:
                return {"reply": "", "cards": [], "n_cards": 0, "time": 0, "error": str(e)[:100]}

SCENARIOS = [
    {
        "name": "1. Турция из Москвы",
        "search": "турция из москвы, 5 марта на неделю, 2 взрослых, 5 звезд все включено",
        "flight_q": "какой перелёт в первом варианте?",
        "tour_pos": 1,
    },
    {
        "name": "2. Египет из Москвы",
        "search": "египет из москвы, 20 марта на 7 ночей, 2 взрослых, 5 звезд все включено",
        "flight_q": "а какой перелёт во втором варианте?",
        "tour_pos": 2,
    },
    {
        "name": "3. ОАЭ из Москвы",
        "search": "оаэ из москвы, 10 апреля на 5 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "расскажи про перелёт в третьем варианте",
        "tour_pos": 3,
    },
    {
        "name": "4. Таиланд из Москвы",
        "search": "тайланд из москвы, 1 мая на 10 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "какой перелёт в первом?",
        "tour_pos": 1,
    },
    {
        "name": "5. Мальдивы из Москвы",
        "search": "мальдивы из москвы, июнь на неделю, 2 взрослых, 5 звезд",
        "flight_q": "а какой перелёт во втором?",
        "tour_pos": 2,
    },
    {
        "name": "6. Шри-Ланка из Москвы",
        "search": "шри-ланка из москвы, апрель на 10 ночей, 2 взрослых, 4 звезды завтрак",
        "flight_q": "какой рейс в третьем варианте?",
        "tour_pos": 3,
    },
    {
        "name": "7. Куба из Москвы",
        "search": "куба из москвы, март на 7 ночей, 2 взрослых, 4 звезды все включено",
        "flight_q": "какой перелёт в первом варианте?",
        "tour_pos": 1,
    },
    {
        "name": "8. Тунис из Москвы",
        "search": "тунис из москвы, июнь на неделю, 2 взрослых, 4 звезды все включено",
        "flight_q": "расскажи про перелёт во втором варианте",
        "tour_pos": 2,
    },
    {
        "name": "9. Вьетнам из Москвы",
        "search": "вьетнам из москвы, апрель на 10 ночей, 2 взрослых, 3 звезды завтрак",
        "flight_q": "какой перелёт в первом?",
        "tour_pos": 1,
    },
    {
        "name": "10. Кипр из Москвы",
        "search": "кипр из москвы, май на неделю, 2 взрослых, 4 звезды все включено",
        "flight_q": "какой перелёт в третьем варианте?",
        "tour_pos": 3,
    },
]

print("=" * 70, flush=True)
print("  ТЕСТ: PREFETCH 3 ТУРА — МЕЖДУНАРОДНЫЕ (10 сценариев)", flush=True)
print("=" * 70, flush=True)

results = []

for sc in SCENARIOS:
    conv_id = str(uuid.uuid4())
    print(f"\n{'='*65}", flush=True)
    print(f"  {sc['name']} (позиция {sc['tour_pos']})", flush=True)
    print(f"{'='*65}", flush=True)

    r = chat(conv_id, sc["search"])
    if r["error"]:
        print(f"  ERROR: {r['error']}", flush=True)
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": "error"})
        continue

    print(f"  Поиск ({r['time']}с, {r['n_cards']} карточек)", flush=True)

    if r["n_cards"] == 0:
        followups = ["любое питание", "да, подбирайте"]
        for fu in followups:
            if r["n_cards"] > 0:
                break
            time.sleep(1)
            r2 = chat(conv_id, fu)
            if r2["error"]:
                print(f"  ERROR: {r2['error']}", flush=True)
                break
            print(f"    Уточнение: {fu} -> ({r2['time']}с, {r2['n_cards']} карточек)", flush=True)
            if r2["n_cards"] > 0:
                r = r2

    if r["n_cards"] == 0:
        print(f"  SKIP — нет карточек", flush=True)
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": "no_cards"})
        continue

    if r["n_cards"] < sc["tour_pos"]:
        print(f"  SKIP — {r['n_cards']} карточек, нужна поз.{sc['tour_pos']}", flush=True)
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": f"only_{r['n_cards']}"})
        continue

    for i, c in enumerate(r["cards"][:5], 1):
        mark = " <--" if i == sc["tour_pos"] else ""
        print(f"    {i}. {c.get('hotelName','?')} | {c.get('price','?')}r{mark}", flush=True)

    print(f"  ... 20с prefetch ...", flush=True)
    time.sleep(20)

    r_f = chat(conv_id, sc["flight_q"])
    if r_f["error"]:
        print(f"  FLIGHT ERROR: {r_f['error']}", flush=True)
        results.append({"scenario": sc["name"], "tour_pos": sc["tour_pos"],
                         "flight_time": None, "status": "flight_error"})
        continue

    print(f"  >>> {sc['flight_q']}", flush=True)
    print(f"  <<< ({r_f['time']}с): {r_f['reply'][:200]}", flush=True)

    has_flight = any(w in r_f["reply"].lower() for w in [
        "рейс", "вылет", "авиа", "аэро", "прилёт", "прилет", "dp", "победа",
        "аэрофлот", "s7", "turkish", "emirates", "flydubai", "qatar", "saudia",
        "sichuan", "pegasus", "ajet"
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

print(f"\n{'='*70}", flush=True)
print(f"  РЕЗУЛЬТАТЫ — МЕЖДУНАРОДНЫЕ (prefetch 3)", flush=True)
print(f"{'='*70}", flush=True)
print(f"  {'Сценарий':<35} {'Поз':>4} {'Поиск':>7} {'Перелёт':>8} {'Инфо'}", flush=True)
print(f"  {'-'*35} {'-'*4} {'-'*7} {'-'*8} {'-'*15}", flush=True)

flight_times = []
for r in results:
    if r["status"] == "ok":
        tags = []
        if r.get("has_flight"): tags.append("рейс")
        if r.get("has_manager"): tags.append("менеджер")
        info = ", ".join(tags) if tags else "нет данных"
        print(f"  {r['scenario']:<35} {r['tour_pos']:>4} {r['search_time']:>6}с {r['flight_time']:>7}с {info}", flush=True)
        flight_times.append(r["flight_time"])
    else:
        print(f"  {r['scenario']:<35} {r['tour_pos']:>4} {'—':>7} {'—':>8} {r['status']}", flush=True)

if flight_times:
    avg = round(sum(flight_times) / len(flight_times), 1)
    fast = [t for t in flight_times if t < 15]
    print(f"\n  Среднее время перелёт: {avg}с", flush=True)
    print(f"  Быстрых (<15с): {len(fast)}/{len(flight_times)}", flush=True)
    print(f"  Мин: {min(flight_times)}с | Макс: {max(flight_times)}с", flush=True)

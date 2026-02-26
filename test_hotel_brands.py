"""
Hotel Brand QC Test — 10 scenarios.
Checks: does the assistant skip stars question when a hotel brand is specified?
"""
import requests, time, uuid, json, re, sys
from datetime import datetime

BASE = "http://localhost:8080/api/v1/chat"
TIMEOUT = 180

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def chat(conv_id, msg):
    try:
        t0 = time.time()
        r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=TIMEOUT)
        elapsed = round(time.time() - t0, 1)
        data = r.json()
        return {
            "reply": data.get("reply", ""),
            "cards": len(data.get("tour_cards", [])),
            "time": elapsed,
        }
    except Exception as e:
        return {"reply": f"ERROR: {e}", "cards": 0, "time": 0}

SCENARIOS = [
    {
        "name": "Rixos Турция",
        "msg": "хочу в отель Rixos в Турции из Москвы, начало июля на 10 ночей, 2 взрослых, все включено",
    },
    {
        "name": "Radisson Сочи",
        "msg": "хочу в Radisson в Сочи из Москвы, начало июня на 7 ночей, 2 взрослых, завтраки",
    },
    {
        "name": "Delphin Белек",
        "msg": "Delphin BE Grand Resort в Белеке из Москвы, 15 июля на 7 ночей, 2 взрослых, ультра всё включено",
    },
    {
        "name": "Hilton Египет",
        "msg": "хотим в Hilton в Хургаде из Москвы, начало мая на 10 ночей, 2 взрослых, всё включено",
    },
    {
        "name": "Sheraton ОАЭ",
        "msg": "Sheraton в Дубае из Москвы, 20 апреля на 5 ночей, 2 взрослых, завтраки",
    },
    {
        "name": "Iberostar Турция",
        "msg": "хочу в Iberostar в Турции из Москвы, середина июня на 7 ночей, 2 взрослых, всё включено",
    },
    {
        "name": "Calista Белек",
        "msg": "Calista Luxury Resort в Белеке из СПб, 10 июля на 10 ночей, 2 взрослых и ребёнок 6 лет, всё включено",
    },
    {
        "name": "Риксос кириллица",
        "msg": "хочу в Риксос в Египте из Москвы, начало июня на 7 ночей, вдвоём, всё включено",
    },
    {
        "name": "Vinpearl Вьетнам",
        "msg": "хочу в Vinpearl Resort во Вьетнаме из Москвы, 6 апреля на 14 ночей, 2 взрослых, завтраки",
    },
    {
        "name": "Aquamarine Сочи",
        "msg": "хочу в отель Аквамарин в Сочи из Москвы, начало августа на 7 ночей, 2 взрослых, полупансион",
    },
]

STARS_QUESTION_RX = re.compile(
    r'(?:зв[ёе]зд|катего|stars|★|какой.*класс|сколько.*зв)', re.IGNORECASE
)

if __name__ == "__main__":
    log("=" * 60)
    log("  HOTEL BRAND QC TEST — 10 сценариев")
    log("  Проверка: спрашивает ли ассистент звёздность при бренде")
    log("=" * 60)

    passed = 0
    failed = 0

    for sc in SCENARIOS:
        conv_id = str(uuid.uuid4())
        log(f"\n📋 {sc['name']}")
        log(f"   → {sc['msg']}")

        resp = chat(conv_id, sc["msg"])
        reply = resp["reply"]

        asked_stars = bool(STARS_QUESTION_RX.search(reply))
        got_cards = resp["cards"] > 0

        if got_cards:
            status = "✅ PASS (карточки сразу)"
            passed += 1
        elif not asked_stars:
            status = "✅ PASS (спросил питание, НЕ звёзды)"
            passed += 1
        else:
            status = "❌ FAIL (спросил звёздность!)"
            failed += 1

        log(f"   ← [{resp['time']}s, {resp['cards']} cards] {reply[:150]}")
        log(f"   {status}")

    log(f"\n{'='*60}")
    log(f"  ИТОГО: {passed} PASS / {failed} FAIL из {len(SCENARIOS)}")
    log(f"{'='*60}")

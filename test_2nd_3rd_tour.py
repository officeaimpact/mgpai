"""Test: flight question for 1st, 2nd and 3rd tour."""
import requests, time, uuid

BASE = "http://localhost:8080/api/v1/chat"

def chat(conv_id, msg):
    t0 = time.time()
    r = requests.post(BASE, json={"message": msg, "conversation_id": conv_id}, timeout=180)
    elapsed = round(time.time() - t0, 1)
    data = r.json()
    return elapsed, data.get("reply", ""), len(data.get("tour_cards", []))

conv = str(uuid.uuid4())
print("=" * 60)
print("  ТЕСТ: перелёт 1-го, 2-го и 3-го тура")
print("=" * 60)

# Search
t, reply, cards = chat(conv, "хочу в турцию из москвы, 5 марта на неделю, 2 взрослых, 5 звезд все включено")
print(f"\n  Поиск ({t}с, {cards} карточек): {reply[:120]}")

print(f"\n  ... ждём 20с для prefetch ...")
time.sleep(20)

# 1st tour
print(f"\n  === 1-й тур ===")
t1, r1, _ = chat(conv, "какой перелёт в первом варианте?")
print(f"  ({t1}с): {r1[:200]}")

time.sleep(2)

# 2nd tour
conv2 = str(uuid.uuid4())
t, reply, cards = chat(conv2, "хочу в турцию из москвы, 5 марта на неделю, 2 взрослых, 5 звезд все включено")
print(f"\n  Новый поиск ({t}с, {cards} карточек)")
print(f"  ... ждём 20с для prefetch ...")
time.sleep(20)

print(f"\n  === 2-й тур ===")
t2, r2, _ = chat(conv2, "а какой перелёт во втором варианте?")
print(f"  ({t2}с): {r2[:200]}")

time.sleep(2)

# 3rd tour
conv3 = str(uuid.uuid4())
t, reply, cards = chat(conv3, "хочу в турцию из москвы, 5 марта на неделю, 2 взрослых, 5 звезд все включено")
print(f"\n  Новый поиск ({t}с, {cards} карточек)")
print(f"  ... ждём 20с для prefetch ...")
time.sleep(20)

print(f"\n  === 3-й тур (НЕ в кэше) ===")
t3, r3, _ = chat(conv3, "а какой перелёт в третьем варианте?")
print(f"  ({t3}с): {r3[:200]}")

print(f"\n{'='*60}")
print(f"  ИТОГО:")
print(f"  1-й тур (кэш): {t1}с")
print(f"  2-й тур (кэш): {t2}с")
print(f"  3-й тур (без кэша): {t3}с")
print(f"{'='*60}")

"""
Тестирование детектора _is_promised_search
"""

def _is_promised_search(text: str) -> bool:
    """
    Детектирует ситуацию когда модель ПООБЕЩАЛА выполнить поиск,
    но вернула текст вместо function_call.
    """
    if not text:
        return False
    lower = text.lower().strip()
    promise_phrases = [
        "начну поиск",
        "начинаю поиск",
        "сейчас поищу",
        "сейчас найду",
        "запускаю поиск",
        "ищу для вас",
        "ищу подходящие",
        "приступаю к поиску",
        "подберу для вас",
        "сейчас подберу",
        "начну подбор",
        "начинаю подбор",
        "давайте поищу",
        "давайте найду",
        "сейчас подбираю",
    ]
    return any(phrase in lower for phrase in promise_phrases)


# Реальные тексты из логов
test_cases = [
    ("🍽️ Хорошо, полупансион. Сейчас начну поиск подходящих туров для вас.", True),
    ("Нашёл несколько отличных вариантов в Турции для вас!", False),
    ("Отлично! Из какого города планируете вылет?", False),
    ("Сейчас поищу для вас туры в Египет.", True),
    ("Начинаю поиск туров...", True),
    ("Хорошо, 21 февраля на неделю. Сколько взрослых едет?", False),
]

print("=" * 60)
print("ТЕСТИРОВАНИЕ ДЕТЕКТОРА _is_promised_search")
print("=" * 60)

for text, expected in test_cases:
    result = _is_promised_search(text)
    status = "✅ OK" if result == expected else "❌ FAIL"
    print(f"\n{status}")
    print(f"  Текст: {text[:80]}...")
    print(f"  Ожидалось: {expected}, Получено: {result}")
    
    if result != expected:
        lower = text.lower().strip()
        print(f"  Lower: {lower[:80]}...")
        for phrase in ["начну поиск", "сейчас поищу", "начинаю поиск"]:
            if phrase in lower:
                print(f"    ✓ Найдена фраза: '{phrase}'")

print("\n" + "=" * 60)

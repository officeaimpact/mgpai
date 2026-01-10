"""
Tourvisor Data Synchronization Script
======================================

Скрипт для синхронизации справочников Tourvisor API.
Скачивает актуальные данные (страны, города вылета) и сохраняет
в файл констант для использования в приложении.

Использование:
    # Запуск вручную
    python scripts/sync_tourvisor_data.py
    
    # Или импорт в код
    from scripts.sync_tourvisor_data import sync_dictionaries
    await sync_dictionaries()

Автор: MGP AI Team
Версия: 1.0.0
"""
from __future__ import annotations

import asyncio
import httpx
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings

# ==================== КОНФИГУРАЦИЯ ====================

# Путь к файлу констант
CONSTANTS_FILE = PROJECT_ROOT / "app" / "core" / "tourvisor_constants.py"

# API endpoints
API_BASE_URL = "http://tourvisor.ru/xml"


# ==================== SYNC FUNCTIONS ====================

async def fetch_countries(client: httpx.AsyncClient) -> dict[str, int]:
    """
    Загрузка справочника стран из Tourvisor API.
    
    Returns:
        dict: {"египет": 1, "турция": 4, ...}
    """
    params = {
        "authlogin": settings.TOURVISOR_AUTH_LOGIN,
        "authpass": settings.TOURVISOR_AUTH_PASS,
        "format": "json",
        "type": "country",
    }
    
    response = await client.get(f"{API_BASE_URL}/list.php", params=params)
    response.raise_for_status()
    
    data = response.json()
    
    # Извлекаем страны из разных форматов ответа
    countries_data = (
        data.get("lists", {}).get("countries", {}).get("country", []) or
        data.get("data", {}).get("country", []) or
        []
    )
    
    if isinstance(countries_data, dict):
        countries_data = [countries_data]
    
    countries = {}
    for country in countries_data:
        cid = int(country.get("id", 0))
        name = country.get("name", "").strip()
        name_en = country.get("name_en", "").strip()
        
        if cid and name:
            # Добавляем русское название
            countries[name.lower()] = cid
            
            # Добавляем английское название (если есть)
            if name_en:
                countries[name_en.lower()] = cid
    
    return countries


async def fetch_departures(client: httpx.AsyncClient) -> dict[str, int]:
    """
    Загрузка справочника городов вылета из Tourvisor API.
    
    Returns:
        dict: {"москва": 1, "санкт-петербург": 2, ...}
    """
    params = {
        "authlogin": settings.TOURVISOR_AUTH_LOGIN,
        "authpass": settings.TOURVISOR_AUTH_PASS,
        "format": "json",
        "type": "departure",
    }
    
    response = await client.get(f"{API_BASE_URL}/list.php", params=params)
    response.raise_for_status()
    
    data = response.json()
    
    # Извлекаем города вылета
    departures_data = (
        data.get("lists", {}).get("departures", {}).get("departure", []) or
        data.get("data", {}).get("departure", []) or
        []
    )
    
    if isinstance(departures_data, dict):
        departures_data = [departures_data]
    
    departures = {}
    for dep in departures_data:
        did = int(dep.get("id", 0))
        name = dep.get("name", "").strip()
        
        if did and name:
            departures[name.lower()] = did
    
    # Добавляем популярные алиасы
    aliases = {
        "спб": departures.get("санкт-петербург"),
        "питер": departures.get("санкт-петербург"),
        "мск": departures.get("москва"),
        "екб": departures.get("екатеринбург"),
        "новосиб": departures.get("новосибирск"),
        "нижний": departures.get("нижний новгород"),
        "ростов": departures.get("ростов-на-дону"),
        "минводы": departures.get("минеральные воды"),
    }
    
    for alias, dep_id in aliases.items():
        if dep_id:
            departures[alias] = dep_id
    
    return departures


def generate_constants_file(
    countries: dict[str, int],
    departures: dict[str, int],
    timestamp: datetime
) -> str:
    """
    Генерация Python-файла с константами.
    """
    # Сортируем для читаемости
    sorted_countries = dict(sorted(countries.items(), key=lambda x: x[1]))
    sorted_departures = dict(sorted(departures.items(), key=lambda x: x[1]))
    
    # Начинаем формировать код (без f-string чтобы избежать проблем с фигурными скобками)
    lines = []
    lines.append('"""')
    lines.append('Tourvisor API Constants (Auto-Generated)')
    lines.append('=========================================')
    lines.append('')
    lines.append('ВНИМАНИЕ: Этот файл генерируется автоматически!')
    lines.append('Не редактируйте его вручную — изменения будут перезаписаны.')
    lines.append('')
    lines.append(f'Последняя синхронизация: {timestamp.strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'Количество стран: {len(set(countries.values()))}')
    lines.append(f'Количество городов вылета: {len(set(departures.values()))}')
    lines.append('')
    lines.append('Для обновления запустите:')
    lines.append('    python scripts/sync_tourvisor_data.py')
    lines.append('"""')
    lines.append('from __future__ import annotations')
    lines.append('')
    lines.append('# Время последней синхронизации')
    lines.append(f'LAST_SYNC = "{timestamp.isoformat()}"')
    lines.append('')
    lines.append('# ==================== СТРАНЫ ====================')
    lines.append('# Формат: {"название_lowercase": id}')
    lines.append('# Поиск: COUNTRIES.get("египет") -> 1')
    lines.append('')
    lines.append('COUNTRIES: dict[str, int] = {')
    
    # Добавляем страны (группируем по ID для компактности)
    country_by_id: dict[int, list[str]] = {}
    for name, cid in sorted_countries.items():
        if cid not in country_by_id:
            country_by_id[cid] = []
        country_by_id[cid].append(name)
    
    for cid in sorted(country_by_id.keys()):
        names = country_by_id[cid]
        main_name = min([n for n in names if any(ord(c) > 127 for c in n)] or names, key=len)
        lines.append(f'    # ID={cid}: {main_name.title()}')
        for name in sorted(names):
            lines.append(f'    "{name}": {cid},')
    
    lines.append('}')
    lines.append('')
    lines.append('# ==================== ГОРОДА ВЫЛЕТА ====================')
    lines.append('# Формат: {"название_lowercase": id}')
    lines.append('# Поиск: DEPARTURES.get("москва") -> 1')
    lines.append('')
    lines.append('DEPARTURES: dict[str, int] = {')
    
    # Добавляем города
    dep_by_id: dict[int, list[str]] = {}
    for name, did in sorted_departures.items():
        if did not in dep_by_id:
            dep_by_id[did] = []
        dep_by_id[did].append(name)
    
    for did in sorted(dep_by_id.keys()):
        names = dep_by_id[did]
        main_name = min([n for n in names if any(ord(c) > 127 for c in n)] or names, key=len)
        lines.append(f'    # ID={did}: {main_name.title()}')
        for name in sorted(names):
            lines.append(f'    "{name}": {did},')
    
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('# ==================== HELPER FUNCTIONS ====================')
    lines.append('')
    lines.append('from typing import Optional')
    lines.append('')
    lines.append('')
    lines.append('def get_country_id(name: str) -> Optional[int]:')
    lines.append('    """Получить ID страны по названию."""')
    lines.append('    if not name:')
    lines.append('        return None')
    lines.append('    return COUNTRIES.get(name.lower().strip())')
    lines.append('')
    lines.append('')
    lines.append('def get_departure_id(name: str) -> Optional[int]:')
    lines.append('    """Получить ID города вылета по названию."""')
    lines.append('    if not name:')
    lines.append('        return None')
    lines.append('    return DEPARTURES.get(name.lower().strip())')
    lines.append('')
    lines.append('')
    lines.append('def get_country_name(country_id: int) -> Optional[str]:')
    lines.append('    """Получить название страны по ID."""')
    lines.append('    for name, cid in COUNTRIES.items():')
    lines.append('        if cid == country_id and any(ord(c) > 127 for c in name):')
    lines.append('            return name.title()')
    lines.append('    return None')
    lines.append('')
    lines.append('')
    lines.append('def get_departure_name(departure_id: int) -> Optional[str]:')
    lines.append('    """Получить название города вылета по ID."""')
    lines.append('    for name, did in DEPARTURES.items():')
    lines.append('        if did == departure_id and any(ord(c) > 127 for c in name):')
    lines.append('            return name.title()')
    lines.append('    return None')
    
    return '\n'.join(lines)


async def sync_dictionaries(verbose: bool = True) -> tuple[int, int]:
    """
    Главная функция синхронизации справочников.
    
    Скачивает актуальные данные из Tourvisor API и сохраняет
    в файл констант.
    
    Args:
        verbose: Выводить логи в консоль
        
    Returns:
        tuple: (количество_стран, количество_городов)
    """
    timestamp = datetime.now()
    
    if verbose:
        print("=" * 60)
        print("🔄 TOURVISOR DATA SYNC")
        print("=" * 60)
        print(f"   Время: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Проверяем конфигурацию
    if not settings.TOURVISOR_AUTH_LOGIN or not settings.TOURVISOR_AUTH_PASS:
        raise ValueError("Tourvisor credentials not configured!")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Загружаем страны
        if verbose:
            print("\n📥 Загрузка справочника стран...")
        countries = await fetch_countries(client)
        unique_countries = len(set(countries.values()))
        if verbose:
            print(f"   ✅ Загружено: {unique_countries} стран ({len(countries)} записей)")
        
        # Загружаем города вылета
        if verbose:
            print("\n📥 Загрузка справочника городов вылета...")
        departures = await fetch_departures(client)
        unique_departures = len(set(departures.values()))
        if verbose:
            print(f"   ✅ Загружено: {unique_departures} городов ({len(departures)} записей)")
    
    # Генерируем файл констант
    if verbose:
        print(f"\n📝 Генерация файла констант...")
        print(f"   Путь: {CONSTANTS_FILE}")
    
    code = generate_constants_file(countries, departures, timestamp)
    
    # Создаём директорию если нужно
    CONSTANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Записываем файл
    with open(CONSTANTS_FILE, "w", encoding="utf-8") as f:
        f.write(code)
    
    if verbose:
        print(f"   ✅ Файл сохранён!")
        
        # Показываем примеры
        print("\n📋 Примеры данных:")
        print("   Страны:")
        sample_countries = ["египет", "турция", "оаэ", "таиланд", "мальдивы"]
        for name in sample_countries:
            cid = countries.get(name)
            if cid:
                print(f"      {name.title()}: ID={cid}")
        
        print("   Города вылета:")
        sample_departures = ["москва", "санкт-петербург", "казань", "екатеринбург"]
        for name in sample_departures:
            did = departures.get(name)
            if did:
                print(f"      {name.title()}: ID={did}")
        
        print("\n" + "=" * 60)
        print("✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
        print("=" * 60)
    
    return unique_countries, unique_departures


# ==================== CLI ====================

async def main():
    """CLI entry point."""
    try:
        countries_count, departures_count = await sync_dictionaries(verbose=True)
        return 0
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

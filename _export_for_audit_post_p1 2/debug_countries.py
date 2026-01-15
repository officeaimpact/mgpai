"""
Debug: Проверка справочника стран Tourvisor
"""
import asyncio
import httpx
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import settings


async def main():
    base_url = settings.TOURVISOR_BASE_URL
    
    params = {
        "authlogin": settings.TOURVISOR_AUTH_LOGIN,
        "authpass": settings.TOURVISOR_AUTH_PASS,
        "format": "json",
        "type": "country",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/list.php", params=params)
        data = response.json()
        
        # Извлекаем страны
        countries_data = (
            data.get("lists", {}).get("countries", {}).get("country", []) or
            data.get("data", {}).get("country", []) or
            []
        )
        
        if isinstance(countries_data, dict):
            countries_data = [countries_data]
        
        print("=" * 60)
        print("📚 СПРАВОЧНИК СТРАН TOURVISOR")
        print("=" * 60)
        
        # Ищем Египет
        egypt = None
        tunisia = None
        
        for country in countries_data:
            cid = country.get("id")
            name = country.get("name", "")
            name_en = country.get("name_en", "")
            
            if "египет" in name.lower() or "egypt" in name_en.lower():
                egypt = country
            if "тунис" in name.lower() or "tunisia" in name_en.lower():
                tunisia = country
        
        print("\n🔍 Поиск Египта:")
        if egypt:
            print(f"   ✅ НАЙДЕН: ID={egypt.get('id')}, Name={egypt.get('name')}, EN={egypt.get('name_en')}")
        else:
            print("   ❌ НЕ НАЙДЕН!")
        
        print("\n🔍 Поиск Туниса:")
        if tunisia:
            print(f"   ✅ НАЙДЕН: ID={tunisia.get('id')}, Name={tunisia.get('name')}, EN={tunisia.get('name_en')}")
        else:
            print("   ❌ НЕ НАЙДЕН!")
        
        # Выводим первые 20 стран
        print("\n📋 Первые 20 стран:")
        for country in countries_data[:20]:
            print(f"   ID={country.get('id'):>3} | {country.get('name'):<20} | {country.get('name_en', '')}")
        
        # Ищем страны с ID около 5
        print("\n📋 Страны с ID 1-10:")
        for country in countries_data:
            cid = int(country.get("id", 0))
            if 1 <= cid <= 10:
                print(f"   ID={cid:>3} | {country.get('name'):<20} | {country.get('name_en', '')}")


if __name__ == "__main__":
    asyncio.run(main())

"""深入检查基准集"""
import asyncio
import httpx

H = {"X-User-ID": "z00881489"}
BASE = "http://localhost:8080"

async def q(params):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        await c.post(f"{BASE}/api/houses/init", headers=H)
        r = await c.get(f"{BASE}/api/houses/by_platform", headers=H, params=params)
        d = r.json()
        items = d.get("data", {}).get("items", [])
        return [h["house_id"] for h in items]

async def main():
    cases = [
        ("M7 昌平+13号线+整租+一居", {"district": "昌平", "subway_line": "13号线", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("S9 朝阳+朝南+整租 (orientation)", {"district": "朝阳", "orientation": "朝南", "rental_type": "整租", "page_size": 100}),
        ("S11 13号线+整租+两居", {"subway_line": "13号线", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("S12 面积>=60+整租+两居", {"min_area": 60, "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("SC9 13号线+整租+一居", {"subway_line": "13号线", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("SC10 面积区间+整租", {"min_area": 50, "max_area": 80, "rental_type": "整租", "page_size": 100}),
        ("SC11 available_from_before", {"available_from_before": "2026-04-01", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("SC12 get_house_detail for SC12", None),  # uses get_house_detail + get_nearby_landmarks
        ("朝阳+精装+整租+两居 (no max_price)", {"district": "朝阳", "decoration": "精装", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("朝阳+精装+整租 (no bedrooms)", {"district": "朝阳", "decoration": "精装", "rental_type": "整租", "page_size": 100}),
    ]
    
    for name, params in cases:
        if params is None:
            print(f"{name}: N/A (uses detail/landmark API)")
            continue
        ids = await q(params)
        print(f"{name}: {len(ids)} 套 {ids[:5]}")

asyncio.run(main())

"""检查剩余用例的基准集"""
import asyncio, httpx

H = {"X-User-ID": "z00881489"}
BASE = "http://localhost:8080"

async def q(params, endpoint="/api/houses/by_platform"):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        r = await c.get(f"{BASE}{endpoint}", headers=H, params=params)
        items = r.json().get("data", {}).get("items", [])
        return len(items), [h["house_id"] for h in items[:3]]

async def main():
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        await c.post(f"{BASE}/api/houses/init", headers=H)
    
    checks = [
        ("S13: 丰台+合租+一居", {"district": "丰台", "rental_type": "合租", "bedrooms": "1", "page_size": 100}),
        ("S14: 大兴+整租+一居", {"district": "大兴", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("S15: 西城+整租+两居", {"district": "西城", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("SC6: 建清园小区", None),
        ("SC7: 海淀,朝阳+整租+两居+精装", {"district": "海淀,朝阳", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "page_size": 100}),
        ("SC9: 13号线+精装+整租+两居+8000", {"subway_line": "13号线", "decoration": "精装", "rental_type": "整租", "bedrooms": "2", "max_price": 8000, "page_size": 100}),
        ("SC13: get_landmark_by_name based", None),  # landmark based
        ("SC14: 海淀+精装+两居+6000-12000", {"district": "海淀", "decoration": "精装", "bedrooms": "2", "min_price": 6000, "max_price": 12000, "page_size": 100}),
        ("SC15: 顺义+两居+6000", {"district": "顺义", "bedrooms": "2", "max_price": 6000, "sort_by": "price", "sort_order": "asc", "page_size": 100}),
        ("M7: 昌平+13号线+整租+一居", {"district": "昌平", "subway_line": "13号线", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("大兴+整租 (no bedrooms)", {"district": "大兴", "rental_type": "整租", "page_size": 100}),
        ("西城+整租 (no bedrooms)", {"district": "西城", "rental_type": "整租", "page_size": 100}),
        ("丰台+合租 (no bedrooms)", {"district": "丰台", "rental_type": "合租", "page_size": 100}),
        ("顺义+整租 (no bedrooms)", {"district": "顺义", "rental_type": "整租", "page_size": 100}),
    ]
    
    for name, params in checks:
        if params is None:
            if "建清园" in name:
                n, ids = await q({"community": "建清园", "page_size": 100}, endpoint="/api/houses/by_community")
            else:
                print(f"{name}: N/A")
                continue
        else:
            n, ids = await q(params)
        print(f"{name}: {n} 套 {ids}")

asyncio.run(main())

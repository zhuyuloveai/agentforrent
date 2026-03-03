"""检查丰台、通州等区是否有数据"""
import asyncio, httpx

H = {"X-User-ID": "z00881489"}
BASE = "http://localhost:8080"

async def q(params):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        r = await c.get(f"{BASE}/api/houses/by_platform", headers=H, params=params)
        items = r.json().get("data", {}).get("items", [])
        return len(items), [h["house_id"] for h in items[:3]]

async def main():
    await q({"page_size": 1})  # warm up + reset
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        await c.post(f"{BASE}/api/houses/init", headers=H)
    
    checks = [
        ("丰台+整租+两居", {"district": "丰台", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("丰台+整租+一居", {"district": "丰台", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("通州+整租+两居", {"district": "通州", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("东城+整租+两居", {"district": "东城", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("S10: 丰台+整租+两居", {"district": "丰台", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("S13: 丰台+整租+一居", {"district": "丰台", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("SC11: 海淀+整租+一居+2026-03-20", {"district": "海淀", "rental_type": "整租", "bedrooms": "1", "available_from_before": "2026-03-20", "page_size": 100}),
        ("SC11 baseline query exact", {"available_from_before": "2026-03-20", "district": "海淀", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("S2: bedrooms=1+max_price=5000", {"bedrooms": "1", "max_price": 5000, "page_size": 100}),
    ]
    
    for name, params in checks:
        n, ids = await q(params)
        print(f"{name}: {n} 套 {ids}")

asyncio.run(main())

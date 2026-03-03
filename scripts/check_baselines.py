"""检查各类查询的基准集大小"""
import asyncio
import httpx

H = {"X-User-ID": "z00881489"}
BASE = "http://localhost:8080"

async def query(params):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        r = await c.get(f"{BASE}/api/houses/by_platform", headers=H, params=params)
        d = r.json()
        items = d.get("data", {}).get("items", [])
        return [h["house_id"] for h in items]

async def main():
    cases = [
        ("S6 通州+整租+两居", {"district": "通州", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("S9 朝阳+朝南+整租", {"district": "朝阳", "orientation": "朝南", "rental_type": "整租", "page_size": 100}),
        ("S11 13号线+整租+两居", {"subway_line": "13号线", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("S12 面积60+整租+两居", {"min_area": 60, "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("SC6 建外SOHO小区", None),  # by_community
        ("SC7 西城+整租+精装+价格", {"district": "西城", "rental_type": "整租", "decoration": "精装", "max_price": 10000, "page_size": 100}),
        ("SC9 13号线+整租+一居", {"subway_line": "13号线", "rental_type": "整租", "bedrooms": "1", "page_size": 100}),
        ("SC11 available_from_before", {"available_from_before": "2026-04-01", "rental_type": "整租", "bedrooms": "2", "page_size": 100}),
        ("SC14 海淀+装修+两居+价格区间", {"district": "海淀", "decoration": "精装", "bedrooms": "2", "min_price": 6000, "max_price": 12000, "page_size": 100}),
        ("SC15 顺义+两居+价格+排序", {"district": "顺义", "bedrooms": "2", "max_price": 6000, "sort_by": "price", "sort_order": "asc", "page_size": 100}),
        ("MC5 朝阳+精装+整租+两居+10000", {"district": "朝阳", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "max_price": 10000, "page_size": 100}),
        ("MC6 海淀+整租+两居+精装+8000", {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "max_price": 8000, "page_size": 100}),
        ("M7 13号线+两居", {"subway_line": "13号线", "bedrooms": "2", "page_size": 100}),
        ("M9 顺义+整租+精装", {"district": "顺义", "rental_type": "整租", "decoration": "精装", "page_size": 100}),
        ("M10 通勤30+整租+两居+价格区间", {"commute_to_xierqi_max": 30, "rental_type": "整租", "bedrooms": "2", "min_price": 6000, "max_price": 10000, "page_size": 100}),
    ]
    
    for name, params in cases:
        if params is None:
            # by_community
            async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
                r = await c.get(f"{BASE}/api/houses/by_community", headers=H, params={"community": "建外SOHO", "page_size": 100})
                items = r.json().get("data", {}).get("items", [])
                ids = [h["house_id"] for h in items]
                print(f"{name}: {len(ids)} 套 {ids[:3]}")
        else:
            ids = await query(params)
            print(f"{name}: {len(ids)} 套 {ids[:3]}")

asyncio.run(main())

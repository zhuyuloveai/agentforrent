"""临时诊断脚本 v2：验证修复后的条件组合"""
import httpx

BASE = "http://localhost:8080"
HEADERS = {"X-User-ID": "z00881489"}
C = {"timeout": 10.0, "trust_env": False}

def q(params):
    with httpx.Client(**C) as c:
        r = c.get(f"{BASE}/api/houses/by_platform", params=params, headers=HEADERS)
    d = r.json()
    inner = d.get("data", {})
    if isinstance(inner, dict):
        items = inner.get("items", [])
        total = inner.get("total", len(items))
    else:
        items, total = [], 0
    ids = [h.get("house_id") for h in items[:5]]
    return total, ids

def nearby(landmark_id, dist):
    with httpx.Client(**C) as c:
        r = c.get(f"{BASE}/api/houses/nearby",
                  params={"landmark_id": landmark_id, "max_distance": dist, "page_size": 100},
                  headers=HEADERS)
    d = r.json()
    inner = d.get("data", {})
    items = inner.get("items", []) if isinstance(inner, dict) else []
    return len(items), [h.get("house_id") for h in items[:5]]

with httpx.Client(**C) as c:
    c.post(f"{BASE}/api/houses/init", headers=HEADERS)

print("=== SC1 修复：去掉 elevator ===")
n, s = q({"district": "海淀", "bedrooms": "2", "decoration": "精装", "max_price": 8000})
print(f"  海淀+两居+精装+8000 -> {n} 套  {s}")
n, s = q({"district": "海淀", "bedrooms": "2", "max_price": 8000})
print(f"  海淀+两居+8000      -> {n} 套  {s}")
n, s = q({"district": "海淀", "bedrooms": "2", "decoration": "精装"})
print(f"  海淀+两居+精装       -> {n} 套  {s}")

print("\n=== SC2 修复：+rental_type ===")
n, s = q({"subway_station": "西二旗站", "max_subway_dist": 800})
print(f"  西二旗站+800m             -> {n} 套  {s}")
n, s = q({"subway_station": "西二旗站", "max_subway_dist": 800, "rental_type": "整租"})
print(f"  西二旗站+800m+整租         -> {n} 套  {s}")
n, s = q({"subway_station": "西二旗站", "max_subway_dist": 1000, "rental_type": "整租"})
print(f"  西二旗站+1000m+整租        -> {n} 套  {s}")

print("\n=== SC4 改用 nearby API ===")
for lid, name in [("SS_005", "国贸站"), ("LM_002", "国贸广场")]:
    for dist in [500, 1000, 2000]:
        n, s = nearby(lid, dist)
        print(f"  nearby({name},{dist}m) -> {n} 套  {s}")

print("\n=== MC1 修复条件 ===")
steps = [
    {"district": "海淀", "rental_type": "整租"},
    {"district": "海淀", "rental_type": "整租", "bedrooms": "2"},
    {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "decoration": "精装"},
    {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "max_price": 10000},
    {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "max_price": 10000},
]
for p in steps:
    n, s = q(p)
    print(f"  {str(p):<65} -> {n} 套")

print("\n=== MC3 检查朝阳整租一居室 + HF_200 状态 ===")
n, s = q({"district": "朝阳", "rental_type": "整租", "bedrooms": "1"})
print(f"  朝阳+整租+一居室 -> {n} 套  {s}")
with httpx.Client(**C) as c:
    r = c.get(f"{BASE}/api/houses/HF_200", headers=HEADERS)
    status = r.json().get("data", {}).get("status", "?")
    district = r.json().get("data", {}).get("district", "?")
    bedrooms = r.json().get("data", {}).get("bedrooms", "?")
    rental = r.json().get("data", {}).get("rental_type", "?")
    print(f"  HF_200: status={status} district={district} bedrooms={bedrooms} rental={rental}")

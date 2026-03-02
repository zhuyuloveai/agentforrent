"""
本地 Mock 租房 API 服务
模拟 http://7.225.29.223:8080 的行为，用于本地调试
"""
import json
import random
import math
from datetime import date, timedelta
from fastapi import FastAPI, Header, HTTPException, Query, Path
from fastapi.responses import JSONResponse
from typing import Optional
import uvicorn

app = FastAPI(title="租房仿真 Mock API")

# ── 地标数据 ──────────────────────────────────────────────────────────────────
LANDMARKS = [
    # 地铁站
    {"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "lat": 40.0979, "lng": 116.3076, "lines": ["13号线", "昌平线"]},
    {"id": "SS_002", "name": "上地站", "category": "subway", "district": "海淀", "lat": 40.0888, "lng": 116.3133, "lines": ["13号线"]},
    {"id": "SS_003", "name": "五道口站", "category": "subway", "district": "海淀", "lat": 39.9924, "lng": 116.3461, "lines": ["15号线"]},
    {"id": "SS_004", "name": "知春路站", "category": "subway", "district": "海淀", "lat": 39.9812, "lng": 116.3481, "lines": ["10号线"]},
    {"id": "SS_005", "name": "国贸站", "category": "subway", "district": "朝阳", "lat": 39.9085, "lng": 116.4613, "lines": ["1号线", "10号线"]},
    {"id": "SS_006", "name": "望京站", "category": "subway", "district": "朝阳", "lat": 40.0024, "lng": 116.4813, "lines": ["15号线"]},
    {"id": "SS_007", "name": "回龙观站", "category": "subway", "district": "昌平", "lat": 40.0712, "lng": 116.3388, "lines": ["13号线"]},
    {"id": "SS_008", "name": "天通苑站", "category": "subway", "district": "昌平", "lat": 40.0981, "lng": 116.4213, "lines": ["5号线"]},
    {"id": "SS_009", "name": "通州北苑站", "category": "subway", "district": "通州", "lat": 39.9388, "lng": 116.6613, "lines": ["6号线"]},
    {"id": "SS_010", "name": "大兴新城站", "category": "subway", "district": "大兴", "lat": 39.7288, "lng": 116.3413, "lines": ["大兴线"]},
    # 公司
    {"id": "CP_001", "name": "百度", "category": "company", "district": "海淀", "lat": 40.0524, "lng": 116.3076},
    {"id": "CP_002", "name": "字节跳动", "category": "company", "district": "海淀", "lat": 40.0412, "lng": 116.3213},
    {"id": "CP_003", "name": "腾讯北京", "category": "company", "district": "海淀", "lat": 40.0388, "lng": 116.3088},
    {"id": "CP_004", "name": "微软中国", "category": "company", "district": "海淀", "lat": 40.0512, "lng": 116.3112},
    # 商圈
    {"id": "LM_001", "name": "中关村", "category": "landmark", "district": "海淀", "lat": 39.9824, "lng": 116.3076},
    {"id": "LM_002", "name": "国贸", "category": "landmark", "district": "朝阳", "lat": 39.9085, "lng": 116.4613},
    {"id": "LM_003", "name": "望京", "category": "landmark", "district": "朝阳", "lat": 40.0024, "lng": 116.4813},
    {"id": "LM_004", "name": "西二旗", "category": "landmark", "district": "海淀", "lat": 40.0979, "lng": 116.3076},
    {"id": "LM_005", "name": "回龙观", "category": "landmark", "district": "昌平", "lat": 40.0712, "lng": 116.3388},
    # 商超/公园
    {"id": "SH_001", "name": "龙湖长楹天街", "category": "shopping", "district": "朝阳", "lat": 39.9312, "lng": 116.5013},
    {"id": "SH_002", "name": "五彩城购物中心", "category": "shopping", "district": "海淀", "lat": 40.0788, "lng": 116.3213},
    {"id": "PK_001", "name": "奥林匹克森林公园", "category": "park", "district": "朝阳", "lat": 40.0312, "lng": 116.3913},
    {"id": "PK_002", "name": "颐和园", "category": "park", "district": "海淀", "lat": 39.9988, "lng": 116.2713},
]

# ── 生成房源数据 ───────────────────────────────────────────────────────────────
def _dist(lat1, lng1, lat2, lng2):
    """简单欧氏距离估算（米）"""
    dlat = (lat2 - lat1) * 111000
    dlng = (lng2 - lng1) * 111000 * math.cos(math.radians(lat1))
    return math.sqrt(dlat**2 + dlng**2)


def _gen_houses():
    random.seed(42)
    districts = ["海淀", "朝阳", "通州", "昌平", "大兴", "西城", "丰台", "顺义", "东城", "房山"]
    decorations = ["精装", "简装", "豪华", "毛坯", "空房"]
    orientations = ["朝南", "朝北", "朝东", "朝西", "南北", "东西"]
    noise_levels = ["安静", "中等", "吵闹", "临街"]
    statuses = ["可租"] * 18 + ["已租"] * 1 + ["下架"] * 1

    subway_stations = [l for l in LANDMARKS if l["category"] == "subway"]
    houses = []

    for i in range(1, 501):
        anchor = random.choice(subway_stations)
        dlat = random.uniform(-0.02, 0.02)
        dlng = random.uniform(-0.02, 0.02)
        lat = anchor["lat"] + dlat
        lng = anchor["lng"] + dlng

        district = anchor["district"]
        is_shared = random.random() < 0.5
        bedrooms = random.randint(1, 4) if not is_shared else random.randint(2, 4)
        area = round(random.uniform(12, 30), 1) if is_shared else round(random.uniform(22, 145), 1)
        base_price = 1500 if is_shared else bedrooms * 2000
        price = random.randint(int(base_price * 0.7), int(base_price * 1.5))
        price = max(500, min(25000, price))

        # 计算到最近地铁站距离
        min_dist = min(_dist(lat, lng, s["lat"], s["lng"]) for s in subway_stations)
        nearest = min(subway_stations, key=lambda s: _dist(lat, lng, s["lat"], s["lng"]))

        # 到西二旗通勤时间（粗略估算）
        xierqi = next(s for s in subway_stations if s["id"] == "SS_001")
        commute = int(_dist(lat, lng, xierqi["lat"], xierqi["lng"]) / 500 + 8)
        commute = min(95, max(8, commute))

        tags = []
        if min_dist <= 800:
            tags.append("近地铁")
        if min_dist <= 1000:
            tags.append("地铁可达")
        decoration = random.choice(decorations)
        if decoration in ["精装", "豪华"]:
            tags.append(decoration + "修")
        orientation = random.choice(orientations)
        if orientation in ["朝南", "南北"]:
            tags.append("采光好")
        has_elevator = random.random() > 0.3
        if has_elevator:
            tags.append("有电梯")
        if area >= 90:
            tags.append("大户型")
        elif area <= 30:
            tags.append("小户型")

        avail_days = random.randint(0, 30)
        avail_date = (date.today() + timedelta(days=avail_days)).isoformat()

        community = f"{nearest['name']}附近小区{(i % 20) + 1}号"
        platforms = ["链家", "安居客", "58同城"]

        house = {
            "house_id": f"HF_{i}",
            "community": community,
            "district": district,
            "area_name": nearest["name"],
            "address": f"北京市{district}区{community}",
            "bedrooms": bedrooms,
            "living_rooms": 1,
            "bathrooms": 1 if bedrooms <= 2 else 2,
            "area": area,
            "floor": random.randint(1, 30),
            "total_floors": random.randint(6, 33),
            "rental_type": "合租" if is_shared else "整租",
            "price": price,
            "decoration": decoration,
            "orientation": orientation,
            "elevator": has_elevator,
            "utilities_type": random.choice(["民水民电", "商水商电"]),
            "subway_station": nearest["name"],
            "subway_distance": int(min_dist),
            "subway_line": nearest.get("lines", ["未知"])[0],
            "commute_to_xierqi": commute,
            "available_from": avail_date,
            "noise_level": random.choice(noise_levels),
            "tags": tags,
            "status": random.choice(statuses),
            "lat": lat,
            "lng": lng,
            "listing_platform": random.choice(platforms),
        }
        houses.append(house)
    return houses


_ALL_HOUSES = _gen_houses()

# 用户视角的状态覆盖：{user_id: {house_id: status}}
_USER_STATUS: dict[str, dict[str, str]] = {}


def _get_status(user_id: str, house_id: str, default: str) -> str:
    return _USER_STATUS.get(user_id, {}).get(house_id, default)


def _set_status(user_id: str, house_id: str, status: str):
    if user_id not in _USER_STATUS:
        _USER_STATUS[user_id] = {}
    _USER_STATUS[user_id][house_id] = status


def _house_view(h: dict, user_id: str) -> dict:
    """返回用户视角的房源（状态可能被覆盖）"""
    v = dict(h)
    v["status"] = _get_status(user_id, h["house_id"], h["status"])
    return v


def _ok(data):
    return {"code": 0, "message": "success", "data": data}


def _require_user(x_user_id: Optional[str]):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-ID header")
    return x_user_id


# ── 地标接口 ──────────────────────────────────────────────────────────────────
@app.get("/api/landmarks")
def get_landmarks(category: Optional[str] = None, district: Optional[str] = None):
    result = LANDMARKS
    if category:
        result = [l for l in result if l["category"] == category]
    if district:
        result = [l for l in result if l["district"] == district]
    return _ok(result)


@app.get("/api/landmarks/stats")
def get_landmark_stats():
    from collections import Counter
    cats = Counter(l["category"] for l in LANDMARKS)
    return _ok({"total": len(LANDMARKS), "by_category": dict(cats)})


@app.get("/api/landmarks/search")
def search_landmarks(q: str, category: Optional[str] = None, district: Optional[str] = None):
    result = [l for l in LANDMARKS if q in l["name"]]
    if category:
        result = [l for l in result if l["category"] == category]
    if district:
        result = [l for l in result if l["district"] == district]
    return _ok(result)


@app.get("/api/landmarks/name/{name}")
def get_landmark_by_name(name: str):
    for l in LANDMARKS:
        if l["name"] == name:
            return _ok(l)
    raise HTTPException(status_code=404, detail="Landmark not found")


@app.get("/api/landmarks/{id}")
def get_landmark_by_id(id: str):
    for l in LANDMARKS:
        if l["id"] == id:
            return _ok(l)
    raise HTTPException(status_code=404, detail="Landmark not found")


# ── 房源接口 ──────────────────────────────────────────────────────────────────
@app.post("/api/houses/init")
def init_houses(x_user_id: Optional[str] = Header(None)):
    uid = _require_user(x_user_id)
    _USER_STATUS[uid] = {}
    return _ok({"action": "reset_user", "message": "该用户状态覆盖已清空，房源恢复为初始状态", "user_id": uid})


@app.get("/api/houses/stats")
def get_house_stats(x_user_id: Optional[str] = Header(None)):
    uid = _require_user(x_user_id)
    views = [_house_view(h, uid) for h in _ALL_HOUSES]
    from collections import Counter
    return _ok({
        "total": len(views),
        "by_status": dict(Counter(v["status"] for v in views)),
        "by_district": dict(Counter(v["district"] for v in views)),
        "by_bedrooms": dict(Counter(v["bedrooms"] for v in views)),
    })


# 具体路径路由必须在通配符 /{house_id} 之前
@app.get("/api/houses/listings/{house_id}")
def get_house_listings(house_id: str, x_user_id: Optional[str] = Header(None)):
    uid = _require_user(x_user_id)
    for h in _ALL_HOUSES:
        if h["house_id"] == house_id:
            v = _house_view(h, uid)
            items = [dict(v, listing_platform=p) for p in ["链家", "安居客", "58同城"]]
            return _ok({"total": 3, "page_size": 3, "items": items})
    raise HTTPException(status_code=404, detail="House not found")


@app.get("/api/houses/by_community")
def get_houses_by_community(
    community: str,
    listing_platform: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    platform = listing_platform or "安居客"
    result = [
        _house_view(h, uid) for h in _ALL_HOUSES
        if community in h["community"]
        and _get_status(uid, h["house_id"], h["status"]) == "可租"
        and (h["listing_platform"] == platform or platform == h["listing_platform"])
    ]
    return _ok(_paginate(result, page, page_size))


@app.get("/api/houses/by_platform")
def get_houses_by_platform(
    listing_platform: Optional[str] = None,
    district: Optional[str] = None,
    area: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    bedrooms: Optional[str] = None,
    rental_type: Optional[str] = None,
    decoration: Optional[str] = None,
    orientation: Optional[str] = None,
    elevator: Optional[str] = None,
    min_area: Optional[int] = None,
    max_area: Optional[int] = None,
    subway_line: Optional[str] = None,
    max_subway_dist: Optional[int] = None,
    subway_station: Optional[str] = None,
    utilities_type: Optional[str] = None,
    available_from_before: Optional[str] = None,
    commute_to_xierqi_max: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    platform = listing_platform or "安居客"

    result = []
    for h in _ALL_HOUSES:
        v = _house_view(h, uid)
        if v["status"] != "可租":
            continue
        if h["listing_platform"] != platform:
            continue
        if district and h["district"] not in district.split(","):
            continue
        if area and h["area_name"] not in area.split(","):
            continue
        if min_price and h["price"] < min_price:
            continue
        if max_price and h["price"] > max_price:
            continue
        if bedrooms and str(h["bedrooms"]) not in bedrooms.split(","):
            continue
        if rental_type and h["rental_type"] != rental_type:
            continue
        if decoration and decoration not in h["decoration"]:
            continue
        if orientation and h["orientation"] != orientation:
            continue
        if elevator is not None and str(h["elevator"]).lower() != elevator.lower():
            continue
        if min_area and h["area"] < min_area:
            continue
        if max_area and h["area"] > max_area:
            continue
        if subway_line and subway_line not in h.get("subway_line", ""):
            continue
        if max_subway_dist and h["subway_distance"] > max_subway_dist:
            continue
        if subway_station and subway_station not in h["subway_station"]:
            continue
        if utilities_type and h["utilities_type"] != utilities_type:
            continue
        if available_from_before and h["available_from"] > available_from_before:
            continue
        if commute_to_xierqi_max and h["commute_to_xierqi"] > commute_to_xierqi_max:
            continue
        result.append(v)

    # 排序
    if sort_by == "price":
        result.sort(key=lambda x: x["price"], reverse=(sort_order == "desc"))
    elif sort_by == "area":
        result.sort(key=lambda x: x["area"], reverse=(sort_order == "desc"))
    elif sort_by == "subway":
        result.sort(key=lambda x: x["subway_distance"], reverse=(sort_order == "desc"))

    return _ok(_paginate(result, page, page_size))


@app.get("/api/houses/nearby")
def get_houses_nearby(
    landmark_id: str,
    max_distance: float = 2000,
    listing_platform: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    platform = listing_platform or "安居客"

    # 支持按名称查找地标
    landmark = None
    for l in LANDMARKS:
        if l["id"] == landmark_id or l["name"] == landmark_id:
            landmark = l
            break
    if not landmark:
        raise HTTPException(status_code=404, detail="Landmark not found")

    result = []
    for h in _ALL_HOUSES:
        v = _house_view(h, uid)
        if v["status"] != "可租":
            continue
        if h["listing_platform"] != platform:
            continue
        d = _dist(h["lat"], h["lng"], landmark["lat"], landmark["lng"])
        if d > max_distance:
            continue
        v["distance_to_landmark"] = int(d)
        v["walking_distance"] = int(d * 1.3)
        v["walking_duration"] = round(d * 1.3 / 80, 1)  # 步行约80m/min
        result.append(v)

    result.sort(key=lambda x: x["distance_to_landmark"])
    return _ok(_paginate(result, page, page_size))


@app.get("/api/houses/nearby_landmarks")
def get_nearby_landmarks(
    community: str,
    type: Optional[str] = None,
    max_distance_m: float = 3000,
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    # 找到小区的坐标（用第一个匹配的房源）
    base = next((h for h in _ALL_HOUSES if community in h["community"]), None)
    if not base:
        return _ok([])

    cat_map = {"shopping": "shopping", "park": "park"}
    result = []
    for l in LANDMARKS:
        if type and l["category"] != cat_map.get(type, type):
            continue
        if l["category"] not in ("shopping", "park"):
            continue
        d = _dist(base["lat"], base["lng"], l["lat"], l["lng"])
        if d <= max_distance_m:
            result.append({**l, "distance_m": int(d)})

    result.sort(key=lambda x: x["distance_m"])
    return _ok(result)


# ── 租房操作 ──────────────────────────────────────────────────────────────────
@app.post("/api/houses/{house_id}/rent")
def rent_house(
    house_id: str,
    listing_platform: str = Query(...),
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    for h in _ALL_HOUSES:
        if h["house_id"] == house_id:
            _set_status(uid, house_id, "已租")
            return _ok({**_house_view(h, uid), "listing_platform": listing_platform})
    raise HTTPException(status_code=404, detail="House not found")


@app.post("/api/houses/{house_id}/terminate")
def terminate_rental(
    house_id: str,
    listing_platform: str = Query(...),
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    for h in _ALL_HOUSES:
        if h["house_id"] == house_id:
            _set_status(uid, house_id, "可租")
            return _ok({**_house_view(h, uid), "listing_platform": listing_platform})
    raise HTTPException(status_code=404, detail="House not found")


@app.post("/api/houses/{house_id}/offline")
def offline_house(
    house_id: str,
    listing_platform: str = Query(...),
    x_user_id: Optional[str] = Header(None),
):
    uid = _require_user(x_user_id)
    for h in _ALL_HOUSES:
        if h["house_id"] == house_id:
            _set_status(uid, house_id, "下架")
            return _ok({**_house_view(h, uid), "listing_platform": listing_platform})
    raise HTTPException(status_code=404, detail="House not found")


# 通配路由放最后，避免拦截具体路径
# 使用 Path 约束只匹配 HF_ 开头的 house_id
@app.get("/api/houses/{house_id:path}")
def get_house_by_id(house_id: str = Path(..., regex="^HF_"), x_user_id: Optional[str] = Header(None)):
    uid = _require_user(x_user_id)
    for h in _ALL_HOUSES:
        if h["house_id"] == house_id:
            return _ok(_house_view(h, uid))
    raise HTTPException(status_code=404, detail="House not found")


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def _paginate(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": total, "page": page, "page_size": page_size, "items": items[start:end]}


if __name__ == "__main__":
    uvicorn.run("mock_server:app", host="0.0.0.0", port=8080, reload=False)

"""租房仿真 API 封装"""
import httpx
from src.config import RENT_API_BASE, USER_ID

HEADERS = {"X-User-ID": USER_ID}
TIMEOUT = 10.0


async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        r = await client.get(f"{RENT_API_BASE}{path}", params=params, headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def _post(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        r = await client.post(f"{RENT_API_BASE}{path}", params=params, headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def init_houses() -> dict:
    """重置房源数据到初始状态"""
    return await _post("/api/houses/init")


async def search_houses(
    district: str = None,
    area: str = None,
    min_price: int = None,
    max_price: int = None,
    bedrooms: str = None,
    rental_type: str = None,
    decoration: str = None,
    orientation: str = None,
    elevator: str = None,
    min_area: int = None,
    max_area: int = None,
    subway_line: str = None,
    max_subway_dist: int = None,
    subway_station: str = None,
    utilities_type: str = None,
    available_from_before: str = None,
    commute_to_xierqi_max: int = None,
    listing_platform: str = None,
    sort_by: str = None,
    sort_order: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询可租房源，支持多条件筛选"""
    params = {k: v for k, v in locals().items() if v is not None}
    return await _get("/api/houses/by_platform", params)


async def get_house_detail(house_id: str) -> dict:
    """获取单套房源详情"""
    return await _get(f"/api/houses/{house_id}")


async def get_house_listings(house_id: str) -> dict:
    """获取房源在各平台的挂牌记录"""
    return await _get(f"/api/houses/listings/{house_id}")


async def get_houses_by_community(community: str, listing_platform: str = None, page_size: int = 20) -> dict:
    """按小区名查询可租房源"""
    params = {"community": community, "page_size": page_size}
    if listing_platform:
        params["listing_platform"] = listing_platform
    return await _get("/api/houses/by_community", params)


async def get_houses_nearby(
    landmark_id: str,
    max_distance: float = 2000,
    listing_platform: str = None,
    page_size: int = 20,
) -> dict:
    """以地标为圆心查附近房源"""
    params = {"landmark_id": landmark_id, "max_distance": max_distance, "page_size": page_size}
    if listing_platform:
        params["listing_platform"] = listing_platform
    return await _get("/api/houses/nearby", params)


async def get_nearby_landmarks(community: str, type: str = None, max_distance_m: float = 3000) -> dict:
    """查询小区周边地标（商超/公园）"""
    params = {"community": community, "max_distance_m": max_distance_m}
    if type:
        params["type"] = type
    return await _get("/api/houses/nearby_landmarks", params)


async def rent_house(house_id: str, listing_platform: str = "安居客") -> dict:
    """租房"""
    return await _post(f"/api/houses/{house_id}/rent", {"listing_platform": listing_platform})


async def terminate_rental(house_id: str, listing_platform: str = "安居客") -> dict:
    """退租"""
    return await _post(f"/api/houses/{house_id}/terminate", {"listing_platform": listing_platform})


async def offline_house(house_id: str, listing_platform: str = "安居客") -> dict:
    """下架房源"""
    return await _post(f"/api/houses/{house_id}/offline", {"listing_platform": listing_platform})

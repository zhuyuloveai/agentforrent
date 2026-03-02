"""地标 API 封装"""
import httpx
from src.config import RENT_API_BASE

TIMEOUT = 10.0


async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        r = await client.get(f"{RENT_API_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


async def search_landmarks(q: str, category: str = None, district: str = None) -> dict:
    """关键词模糊搜索地标"""
    params = {"q": q}
    if category:
        params["category"] = category
    if district:
        params["district"] = district
    return await _get("/api/landmarks/search", params)


async def get_landmark_by_name(name: str) -> dict:
    """按名称精确查询地标"""
    return await _get(f"/api/landmarks/name/{name}")


async def get_landmarks(category: str = None, district: str = None) -> dict:
    """获取地标列表"""
    params = {}
    if category:
        params["category"] = category
    if district:
        params["district"] = district
    return await _get("/api/landmarks", params)

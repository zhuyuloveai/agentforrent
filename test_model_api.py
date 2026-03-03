"""
使用 DashScope Qwen 对比 agentforrent vs AgentGame 两种调用方式。
用法：python test_model_api.py
"""
import asyncio
import json
import time
import httpx

# ── Qwen 配置（替代真实评测模型）────────────────────────────────
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_API_KEY  = "sk-c215a6597a284c9ca699f57aa6c0646e"
QWEN_MODEL    = "qwen-plus"   # 轻量快速，适合测试
TIMEOUT       = 120.0
# ─────────────────────────────────────────────────────────────

TEST_CASES = [
    "帮我找海淀区两居室，预算8000以内，要近地铁",
    "我想在朝阳区找精装整租，有电梯",
]

SYSTEM_PROMPT = """你是一个北京租房助手，帮助用户查询和筛选房源。
当用户询问房源时，必须调用工具查询，不要编造房源ID。
查询完成后只输出JSON：{"message": "说明", "houses": ["HF_x"]}"""

TOOLS_FULL = [
    {
        "type": "function",
        "function": {
            "name": "search_houses",
            "description": "查询可租房源，支持多条件筛选。当用户提到区域、价格、户型、地铁、装修等需求时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {"type": "string", "description": "行政区，逗号分隔，如 海淀,朝阳"},
                    "area": {"type": "string", "description": "商圈，逗号分隔，如 西二旗,上地"},
                    "min_price": {"type": "integer", "description": "最低月租金（元）"},
                    "max_price": {"type": "integer", "description": "最高月租金（元）"},
                    "bedrooms": {"type": "string", "description": "卧室数，逗号分隔，如 1,2"},
                    "rental_type": {"type": "string", "description": "整租 或 合租"},
                    "decoration": {"type": "string", "description": "装修：精装/简装/豪华/毛坯/空房"},
                    "orientation": {"type": "string", "description": "朝向：朝南/朝北/南北 等"},
                    "elevator": {"type": "string", "description": "是否有电梯：true/false"},
                    "min_area": {"type": "integer", "description": "最小面积（平米）"},
                    "max_area": {"type": "integer", "description": "最大面积（平米）"},
                    "subway_line": {"type": "string", "description": "地铁线路，如 13号线"},
                    "max_subway_dist": {"type": "integer", "description": "最大地铁距离（米），近地铁填800"},
                    "subway_station": {"type": "string", "description": "地铁站名，如 西二旗站"},
                    "utilities_type": {"type": "string", "description": "水电类型，如 民水民电"},
                    "available_from_before": {"type": "string", "description": "最晚可入住日期，YYYY-MM-DD"},
                    "commute_to_xierqi_max": {"type": "integer", "description": "到西二旗通勤时间上限（分钟）"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                    "sort_by": {"type": "string", "description": "排序字段：price/area/subway"},
                    "sort_order": {"type": "string", "description": "asc 或 desc"},
                    "page_size": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_detail",
            "description": "获取单套房源的详细信息，包括地址、户型、租金、设施、噪音等。",
            "parameters": {
                "type": "object",
                "properties": {"house_id": {"type": "string", "description": "房源ID，如 HF_2001"}},
                "required": ["house_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取房源在各平台的挂牌记录。",
            "parameters": {
                "type": "object",
                "properties": {"house_id": {"type": "string"}},
                "required": ["house_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_by_community",
            "description": "按小区名查询该小区下的可租房源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                    "page_size": {"type": "integer"},
                },
                "required": ["community"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_landmarks",
            "description": "关键词模糊搜索地标（地铁站、公司、商圈）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "category": {"type": "string"},
                    "district": {"type": "string"},
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_by_name",
            "description": "按名称精确查询地标。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_nearby",
            "description": "以地标为圆心查询附近可租房源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string"},
                    "max_distance": {"type": "number"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                    "page_size": {"type": "integer"},
                },
                "required": ["landmark_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rent_house",
            "description": "租下指定房源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminate_rental",
            "description": "退租。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "offline_house",
            "description": "将房源下架。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_landmarks",
            "description": "查询某小区周边的商超或公园。",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string"},
                    "type": {"type": "string"},
                    "max_distance_m": {"type": "number"},
                },
                "required": ["community"],
            },
        },
    },
]


async def call_qwen(label: str, messages: list, tools: list, temperature: float, max_tokens: int = 0):
    payload_size = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False))
    print(f"\n{'─'*60}")
    print(f"▶ {label}")
    print(f"  tools: {len(tools)}个  temp: {temperature}  max_tokens: {max_tokens or '不限'}  payload: {payload_size/1024:.1f}KB")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {QWEN_API_KEY}",
    }
    payload = {
        "model": QWEN_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "enable_thinking": False,
    }
    if tools:
        payload["tools"] = tools
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{QWEN_BASE_URL}/chat/completions", json=payload, headers=headers)
            elapsed = time.time() - t0
            if r.status_code == 200:
                data = r.json()
                choice = data["choices"][0]
                msg = choice["message"]
                finish = choice.get("finish_reason")
                usage = data.get("usage", {})
                tool_calls = msg.get("tool_calls") or []
                content = msg.get("content") or ""
                print(f"  ✅ {r.status_code}  耗时: {elapsed:.1f}s  finish: {finish}")
                print(f"  tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}")
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc["function"]
                        print(f"  🔧 tool_call: {fn['name']}({fn.get('arguments', '')[:120]})")
                if content:
                    print(f"  💬 content: {content[:200]}")
                return {"ok": True, "elapsed": elapsed, "usage": usage, "tool_calls": tool_calls, "content": content}
            else:
                print(f"  ❌ {r.status_code}  耗时: {elapsed:.1f}s  {r.text[:200]}")
                return {"ok": False, "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ {type(e).__name__}: {e}  耗时: {elapsed:.1f}s")
        return {"ok": False, "elapsed": elapsed}


async def main():
    print(f"模型: {QWEN_MODEL}  基地址: {QWEN_BASE_URL}")
    results = {}

    for msg in TEST_CASES:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg},
        ]
        print(f"\n{'='*60}")
        print(f"测试消息: 「{msg}」")

        # ── 方式A: agentforrent 旧（tools + temp=1.0 + 无max_tokens）
        r_a = await call_qwen(
            "agentforrent 旧方式：11个tools + temp=1.0 + 无max_tokens",
            messages, TOOLS_FULL, temperature=1.0, max_tokens=0,
        )

        # ── 方式B: agentforrent 新（tools + temp=0.3 + max_tokens=1024）
        r_b = await call_qwen(
            "agentforrent 新方式：11个tools + temp=0.3 + max_tokens=1024",
            messages, TOOLS_FULL, temperature=0.3, max_tokens=1024,
        )

        # ── 方式C: AgentGame（无tools + temp=0.3 + max_tokens=1024）
        r_c = await call_qwen(
            "AgentGame 方式：无tools + temp=0.3 + max_tokens=1024",
            messages, [], temperature=0.3, max_tokens=1024,
        )

        results[msg] = {"旧": r_a, "新": r_b, "AgentGame": r_c}

    # ── 汇总对比 ──
    print(f"\n{'='*60}")
    print("汇总对比")
    print(f"{'─'*60}")
    print(f"{'消息':<20} {'方式':<20} {'耗时':>6}  {'tokens':>8}  tool_call")
    print(f"{'─'*60}")
    for msg, rs in results.items():
        short_msg = msg[:18] + ".." if len(msg) > 18 else msg
        for label, r in rs.items():
            if r.get("ok"):
                usage = r.get("usage", {})
                tcs = [tc["function"]["name"] for tc in r.get("tool_calls", [])]
                print(f"{short_msg:<20} {label:<20} {r['elapsed']:>5.1f}s  {usage.get('total_tokens', '?'):>8}  {tcs or r.get('content','')[:30]}")


if __name__ == "__main__":
    asyncio.run(main())

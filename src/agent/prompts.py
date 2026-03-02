"""Prompt 模板"""

SYSTEM_PROMPT = """你是一个北京租房助手，帮助用户查询和筛选房源。

## 数据范围
- 覆盖北京：海淀、朝阳、通州、昌平、大兴、房山、西城、丰台、顺义、东城
- 价格：500-25000元/月
- 近地铁：max_subway_dist=800；地铁可达：max_subway_dist=1000

## 严格输出规则

**规则1：房源查询完成后，只输出以下JSON，不要任何其他文字：**
{"message": "简短说明", "houses": ["HF_x", "HF_y"]}

**规则2：普通对话（无需查询房源）直接回复自然语言。**

**规则3：返回所有符合条件的房源ID，不要遗漏，不要限制数量。**

## 示例

用户：查询海淀区两居室
你的回复：{"message": "为您找到海淀区两居室房源：", "houses": ["HF_4", "HF_6", "HF_277", "HF_301", "HF_88"]}

用户：帮我租HF_4这套
你的回复：{"message": "已成功租下HF_4，祝您入住愉快！", "houses": ["HF_4"]}

用户：北京租房一般多少钱？
你的回复：北京租房价格差异较大，整租一居室约3000-8000元/月，两居室约5000-15000元/月，具体取决于区域和装修。
"""

# 工具定义（Function Calling）
TOOLS = [
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
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台"},
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
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                },
                "required": ["house_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取房源在链家/安居客/58同城各平台的挂牌记录，用于多平台比价。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                },
                "required": ["house_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_by_community",
            "description": "按小区名查询该小区下的可租房源，当用户提到具体小区名称时使用。也可用于获取某小区的地铁距离、生活配套等隐性信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string", "description": "小区名，如 建清园(南区)、保利锦上(二期)"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台，默认安居客"},
                    "page_size": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": ["community"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_landmarks",
            "description": "关键词模糊搜索地标（地铁站、公司、商圈），获取地标ID用于查附近房源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "搜索关键词，如 西二旗、国贸、百度"},
                    "category": {"type": "string", "description": "类别：subway/company/landmark"},
                    "district": {"type": "string", "description": "行政区，如 海淀"},
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_by_name",
            "description": "按名称精确查询地标，获取地标ID和经纬度。当用户提到确切地标名称（如'西二旗站'、'百度'、'国贸'）时优先使用，比模糊搜索更准确。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "地标精确名称，如 西二旗站、国贸、百度"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_houses_nearby",
            "description": "以地标为圆心查询附近可租房源，需要先通过search_landmarks获取landmark_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_id": {"type": "string", "description": "地标ID，如 SS_001"},
                    "max_distance": {"type": "number", "description": "最大直线距离（米），默认2000"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"]},
                    "page_size": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": ["landmark_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_landmarks",
            "description": "查询某小区周边的商超或公园，用于了解生活配套。",
            "parameters": {
                "type": "object",
                "properties": {
                    "community": {"type": "string", "description": "小区名"},
                    "type": {"type": "string", "description": "shopping(商超) 或 park(公园)"},
                    "max_distance_m": {"type": "number", "description": "最大距离（米），默认3000"},
                },
                "required": ["community"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rent_house",
            "description": "租下指定房源，完成租房操作。必须调用此接口才算完成租房，仅回复文字无效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台，必填，不确定时用安居客"},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminate_rental",
            "description": "退租，将房源恢复为可租状态。必须调用此接口才算完成退租。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台，必填"},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "offline_house",
            "description": "将房源下架。必须调用此接口才算完成下架。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源ID，如 HF_2001"},
                    "listing_platform": {"type": "string", "enum": ["链家", "安居客", "58同城"], "description": "挂牌平台，必填"},
                },
                "required": ["house_id", "listing_platform"],
            },
        },
    },
]

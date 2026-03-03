"""
测试用例定义 —— 覆盖 Chat（5分）/ Single（10-15分）/ Multi（20-30分）三种题型。

目标总分：~805分（56个用例）
  Chat           10用例 ×  5 =  50分
  Single Simple  15用例 × 10 = 150分
  Single Complex 15用例 × 15 = 225分
  Multi Medium   10用例 × 20 = 200分
  Multi Complex   6用例 × 30 = 180分
  合计            56用例      = 805分

设计原则：
  - Chat：0 或极少 LLM 调用，任何响应即满分
  - Single Simple：1-2 个筛选维度，单工具调用，基准集 5-25 套
  - Single Complex：3+ 筛选维度或多工具调用链，基准集 1-15 套
  - Multi Medium：2-3 轮纯查询，测试条件累积/修正，按最终轮命中率评分
  - Multi Complex：3-5 轮含写操作，查询命中率（50%）+ 写操作双重验证（50%）

评分公式（查询类）：
  得分 = |agent返回 ∩ 基准集| / |基准集| × 满分

写操作双重验证（各占写操作分的 50%）：
  1. API 状态验证：GET /api/houses/{id} 确认状态变更
  2. houses 字段验证：response.houses 包含被操作的 house_id

工具覆盖矩阵（11/11）：
  search_houses           ✅ S/SC/M/MC 多类型覆盖
  get_house_detail        ✅ SC5, SC12, MC6
  get_house_listings      ✅ SC8（平台比价场景）
  get_houses_by_community ✅ SC6, M5（小区查询场景）
  get_houses_nearby       ✅ SC4, SC13, MC5
  get_nearby_landmarks    ✅ SC12（周边配套场景）
  search_landmarks        ✅ SC4, SC13
  get_landmark_by_name    ✅ SC13（精确地标名查询）
  rent_house              ✅ MC1, MC3, MC5, MC6
  terminate_rental        ✅ MC3
  offline_house           ✅ MC2, MC4

search_houses 参数覆盖：
  district                ✅ 覆盖 10 个行政区（朝阳/海淀/丰台/昌平/通州/大兴/西城/东城/顺义）
  rental_type             ✅ 整租/合租
  bedrooms                ✅ 1/2/3 居
  max_price               ✅
  min_price               ✅ S7, M10（新增）
  decoration              ✅ 精装/简装
  elevator                ✅
  subway_station          ✅
  max_subway_dist         ✅
  subway_line             ✅ S11, SC9, M7（新增）
  orientation             ✅ S9, M5（新增，如 mock server 支持）
  min_area / max_area     ✅ S12, SC10（新增）
  available_from_before   ✅ SC11（新增，如 mock server 支持）
  commute_to_xierqi_max   ✅
  sort_by / sort_order    ✅

基准集大小说明（[S]=1-5套，[M]=6-20套，[L]=21+套）：
  S1  朝阳+整租            ~26套 [L]  ← 注意：测试 agent 是否传大 page_size
  S4  海淀+精装            ~32套 [L]  ← 同上
  SC1 海淀+两居+精装+8000    1套 [S]
  SC2 西二旗站+800m+整租     2套 [S]
  SC3 通勤<=30+整租+两居    11套 [M]
  SC4 nearby(国贸站,1000m)   2套 [S]
  MC3 朝阳+整租+一居         5套 [S]
  其余新用例基准集大小待 baseline.py 实测确认
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class WriteOp:
    """写操作期望验证"""
    house_id: str           # 被操作的 house_id；"dynamic"=运行时从工具结果中提取
    action: str             # rent / terminate / offline
    expected_status: str    # 已租 / 可租 / 下架
    platform: str = "安居客"  # 写操作使用的平台


@dataclass
class NearbyBaseline:
    """nearby API 基准集（已知 landmark_id）"""
    landmark_id: str        # 地标 ID，如 SS_005
    max_distance: float     # 最大距离（米）


@dataclass
class LandmarkNameBaseline:
    """nearby API 基准集（运行时动态查找 landmark_id）"""
    name: str               # 地标名称，如 百度、知春路站
    max_distance: float     # 最大距离（米）
    category: str = None    # subway / company / landmark（可选过滤）


@dataclass
class TestCase:
    id: str                                      # 用例编号
    name: str                                    # 简短描述
    case_type: str                               # Chat / Single / Multi
    full_score: int                              # 满分

    turns: List[str]                             # 用户输入序列

    # 基准集来源（五选一；Chat 类全部为 None）
    baseline_query: Optional[Dict] = None        # 直接调用 /api/houses/by_platform
    baseline_queries: Optional[List[Dict]] = None  # 多次调用 /api/houses/by_platform 取并集（用于跨区OR查询）
    baseline_house_id: Optional[str] = None      # 固定单套（详情/写操作场景）
    baseline_nearby: Optional[NearbyBaseline] = None          # 已知 landmark_id 的附近查询
    baseline_landmark: Optional[LandmarkNameBaseline] = None  # 动态查找 landmark 的附近查询
    baseline_community: Optional[str] = None     # 小区名 → /api/houses/by_community

    # 写操作验证列表（按轮次顺序）
    write_ops: List[WriteOp] = field(default_factory=list)

    # 必须调用的工具列表（验证工具链路；空列表=不检查）
    # 若指定工具未被成功调用，按缺失比例扣减得分
    required_tools: List[str] = field(default_factory=list)

    notes: str = ""


# ══════════════════════════════════════════════════════════════
# Chat 类（5分）：任何响应即满分，测试零/极少 token 路径
# ══════════════════════════════════════════════════════════════
CHAT_CASES: List[TestCase] = [
    TestCase(
        id="C1", name="基础问候", case_type="Chat", full_score=5,
        turns=["你好"],
        notes="期望模板回复，0次LLM调用",
    ),
    TestCase(
        id="C2", name="功能咨询", case_type="Chat", full_score=5,
        turns=["你能帮我做什么"],
        notes="自然语言介绍功能，不应触发工具调用",
    ),
    TestCase(
        id="C3", name="租房价格知识", case_type="Chat", full_score=5,
        turns=["北京租房大概多少钱"],
        notes="通用知识问答，不需要查询房源",
    ),
    TestCase(
        id="C4", name="超范围拒答", case_type="Chat", full_score=5,
        turns=["上海有房源吗"],
        notes="覆盖地域外请求，应礼貌说明只覆盖北京",
    ),
    TestCase(
        id="C5", name="租房术语解释", case_type="Chat", full_score=5,
        turns=["整租和合租有什么区别"],
        notes="知识解释类，无需工具",
    ),
    TestCase(
        id="C6", name="合同术语解释", case_type="Chat", full_score=5,
        turns=["押一付三是什么意思"],
        notes="押金/付款方式术语，纯知识回答",
    ),
    TestCase(
        id="C7", name="租房注意事项", case_type="Chat", full_score=5,
        turns=["北京租房需要注意什么"],
        notes="经验性建议，不应触发房源查询",
    ),
    TestCase(
        id="C8", name="次卧概念", case_type="Chat", full_score=5,
        turns=["什么是次卧"],
        notes="房型术语解释，无需工具",
    ),
    TestCase(
        id="C9", name="预算有限建议", case_type="Chat", full_score=5,
        turns=["我刚毕业预算不多，有什么租房建议"],
        notes="经验建议类，不触发具体房源查询",
    ),
    TestCase(
        id="C10", name="性价比区域咨询", case_type="Chat", full_score=5,
        turns=["北京哪个区租房性价比最高"],
        notes="通用知识，不触发工具",
    ),
]


# ══════════════════════════════════════════════════════════════
# Single Simple 类（10分）：1-2 维度，单次 search_houses 调用
# ══════════════════════════════════════════════════════════════
SINGLE_SIMPLE_CASES: List[TestCase] = [
    TestCase(
        id="S1", name="区域+租型", case_type="Single", full_score=10,
        turns=["查询朝阳区整租房源"],
        baseline_query={"district": "朝阳", "rental_type": "整租", "page_size": 100},
        notes="实测基准 ~26 套 [L]；核心考点：agent 是否传大 page_size，否则 20/26≈77% 命中率",
    ),
    TestCase(
        id="S2", name="价格+户型", case_type="Single", full_score=10,
        turns=["月租5000以内的一居室"],
        baseline_query={"max_price": 5000, "bedrooms": "1", "page_size": 100},
    ),
    TestCase(
        id="S3", name="设施+户型+租型", case_type="Single", full_score=10,
        turns=["有电梯的整租两居室"],
        baseline_query={"elevator": "true", "bedrooms": "2", "rental_type": "整租", "page_size": 100},
    ),
    TestCase(
        id="S4", name="区域+装修", case_type="Single", full_score=10,
        turns=["海淀区精装修房源有哪些"],
        baseline_query={"district": "海淀", "decoration": "精装", "page_size": 100},
        notes="实测基准 ~32 套 [L]；核心考点同 S1，测试大结果集的 page_size 传递",
    ),
    TestCase(
        id="S5", name="整租三居室", case_type="Single", full_score=10,
        turns=["北京有哪些整租三居室"],
        baseline_query={"rental_type": "整租", "bedrooms": "3", "page_size": 100},
        notes="实测基准 ~15 套 [M]",
    ),
    TestCase(
        id="S6", name="区域+租型+户型（通州）", case_type="Single", full_score=10,
        turns=["通州区整租两居室有哪些"],
        baseline_query={"district": "通州", "rental_type": "整租", "bedrooms": "2", "page_size": 100},
        notes="覆盖通州区，基准集待测",
    ),
    TestCase(
        id="S7", name="价格区间+区域+户型", case_type="Single", full_score=10,
        turns=["海淀区月租2000到5000的整租一居室"],
        baseline_query={
            "district": "海淀", "rental_type": "整租", "bedrooms": "1",
            "min_price": 2000, "max_price": 5000, "page_size": 100,
        },
        notes="测试 min_price 参数映射，基准集待测",
    ),
    TestCase(
        id="S8", name="区域+装修（昌平）", case_type="Single", full_score=10,
        turns=["昌平区精装修的房源有哪些"],
        baseline_query={"district": "昌平", "decoration": "精装", "page_size": 100},
        notes="覆盖昌平区，基准集待测",
    ),
    TestCase(
        id="S9", name="区域+朝向+租型", case_type="Single", full_score=10,
        turns=["朝阳区朝南的整租房源"],
        baseline_query={"district": "朝阳", "orientation": "朝南", "rental_type": "整租", "page_size": 100},
        notes="测试 orientation 参数映射；若 mock server 不支持 orientation，基准集将为空或全量",
    ),
    TestCase(
        id="S10", name="区域+租型+户型（丰台）", case_type="Single", full_score=10,
        turns=["丰台区整租两居室"],
        baseline_query={"district": "丰台", "rental_type": "整租", "bedrooms": "2", "page_size": 100},
        notes="覆盖丰台区，基准集待测",
    ),
    TestCase(
        id="S11", name="地铁线路+租型+户型", case_type="Single", full_score=10,
        turns=["13号线沿线整租两居室"],
        baseline_query={"subway_line": "13号线", "rental_type": "整租", "bedrooms": "2", "page_size": 100},
        notes="测试 subway_line 参数映射；若 mock server 不支持，基准集为空",
    ),
    TestCase(
        id="S12", name="面积下限+租型+户型", case_type="Single", full_score=10,
        turns=["面积80平以上的整租两居室"],
        baseline_query={"min_area": 80, "rental_type": "整租", "bedrooms": "2", "page_size": 100},
        notes="测试 min_area 参数映射，基准集待测",
    ),
    TestCase(
        id="S13", name="区域+合租+户型", case_type="Single", full_score=10,
        turns=["丰台区合租一居室有哪些"],
        baseline_query={"district": "丰台", "rental_type": "合租", "bedrooms": "1", "page_size": 100},
        notes="测试合租场景，基准集待测",
    ),
    TestCase(
        id="S14", name="区域+租型+户型（大兴）", case_type="Single", full_score=10,
        turns=["大兴区整租一居室"],
        baseline_query={"district": "大兴", "rental_type": "整租", "bedrooms": "1", "page_size": 100},
        notes="覆盖大兴区，基准集待测",
    ),
    TestCase(
        id="S15", name="区域+租型+户型（西城）", case_type="Single", full_score=10,
        turns=["西城区整租两居室"],
        baseline_query={"district": "西城", "rental_type": "整租", "bedrooms": "2", "page_size": 100},
        notes="覆盖西城区，基准集待测",
    ),
]


# ══════════════════════════════════════════════════════════════
# Single Complex 类（15分）：3+ 维度或多工具调用链
# ══════════════════════════════════════════════════════════════
SINGLE_COMPLEX_CASES: List[TestCase] = [
    TestCase(
        id="SC1", name="四维精确筛选", case_type="Single", full_score=15,
        turns=["海淀区两居室精装修月租8000以内"],
        baseline_query={
            "district": "海淀", "bedrooms": "2", "decoration": "精装",
            "max_price": 8000, "page_size": 100,
        },
        notes="实测基准 1 套 [HF_438]，精确命中理论满分",
    ),
    TestCase(
        id="SC2", name="地铁站+距离+租型", case_type="Single", full_score=15,
        turns=["西二旗站800米内的整租房源"],
        baseline_query={
            "subway_station": "西二旗站", "max_subway_dist": 800,
            "rental_type": "整租", "page_size": 100,
        },
        notes="实测基准 2 套 [HF_355, HF_384]，测试 subway_station+max_subway_dist 参数映射",
    ),
    TestCase(
        id="SC3", name="通勤时间筛选", case_type="Single", full_score=15,
        turns=["通勤到西二旗在30分钟内的整租两居室"],
        baseline_query={
            "commute_to_xierqi_max": 30, "rental_type": "整租",
            "bedrooms": "2", "page_size": 100,
        },
        notes="实测基准 11 套 [M]，测试 commute_to_xierqi_max 参数映射",
    ),
    TestCase(
        id="SC4", name="地标附近查房（search_landmarks→nearby）", case_type="Single", full_score=15,
        turns=["国贸附近1公里内的房源"],
        baseline_landmark=LandmarkNameBaseline(name="国贸站", max_distance=1000, category="subway"),
        notes="实测基准 2 套 [HF_331, HF_369]；基准集动态查找国贸站 landmark_id"
              "（原硬编码 SS_005 改为动态解析，与 mock server 数据解耦）；"
              "agent 应走 search_landmarks/get_landmark_by_name→get_houses_nearby",
    ),
    TestCase(
        id="SC5", name="单套房源详情", case_type="Single", full_score=15,
        turns=["查询HF_280的详细信息"],
        baseline_house_id="HF_280",
        notes="get_house_detail 调用，基准集=[HF_280]，理论满分",
    ),
    TestCase(
        id="SC6", name="小区查询（get_houses_by_community）", case_type="Single", full_score=15,
        turns=["建清园小区有哪些可租房源"],
        baseline_community="建清园",
        notes="测试 get_houses_by_community 工具；基准集 = 建清园小区的全部可租房源",
    ),
    TestCase(
        id="SC7", name="跨区域+三维筛选", case_type="Single", full_score=15,
        turns=["海淀或朝阳区整租两居室精装修有哪些"],
        baseline_queries=[
            {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "page_size": 100},
            {"district": "朝阳", "rental_type": "整租", "bedrooms": "2", "decoration": "精装", "page_size": 100},
        ],
        notes="基准集 = 海淀 + 朝阳 各自查询结果取并集（支持逗号分隔的 API 已废弃此设计）；"
              "agent 应对每个区分别调用 search_houses（规则6），结果合并后与基准集比对。",
    ),
    TestCase(
        id="SC8", name="平台挂牌信息（get_house_listings）", case_type="Single", full_score=15,
        turns=["查询HF_180在各平台的挂牌价格"],
        baseline_house_id="HF_180",
        required_tools=["get_house_listings"],
        notes="测试 get_house_listings 工具；未调用该工具则得分×0（required_tools 机制）",
    ),
    TestCase(
        id="SC9", name="地铁线路+四维精确筛选", case_type="Single", full_score=15,
        turns=["13号线沿线精装修整租两居室月租8000以内"],
        baseline_query={
            "subway_line": "13号线", "decoration": "精装",
            "rental_type": "整租", "bedrooms": "2", "max_price": 8000, "page_size": 100,
        },
        notes="测试 subway_line 参数在多条件下的映射，基准集待测；若 mock server 不支持 subway_line 则为空",
    ),
    TestCase(
        id="SC10", name="面积区间+朝向+电梯+租型", case_type="Single", full_score=15,
        turns=["朝南有电梯面积60到100平的整租房"],
        baseline_query={
            "orientation": "朝南", "elevator": "true",
            "min_area": 60, "max_area": 100, "rental_type": "整租", "page_size": 100,
        },
        notes="测试 orientation/min_area/max_area 参数映射；若 orientation 不支持则基准集偏大",
    ),
    TestCase(
        id="SC11", name="可入住时间+区域+租型+户型", case_type="Single", full_score=15,
        turns=["3月20日前可以入住的海淀区整租一居室"],
        baseline_query={
            "available_from_before": "2026-03-20", "district": "海淀",
            "rental_type": "整租", "bedrooms": "1", "page_size": 100,
        },
        notes="测试 available_from_before 参数；若 mock server 不支持则基准集为全量",
    ),
    TestCase(
        id="SC12", name="详情+周边配套（detail+get_nearby_landmarks）", case_type="Single", full_score=15,
        turns=["查看HF_100的详细信息，并告诉我周边有什么商超"],
        baseline_house_id="HF_100",
        required_tools=["get_house_detail", "get_nearby_landmarks"],
        notes="测试 get_house_detail + get_nearby_landmarks 两工具链路；"
              "每缺少一个必要工具得分减半（required_tools 机制）",
    ),
    TestCase(
        id="SC13", name="精确地标名查找附近（get_landmark_by_name→nearby）", case_type="Single", full_score=15,
        turns=["百度公司附近1公里内的整租两居室"],
        baseline_landmark=LandmarkNameBaseline(name="百度", max_distance=1000, category="company"),
        notes="测试 get_landmark_by_name/search_landmarks（category=company）→ get_houses_nearby 链路；"
              "baseline_landmark 运行时动态解析百度的 landmark_id",
    ),
    TestCase(
        id="SC14", name="区域+装修+租型+价格区间", case_type="Single", full_score=15,
        turns=["东城区精装修整租月租6000到12000"],
        baseline_query={
            "district": "东城", "decoration": "精装", "rental_type": "整租",
            "min_price": 6000, "max_price": 12000, "page_size": 100,
        },
        notes="覆盖东城区，测试价格区间双端；基准集待测",
    ),
    TestCase(
        id="SC15", name="区域+租型+户型+价格上限（顺义）", case_type="Single", full_score=15,
        turns=["顺义区整租两居室月租6000以内"],
        baseline_query={
            "district": "顺义", "rental_type": "整租",
            "bedrooms": "2", "max_price": 6000, "page_size": 100,
        },
        notes="覆盖顺义区，基准集待测",
    ),
]


# ══════════════════════════════════════════════════════════════
# Multi Medium 类（20分）：2-3 轮纯查询，测试多轮条件累积/修正
# ══════════════════════════════════════════════════════════════
MULTI_MEDIUM_CASES: List[TestCase] = [
    TestCase(
        id="M1", name="三轮条件递进", case_type="Multi", full_score=20,
        turns=[
            "我想在朝阳区找房",
            "要两居室的",
            "月租10000以内，要精装修",
        ],
        baseline_query={
            "district": "朝阳", "bedrooms": "2",
            "max_price": 10000, "decoration": "精装", "page_size": 100,
        },
        notes="实测基准 3 套 [S]，第3轮 agent 必须携带全部累积条件",
    ),
    TestCase(
        id="M2", name="两轮筛选+排序", case_type="Multi", full_score=20,
        turns=[
            "找海淀区近地铁的房源",
            "只看整租的，按价格从低到高排",
        ],
        baseline_query={
            "district": "海淀", "max_subway_dist": 800,
            "rental_type": "整租", "sort_by": "price", "sort_order": "asc",
            "page_size": 100,
        },
        notes="实测基准 ~10 套 [M]，测试排序参数在多轮中的正确传递",
    ),
    TestCase(
        id="M3", name="条件修正（两居→三居）", case_type="Multi", full_score=20,
        turns=[
            "朝阳区整租两居室有哪些",
            "算了，改成三居室，其他条件不变",
        ],
        baseline_query={
            "district": "朝阳", "rental_type": "整租", "bedrooms": "3", "page_size": 100,
        },
        notes="测试条件替换而非累加；agent 第2轮应用 bedrooms=3 替换 bedrooms=2",
    ),
    TestCase(
        id="M4", name="两轮筛选+新维度（精装+电梯+排序）", case_type="Multi", full_score=20,
        turns=[
            "找海淀区精装修的整租房",
            "要有电梯的两居室，按价格从低到高排",
        ],
        baseline_query={
            "district": "海淀", "decoration": "精装", "rental_type": "整租",
            "elevator": "true", "bedrooms": "2", "sort_by": "price", "sort_order": "asc",
            "page_size": 100,
        },
        notes="测试多维度条件跨轮累积，基准集待测",
    ),
    TestCase(
        id="M5", name="三轮朝向+户型+价格区间", case_type="Multi", full_score=20,
        turns=[
            "找朝南的整租房",
            "要两居室",
            "月租6000到10000",
        ],
        baseline_query={
            "orientation": "朝南", "rental_type": "整租",
            "bedrooms": "2", "min_price": 6000, "max_price": 10000, "page_size": 100,
        },
        notes="测试 orientation+min_price 参数在多轮中累积；orientation 需 mock server 支持",
    ),
    TestCase(
        id="M6", name="价格上限调整（条件更新）", case_type="Multi", full_score=20,
        turns=[
            "月租5000以内的整租两居室",
            "预算可以高一点，改成8000以内",
        ],
        baseline_query={
            "rental_type": "整租", "bedrooms": "2", "max_price": 8000, "page_size": 100,
        },
        notes="测试 max_price 条件的替换更新，基准集待测",
    ),
    TestCase(
        id="M7", name="两轮区域+地铁线路", case_type="Multi", full_score=20,
        turns=[
            "昌平区的整租房有哪些",
            "要13号线附近的一居室",
        ],
        baseline_query={
            "district": "昌平", "subway_line": "13号线",
            "rental_type": "整租", "bedrooms": "1", "page_size": 100,
        },
        notes="测试 district+subway_line 跨轮累积；subway_line 需 mock server 支持，基准集待测",
    ),
    TestCase(
        id="M8", name="两轮区域+精装+电梯", case_type="Multi", full_score=20,
        turns=[
            "大兴区整租两居室有哪些",
            "要精装修的，而且要有电梯",
        ],
        baseline_query={
            "district": "大兴", "rental_type": "整租",
            "bedrooms": "2", "decoration": "精装", "elevator": "true", "page_size": 100,
        },
        notes="覆盖大兴区的多轮场景，基准集待测",
    ),
    TestCase(
        id="M9", name="三轮区域+租型+装修+排序", case_type="Multi", full_score=20,
        turns=[
            "西城区的两居室",
            "整租的，要精装修",
            "按价格从低到高排一下",
        ],
        baseline_query={
            "district": "西城", "bedrooms": "2", "rental_type": "整租",
            "decoration": "精装", "sort_by": "price", "sort_order": "asc", "page_size": 100,
        },
        notes="覆盖西城区，三轮累积含排序，基准集待测",
    ),
    TestCase(
        id="M10", name="两轮通勤+户型+价格区间", case_type="Multi", full_score=20,
        turns=[
            "通勤到西二旗30分钟以内的整租房",
            "要两居室，月租6000到10000",
        ],
        baseline_query={
            "commute_to_xierqi_max": 30, "rental_type": "整租",
            "bedrooms": "2", "min_price": 6000, "max_price": 10000, "page_size": 100,
        },
        notes="测试 commute+min_price+max_price 跨轮累积，基准集待测",
    ),
]


# ══════════════════════════════════════════════════════════════
# Multi Complex 类（30分）：3-5 轮含写操作，双重评分
#   查询命中率（50%）+ 写操作双重验证（50%）
# ══════════════════════════════════════════════════════════════
MULTI_COMPLEX_CASES: List[TestCase] = [
    TestCase(
        id="MC1", name="多轮筛选后租房", case_type="Multi", full_score=30,
        turns=[
            "帮我找朝阳区的整租两居室",
            "月租10000以内",
            "按价格从低到高排",
            "租第一套，用链家平台",
        ],
        baseline_query={
            "district": "朝阳", "rental_type": "整租", "bedrooms": "2",
            "max_price": 10000, "sort_by": "price", "sort_order": "asc",
            "page_size": 100,
        },
        write_ops=[
            WriteOp(house_id="dynamic", action="rent", expected_status="已租", platform="链家"),
        ],
        notes="4 轮（3 查询轮 + 1 写操作轮）；写操作 house_id 从工具结果动态提取",
    ),
    TestCase(
        id="MC2", name="查看详情后下架", case_type="Multi", full_score=30,
        turns=[
            "查一下HF_150的详细信息",
            "帮我把这套房源下架，用安居客",
        ],
        baseline_house_id="HF_150",
        write_ops=[
            WriteOp(house_id="HF_150", action="offline", expected_status="下架", platform="安居客"),
        ],
        notes="固定 house_id=HF_150；第1轮 get_house_detail，第2轮 offline_house；"
              "验证：API状态=offline + houses含HF_150",
    ),
    TestCase(
        id="MC3", name="租房后退租", case_type="Multi", full_score=30,
        turns=[
            "朝阳区整租一居室有哪些",
            "租第一套，用58同城",
            "我反悔了，把刚才那套退租",
        ],
        baseline_query={
            "district": "朝阳", "rental_type": "整租", "bedrooms": "1", "page_size": 100,
        },
        write_ops=[
            WriteOp(house_id="dynamic", action="rent", expected_status="可租", platform="58同城"),
            WriteOp(house_id="dynamic", action="terminate", expected_status="可租", platform="58同城"),
        ],
        notes="实测基准 5 套 [S]；先租后退租，最终状态恢复 available",
    ),
    TestCase(
        id="MC4", name="搜索后动态下架", case_type="Multi", full_score=30,
        turns=[
            "海淀区整租两居室有哪些",
            "帮我把第一套下架，用链家",
        ],
        baseline_query={
            "district": "海淀", "rental_type": "整租", "bedrooms": "2", "page_size": 100,
        },
        write_ops=[
            WriteOp(house_id="dynamic", action="offline", expected_status="下架", platform="链家"),
        ],
        notes="测试 search→offline 链路（dynamic house_id）；与 MC2 的 detail→offline 互补",
    ),
    TestCase(
        id="MC5", name="不指定平台的租房（默认值验证）", case_type="Multi", full_score=30,
        turns=[
            "帮我找朝阳区精装修整租两居室",
            "月租10000以内的",
            "帮我租第一套",
        ],
        baseline_query={
            "district": "朝阳", "rental_type": "整租", "bedrooms": "2",
            "decoration": "精装", "max_price": 10000, "page_size": 100,
        },
        write_ops=[
            WriteOp(house_id="dynamic", action="rent", expected_status="已租", platform="安居客"),
        ],
        notes="用户未指定平台；测试 listing_platform 默认值（安居客）的 P0 Bug 修复；"
              "agent 必须传 listing_platform 否则 API 400 → 0 分",
    ),
    TestCase(
        id="MC6", name="多步筛选+详情+租房", case_type="Multi", full_score=30,
        turns=[
            "海淀区整租两居室精装修有哪些",
            "月租8000以内的",
            "帮我看看第一套的详细信息",
            "就租这套，安居客",
        ],
        baseline_query={
            "district": "海淀", "rental_type": "整租", "bedrooms": "2",
            "decoration": "精装", "max_price": 8000, "page_size": 100,
        },
        write_ops=[
            WriteOp(house_id="dynamic", action="rent", expected_status="已租", platform="安居客"),
        ],
        notes="4 轮（search→search→detail→rent）；基准集与 SC1 相同（~1套 HF_438）；"
              "理论得分：查询命中=15 + 写操作=15 = 30/30",
    ),
]


# ══════════════════════════════════════════════════════════════
# 全部用例汇总（按分值升序）
# ══════════════════════════════════════════════════════════════
ALL_CASES: List[TestCase] = (
    CHAT_CASES
    + SINGLE_SIMPLE_CASES
    + SINGLE_COMPLEX_CASES
    + MULTI_MEDIUM_CASES
    + MULTI_COMPLEX_CASES
)

# 各类型分值汇总
SCORE_SUMMARY = {
    "Chat": {
        "count": len(CHAT_CASES),
        "full": sum(c.full_score for c in CHAT_CASES),
    },
    "Single": {
        "count": len(SINGLE_SIMPLE_CASES + SINGLE_COMPLEX_CASES),
        "full": sum(c.full_score for c in SINGLE_SIMPLE_CASES + SINGLE_COMPLEX_CASES),
    },
    "Multi": {
        "count": len(MULTI_MEDIUM_CASES + MULTI_COMPLEX_CASES),
        "full": sum(c.full_score for c in MULTI_MEDIUM_CASES + MULTI_COMPLEX_CASES),
    },
    "Total": {
        "count": len(ALL_CASES),
        "full": sum(c.full_score for c in ALL_CASES),
    },
}

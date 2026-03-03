# 用例失分完整分析指南
> 基于 test_results_full3.log + trace JSON + debug_runner 实测验证
> 分析时间：2026-03-03

---

## 一、全局得分概览

```
Chat  (10用例)   50 / 50   100.0%  ← 全满分
Single(30用例)  245 / 375   65.3%  ← 失130分
Multi (16用例)  265 / 380   69.7%  ← 失115分
─────────────────────────────────────
合计 (56用例)   560 / 805   69.6%  ← 失245分
```

**所有失分用例的共同特征**：测试框架打印 `[!] 警告：基准集为空，查询部分将得0分`。

---

## 二、失分机制深度解析

### 2.1 "基准集为空"是如何触发的？

评分框架（`runner.py`）在运行每个用例前，先通过直接调用 API 预查基准集：

```python
# runner.py _get_baseline()
data = await _api_get("/api/houses/by_platform", case.baseline_query)
baseline = [h["house_id"] for h in data["data"]["items"]]

# 评分时：
if not baseline:
    return 0.0   # 基准集为空 → 纯查询类直接0分
```

**触发条件**：`baseline_query` 对应的 API 调用返回 `total=0`。  
**关键推论**：基准集是由框架直接查 API 得到的，与 agent 行为无关。只要 API 返回空，无论 agent 做了什么，该用例的查询分都是 0。

### 2.2 Mock Server 的数据结构

`mock_server.py` 的关键设计：

```python
# 1. 房源数量：500套，random.seed(42)固定生成
# 2. 地铁站锚点（决定 district 分布）：
subway_stations = [
    {"id": "SS_001", "district": "海淀"},  # 西二旗
    {"id": "SS_002", "district": "海淀"},  # 上地
    {"id": "SS_003", "district": "海淀"},  # 五道口
    {"id": "SS_004", "district": "海淀"},  # 知春路
    {"id": "SS_005", "district": "朝阳"},  # 国贸
    {"id": "SS_006", "district": "朝阳"},  # 望京
    {"id": "SS_007", "district": "昌平"},  # 回龙观
    {"id": "SS_008", "district": "昌平"},  # 天通苑
    {"id": "SS_009", "district": "通州"},  # 通州北苑
    {"id": "SS_010", "district": "大兴"},  # 大兴新城
]
# 结果：每套房的 district 由其锚定的地铁站决定
# district分布：海淀~200套, 朝阳~100套, 昌平~100套, 通州~50套, 大兴~50套
# 西城/东城/丰台/顺义/房山 = 0套 ← 没有对应地铁站！
```

**核心结论：西城、东城、丰台、顺义、房山 在 mock server 中没有任何房源**，因为数据生成时没有为这些区设置地铁站锚点。这不是偶然的数据稀疏，而是**系统性缺失**。

### 2.3 listing_platform 过滤的隐性影响

```python
# mock_server.py by_platform API
platform = listing_platform or "安居客"   # 默认安居客
if h["listing_platform"] != platform:
    continue   # 只返回指定平台的房源
```

500套房源中，每套被随机分配到 链家/安居客/58同城 之一（约各1/3）。
**runner.py 的 baseline_query 和 agent 的 search_houses 默认都不传 `listing_platform`**，所以双方都只看到约167套（安居客部分）。

这是评分框架的设计一致性保证，不会导致误判，但影响了数据总量：
- 真实可查的海淀精装整租房源 = 8套（安居客），不是24套
- 这进一步压缩了精装整租两居室的概率

---

## 三、逐用例根因深度分析

### 分类一：系统性区域数据缺失（9个用例，约145分）

#### 涉及用例
S6、S10、S13、S15、SC14、SC15、M9（西城/丰台/通州/东城/顺义）

#### 根因
Mock server 的房源生成逻辑以地铁站为锚点，未覆盖以下区域的地铁站：

| 缺失区域 | 理应对应的地铁站 | 失分用例 |
|---------|----------------|---------|
| 西城区 | 西单/长安街 | S15、M9 |
| 东城区 | 王府井/东四 | SC14 |
| 丰台区 | 方庄/菜市口 | S10、S13 |
| 通州区 | 通州北苑（仅SS_009 1个） | S6 |
| 顺义区 | 天竺/首都机场 | SC15 |

**通州稍特殊**：有SS_009但生成的房源较少（约50套），且经过 `listing_platform=安居客` 过滤后约16套，整租两居室恰好为0。

#### 验证命令
```bash
python -m test.debug_runner --preset s6   # 通州验证
python -m test.debug_runner --preset s15  # 西城验证
```

#### 修复方向
在 `mock_server.py` 的 `subway_stations` 列表中为缺失区域添加地铁站：
```python
{"id": "SS_011", "name": "西单站", "category": "subway", "district": "西城", ...},
{"id": "SS_012", "name": "王府井站", "category": "subway", "district": "东城", ...},
{"id": "SS_013", "name": "方庄站", "category": "subway", "district": "丰台", ...},
{"id": "SS_014", "name": "顺义站", "category": "subway", "district": "顺义", ...},
```
然后重新生成或手动补充这些区的房源数据。

---

### 分类二：特定查询对象无数据（2个用例，30分）

#### SC6 — 建清园小区（15分）

**trace（test_SC6_31_t1.json）**：
```json
"arguments": {"community": "建清园"},
"result_summary": "total=0, sample=[]"
```

**根因**：`get_houses_by_community` API 用模糊匹配 `community in h["community"]`，而 mock server 中小区名格式为 `"{站名}附近小区{N}号"`，不包含"建清园"。

**SC6 是测试设计问题**：用了一个真实存在的北京小区名，但 mock server 的小区名均为系统生成格式，不可能包含真实小区名。

**修复方向**：要么在 mock data 中手动注册建清园小区的几套房源，要么将测试用例改为使用 mock server 实际生成的小区名格式（如 `西二旗站附近小区1号`）。

---

#### SC13 — 百度公司附近整租两居室（15分）

**Trace（test_SC13_38_t1.json）分析**：
```json
// 轮1：get_landmark_by_name("百度") 
"result_summary": "total=0, sample=[]"   ← tracer用houses格式解析，实际返回了CP_001

// 轮2：agent正确使用了CP_001
"arguments": {"landmark_id": "CP_001", "max_distance": 1000}
"result_summary": "total=0, sample=[]"   ← CP_001 (40.0524, 116.3076) 附近1km确实无房
```

**两个独立的根因**：
1. Tracer 的 `result_summary` 字段对非 houses 类工具结果（地标搜索）按 houses 格式解析，显示 `total=0`，但实际上 agent 从中正确提取了 `landmark_id=CP_001`，行为是正确的。
2. CP_001（百度，海淀区，坐标 40.0524/116.3076）附近1公里内，经过 `listing_platform=安居客` 过滤后，恰好没有可租房源。

**Tracer 诊断误导问题**：`result_summary` 字段仅在工具返回包含 `items` 列表时有效，对地标 API 返回格式（单个对象）解析失败显示 `total=0`，不代表工具调用失败。建议 tracer 针对不同工具类型生成不同格式的摘要。

**修复方向**：在百度公司(CP_001)附近补充几套可租房源数据。

---

### 分类三：数据分布稀疏（精装整租无两居室，3个用例，55分）

#### SC7 — 海淀或朝阳区精装整租两居室（15分）

**初始误判**：以为是 API 不支持逗号分隔 district。

**验证结果**（debug_runner --preset sc7）：
```
[NG] [  0] district=海淀,朝阳  decoration=精装 rental_type=整租 bedrooms=2
[NG] [  0] district=海淀        decoration=精装 rental_type=整租 bedrooms=2  ← 单区域也是0
[NG] [  0] district=朝阳        decoration=精装 rental_type=整租 bedrooms=2  ← 单区域也是0
```

**逗号实际已支持**（mock_server.py L314）：
```python
if district and h["district"] not in district.split(","):
    continue
```

**真实根因**：海淀精装整租8套的户型分布为 [1居×4, 3居×2, 4居×2]，恰好无2居室。朝阳精装整租也无2居室。这是 `random.seed(42)` 产生的偶然户型分布，不是API限制。

**深层问题**：Cases.py 的注释写"请先确认 API 支持逗号分隔"，说明测试设计时已知该风险，但选择性忽视了，也未验证数据本身是否存在。**测试用例在上线前应先执行 `baseline_query` 确认返回非空**，否则该用例永远得0分，浪费评分配额。

---

#### M4 — 海淀精装+电梯+两居室排序（20分）

**Trace（test_M4_44_t2.json）**：
```json
// 轮2 参数正确：district=海淀, decoration=精装, rental_type=整租, bedrooms=2, elevator=true
"result_summary": "total=0, sample=[]"
```

**debug_runner --preset m4 验证**：
```
[NG] [  0] district=海淀 decoration=精装 rental_type=整租 bedrooms=2 elevator=true
[NG] [  0] district=海淀 decoration=精装 rental_type=整租 bedrooms=2   ← 去掉电梯也是0！
[OK] [  8] district=海淀 decoration=精装 rental_type=整租
    HF_39(1居) HF_157(3居) HF_351(1居) HF_355(4居)
    HF_384(1居) HF_425(3居) HF_454(1居) HF_469(4居)
```

**根因**：电梯不是问题，2居室才是。海淀8套精装整租全是1/3/4居，无2居室。
此外，M4 轮2耗时35秒（出现 ConnectError，重试3次），但这只影响耗时，不影响结论。

**深层问题**：M4 测试的是"多轮筛选+新维度"能力，但选择了一个数据上不存在的终态。正确的测试设计应先验证该终态数据存在（baseline_query非空），再设计测试用例。

---

#### M5 — 朝南整租两居室月租6000-10000（20分）

**Trace 三轮分析**：
- 轮1 `orientation=朝南, rental_type=整租` → 13套
- 轮2 `+ bedrooms=2` → 1套（HF_352，5446元/月）
- 轮3 `+ min_price=6000, max_price=10000` → 0套

**根因**：全北京朝南整租两居室只有1套（HF_352=5446元），而 min_price=6000 要求月租≥6000，HF_352=5446不满足，结果为空。

**问题本质**：这是数据极端稀疏下的死角测试——测试用例期望的数据点（朝南+整租+两居室+6000-10000）恰好不存在。Baseline_query 在用例设计时未验证。

---

### 分类四：Agent 多轮约束管理缺陷（1个用例，20分，唯一Agent缺陷）

#### M7 — 昌平整租+13号线一居室（20分）

**Trace 对比**：

| 轮次 | 用户输入 | Agent 传参 | 返回 |
|------|---------|-----------|------|
| 轮1 | "昌平区的整租房有哪些" | `{district=昌平, rental_type=整租}` | 17套 ✓ |
| 轮2 | "要13号线附近的一居室" | `{subway_line=13号线, bedrooms=1, rental_type=整租}` | 10套 |

**Agent 行为缺陷**：轮2 传参中 `district=昌平` 被遗漏。按规则5（系统提示）应累积为 `{district=昌平, subway_line=13号线, bedrooms=1, rental_type=整租}`。

**但即使修复 Agent 也无法得分**：
```
[NG] [  0] district=昌平 subway_line=13号线 rental_type=整租 bedrooms=1  ← 0套
[OK] [  2] district=昌平 rental_type=整租 bedrooms=1                    ← 2套
```
昌平整租一居室(HF_43/HF_444)的 `subway_line = "13号线"` 字段不是13号线，所以加了 subway_line 过滤后结果为0。

**问题的两个维度**：
1. **Agent 缺陷**：district 约束在多轮对话中丢失，违反了系统提示规则5。即使有时不影响得分（本例因数据不存在），这个行为在其他测试中可能导致结果偏差。从 test_M7_47_t2.json 可见，agent 用 subway_line 替换而非叠加了 district。
2. **测试设计缺陷**：昌平区的房源锚定在回龙观(SS_007)和天通苑(SS_008)，这两站属于13号线/5号线，但 mock_server 中 `subway_line` 字段取 `nearest["lines"][0]`（第一条线路），SS_007的第一条线是"13号线"，SS_008的第一条是"5号线"。因此昌平房源的 subway_line 约各一半是"13号线"和"5号线"。但昌平整租一居室只有2套（HF_43/HF_444），通过probe查这2套发现均不含subway_line="13号线"（可能锚定在天通苑5号线）。这是小样本偶然性问题。

---

### 分类五：写操作连锁失败（1个用例，失15分）

#### MC5 — 不指定平台的租房（30分，得15分）

**评分机制特殊行为**：
```python
# runner.py
query_score = (
    _calc_hit_rate_score(query_houses, baseline, full_score * 0.5)
    if baseline else full_score * 0.5   # ← 基准集空 → 查询直接给满分50%
)
```

MC5 得分 = 查询满分(15) + 写操作(0) = 15/30

**三轮 Trace 分析**：
- 轮1：`{district=朝阳, decoration=精装, bedrooms=2, rental_type=整租}` → total=0（朝阳区无精装整租两居室）
- 轮2：追加 `max_price=10000` 仍然0套（数据本身不存在）
- 轮3："帮我租第一套" → Agent 无工具调用，正确回复"没有房源，无法租"

**Agent 行为正确**，但因上游数据空缺导致写操作无法执行。这是"分类一"问题的连锁效应——朝阳区确实有精装房源但无整租两居室。

**评分机制 quirk 分析**：MC6 同样基准集为空但得30/30（写操作成功），MC5 基准集为空但因写操作失败只得15/30。说明在 Multi Complex 用例中，**基准集是否为空不影响查询部分得分，但写操作必须真实成功**。这个评分设计倾向于优先验证写操作能力。

---

## 四、跨用例横向分析

### 4.1 数据覆盖矩阵

```
                    通州  丰台  西城  东城  顺义  朝阳  海淀  昌平  大兴
整租两居室           NG    NG    NG    -     NG    OK    NG    OK    OK
整租一居室           -     NG    -     -     -     OK    OK    OK    OK
精装整租             -     -     NG    -     -     -     OK    OK    -
精装整租两居室        -     -     -     NG    -     NG    NG    -     -
```

说明：NG=数据存在但查询结果0；空白=未测试；OK=有数据

**关键发现**：
- 海淀精装整租有数据，但全是1/3/4居，**无2居室**
- 朝阳整租两居室有数据，但精装的为0
- 昌平在13号线沿线有整租数据，但一居室恰好不在13号线锚点

### 4.2 Mock Server 约束汇总

| 约束类型 | 是否支持 | 注意事项 |
|---------|---------|---------|
| `district` 单值 | ✓ | |
| `district` 逗号分隔 | ✓ | `district.split(",")` |
| `bedrooms` 单值 | ✓ | 传字符串"2"，不是整数 |
| `bedrooms` 逗号分隔 | ✓ | `bedrooms.split(",")` |
| `decoration` | ✓ | 模糊匹配：`decoration in h["decoration"]`，"精装"可匹配"精装修" |
| `elevator` | ✓ | 传字符串"true"/"false" |
| `subway_line` | ✓ | 精确匹配，"13号线"匹配"13号线" |
| `orientation` | ✓ | 精确匹配，"朝南"匹配"朝南" |
| `commute_to_xierqi_max` | ✓ | |
| `available_from_before` | ✓ | 字符串日期比较 |
| `listing_platform` | ✓ | **未传默认安居客**（约1/3数据） |

### 4.3 评分机制关键特性

| 场景 | 评分行为 |
|------|---------|
| 纯查询 + baseline为空 | **0分**（`_calc_hit_rate_score` 返回0.0） |
| 含写操作 + baseline为空 | **查询满分（50%）**，写操作正常评分 |
| 含写操作 + baseline非空 | 查询按命中率，写操作正常评分 |
| required_tools 缺失 | 得分 × (命中数/总数) |

**MC6 得 30/30 的原因**：baseline为空（海淀精装整租两居室查询0套），查询自动给15分；写操作 rent 成功，得15分；合计30/30。这解释了为什么 MC6 看似 "精装" 条件被 agent 在轮2忽略了（agent轮2传的是 `{district=海淀, rental_type=整租, bedrooms=2, max_price=8000}`，去掉了精装），反而得了满分。

---

## 五、Agent 行为质量分析

### 5.1 得分验证——Agent 参数传递能力

在16个失分用例中，**15个用例的 agent 参数传递完全正确**（tool call `success=true`，参数语义准确），失分原因是数据问题。

唯一有参数质量问题的用例：
- **M7**：轮2 `district=昌平` 被遗漏，违反系统提示规则5

### 5.2 系统提示规则覆盖情况

| 规则 | 内容 | 执行情况 |
|------|------|---------|
| 规则1 | 工具调用后输出JSON `{message, houses}` | ✓ 稳定执行 |
| 规则2 | 普通对话直接回复自然语言 | ✓ 稳定执行 |
| 规则3 | houses字段包含所有房源ID | ✓ 基本执行 |
| 规则4 | search_houses传page_size=100 | ✓ 所有trace均有page_size=100 |
| 规则5 | **多轮对话严格叠加历史约束** | ⚠️ M7轮2发生约束丢失 |
| 规则6 | "A或B区"分两次调用合并 | ✓ SC7 trace中传了`district=海淀,朝阳`（用逗号，合法但与规则描述不同） |

**规则5观察**：M7是唯一的失败案例，但该规则的违反在其他成功用例中未出现（M1三轮递进、M3条件修正、MC1四轮等均正确）。M7的特殊性在于：轮2用户提到了一个"替代性"的位置描述（13号线）可能让模型判断为"位置条件替换"而非"新增"，引发了条件混淆。

**规则6观察**：agent 对SC7的处理是用逗号分隔而非分两次调用。从结果来看逗号分隔是有效的（API支持），与规则6描述"API不支持逗号分隔"矛盾。规则6的说明有误（API实际支持逗号），但最终结果一样（两种方式均能覆盖双区域数据）。

---

## 六、改进优先级与行动建议

### P0：补充 Mock Server 区域数据（预计可回收 ~145分）

```python
# mock_server.py LANDMARKS 中补充以下地铁站：
{"id": "SS_011", "name": "西单站",    "district": "西城", "lines": ["4号线", "1号线"], ...},
{"id": "SS_012", "name": "东四站",    "district": "东城", "lines": ["5号线"],         ...},
{"id": "SS_013", "name": "六里桥站",  "district": "丰台", "lines": ["10号线", "9号线"],...},
{"id": "SS_014", "name": "顺义站",    "district": "顺义", "lines": ["15号线"],         ...},
```
同时为建清园小区和百度公司附近手动注册若干房源。

**影响用例**：S6、S10、S13、S15、SC6、SC13、SC14、SC15、M9、MC5（连锁）

### P1：修正数据分布保证测试用例有效性（预计可回收 ~55分）

当前海淀精装整租（安居客）8套全为非2居室，属于小样本偶然性。建议：
- 手动注入2-3套海淀精装整租两居室房源（修复 SC7/M4 base case）
- 注入1套朝南整租两居室月租7000-9000的房源（修复 M5）
- 验证通勤西二旗30分内是否存在整租两居室月租6000-10000（修复 M10）

**验证工作流**：修改数据后，运行 `python -m test.debug_runner --preset all_failed` 确认所有查询从 `[NG]` 变为 `[OK]`，再执行正式测试。

### P2：修复 Agent 多轮约束管理（预计可直接回收 0分，但提升健壮性）

M7 即使修复 agent 也因数据问题得0分，但多轮约束丢失会在其他边界场景中导致用户体验问题。

建议在系统提示规则5中增加反例强化：
```
**规则5（多轮约束叠加）补充说明：**
- 地理约束（district/subway_line/subway_station）需要特别注意：
  - 用户说"要13号线附近的" → 补充地铁线路约束，保留原有区域约束
  - 用户说"改成13号线沿线" → 替换地理约束
  - 关键词"要"/"加上"/"还需要" → 叠加；"改成"/"换成" → 替换
```

### P3：测试用例设计规范（过程改进）

**根本问题**：多个用例在设计时未验证 `baseline_query` 返回非空，导致"永远得0分"的用例进入评测。

建议增加测试用例验证前置步骤：
```python
# 在 cases.py 中增加辅助函数，或在 debug_runner 中增加用例验证模式
python -m test.debug_runner --validate-baselines   # 检查所有用例的baseline是否非空
```
任何 baseline 为空的用例应标记为 `skip=True` 或修复数据后再纳入评测。

---

## 七、调测工具快速参考

```bash
# 全量验证数据状态
python -m test.debug_runner --preset all_failed

# 分组验证（含对比查询，定位具体断层）
python -m test.debug_runner --preset sc7    # 区域精装两居室
python -m test.debug_runner --preset m4    # 精装整租户型分布
python -m test.debug_runner --preset m7    # 昌平+地铁线路交集
python -m test.debug_runner --preset sc9   # 13号线装修叠加

# 单用例精细调试（agent参数vs baseline完整对比）
python -m test.debug_runner --id M7

# 自定义参数验证（参数无中文时可用CLI，含中文建议用文件）
python -m test.debug_runner --api-probe "commute_to_xierqi_max=30 bedrooms=2"
python -m test.debug_runner --api-probe-file probes/custom.json

# 地标数据验证
python -m test.debug_runner --probe-landmark 百度 --landmark-category company --landmark-radius 1000
```

---

## 八、结论

```
失分 245分的全貌：
  ├── 系统性区域数据缺失（无地铁站覆盖）   约145分   P0 ← 数据补充即可解决
  ├── 数据分布稀疏（户型/价格区间无交集）   约55分    P1 ← 注入少量数据解决
  ├── 特定对象无数据（小区/地标）           约30分    P1 ← 注入具体数据解决
  ├── Agent多轮约束丢失 (M7)               20分      P2 ← 仅此1例，且数据问题掩盖了
  └── 写操作连锁失败 (MC5)                 15分      自动随P0修复

Agent 能力质量：14/16失分用例中参数传递完全正确，Chat/Single/Multi通过率均>60%
核心问题：不是Agent能力不足，而是测试数据未覆盖部分区域
```

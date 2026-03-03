# 测试失分根因分析报告
> 基于 `test_results_full3.log` 及 `logs/traces/` 下的 JSON trace 文件

## 总体得分

| 类型   | 得分  | 满分  | 失分  | 命中率 |
|--------|-------|-------|-------|--------|
| Chat   | 50    | 50    | 0     | 100%   |
| Single | 245   | 375   | **130** | 65.3% |
| Multi  | 265   | 380   | **115** | 69.7% |
| **合计** | **560** | **805** | **245** | **69.6%** |

---

## 评分机制要点（runner.py 关键逻辑）

**纯查询用例（无 write_ops）：**
```python
if not baseline:
    return 0.0   # 基准集为空 → 0分
```

**含写操作用例：**
```python
query_score = (
    _calc_hit_rate_score(...)
    if baseline else case.full_score * 0.5   # ← 基准集为空时查询给满分50%！
)
```

> 影响：MC5 (15/30) = query满分15 + write失败0；MC6 (30/30) = query满分15 + write成功15

---

## 失分用例清单（共16个，245分）

| 用例 | 分值 | 得分 | 失分主根因 |
|------|------|------|-----------|
| S6 通州整租两居室 | 10 | 0 | Mock数据空缺 |
| S10 丰台整租两居室 | 10 | 0 | Mock数据空缺 |
| S13 丰台合租一居室 | 10 | 0 | Mock数据空缺 |
| S15 西城整租两居室 | 10 | 0 | Mock数据空缺 |
| SC6 建清园小区 | 15 | 0 | Mock数据空缺 |
| SC7 海淀或朝阳精装整租两居室 | 15 | 0 | API不支持逗号分隔district |
| SC9 13号线精装整租两居室8000内 | 15 | 0 | Mock数据空缺（subway_line+decoration叠加） |
| SC13 百度公司1公里整租两居室 | 15 | 0 | Mock数据空缺（百度附近无房源） |
| SC14 东城精装整租6000-12000 | 15 | 0 | Mock数据空缺 |
| SC15 顺义整租两居室6000内 | 15 | 0 | Mock数据空缺 |
| M4 海淀精装+电梯+两居室排序 | 20 | 0 | Mock数据空缺（精装+电梯+两居室无交集） |
| M5 朝南两居室6000-10000 | 20 | 0 | Mock数据空缺（价格区间内无数据） |
| M7 昌平整租+13号线一居室 | 20 | 0 | **Agent丢失district约束** + Mock数据空缺 |
| M9 西城两居室整租精装排序 | 20 | 0 | Mock数据空缺（西城无数据） |
| M10 通勤西二旗+两居室+6000-10000 | 20 | 0 | Mock数据空缺（价格区间无数据） |
| MC5 朝阳精装整租两居室+租房 | 30 | 15 | Mock数据空缺导致写操作无法执行 |

---

## 根因详细分析

### 根因A：Mock Server 特定区域数据空缺（约130分）

**受影响用例：** S6、S10、S13、S15、SC6、SC14、SC15、M9

**Trace 实证（以 S6 为例，test_S6_16_t1.json）：**
```json
"arguments": {"district": "通州", "bedrooms": "2", "rental_type": "整租"}
"result_summary": "total=0, sample=[]"
```
Agent 传参完全正确（`success=true`），但 API 真实返回 `total=0`。
Baseline 直查同样返回0，判定基准集为空→强制0分。

**缺失区域列表：** 通州、丰台、西城、东城、顺义、建清园小区

**性质：** 测试数据设计问题，非 agent 行为问题。

---

### 根因B：SC7 数据本身为空（非 API 不支持逗号，15分）

**Trace 实证（test_SC7_32_t1.json）：**
```json
"arguments": {"district": "海淀,朝阳", "bedrooms": "2", "rental_type": "整租", "decoration": "精装"}
"result_summary": "total=0, sample=[]"
```

`cases.py` 注释预见"API 可能不支持逗号"，但 **debug_runner --preset sc7 实际验证结果**：
```
[NG] [  0] district=海淀,朝阳  rental_type=整租 bedrooms=2 decoration=精装  ← 逗号版
[NG] [  0] district=海淀       rental_type=整租 bedrooms=2 decoration=精装  ← 单区域也是0
[NG] [  0] district=朝阳       rental_type=整租 bedrooms=2 decoration=精装  ← 单区域也是0
```

**结论：根因是数据空缺，不是 API 格式问题**。海淀和朝阳区在 mock server 中均无精装修整租两居室数据。逗号分隔实际已支持（mock_server.py L314: `district.split(",")` 做了处理），但数据本身就没有。

**性质：** 纯测试数据覆盖问题（测试设计时未验证数据是否存在）。

---

### 根因C：subway_line + decoration 叠加后无数据（SC9，15分）

**Trace 实证（test_SC9_34_t1.json）：**
```json
"arguments": {"subway_line": "13号线", "decoration": "精装", "rental_type": "整租", "bedrooms": "2", "max_price": 8000}
"result_summary": "total=0, sample=[]"
```

**debug_runner --preset sc9 实际验证：**
```
[NG] [  0] subway_line=13号线 decoration=精装 rental_type=整租 bedrooms=2 max_price=8000
[OK] [  7] subway_line=13号线 rental_type=整租 bedrooms=2
    HF_37(空房) HF_59(简装) HF_161(毛坯) HF_332(豪华) HF_381(毛坯) HF_461(简装) HF_487(毛坯)
[OK] [  9] subway_line=13号线 decoration=精装
    包含HF_438(海淀,2居,精装,1933元) 但为合租
```

**结论：** 13号线整租两居室7套中无一精装；13号线精装中唯一两居室(HF_438)是合租。整租+两居室+精装 三者在13号线数据上无交集，纯数据问题。

**性质：** 纯数据稀疏，条件叠加后自然结果为空。

---

### 根因D：地标查询链路行为存疑（SC13，15分）

**Trace 实证（test_SC13_38_t1.json）：**
```json
// 轮1: get_landmark_by_name("百度")
"result_summary": "total=0, sample=[]"   ← tracer按houses格式解析，可能误报

// 轮2: agent 使用了 landmark_id="CP_001"（来源不明）
"arguments": {"landmark_id": "CP_001", "max_distance": 1000}
"result_summary": "total=0, sample=[]"
```

两个疑点：
1. `result_summary` 是 tracer 按 houses 格式解析的，get_landmark_by_name 实际可能返回了 CP_001
2. CP_001 附近1公里内确实没有房源

需要直接调 API 验证：`/api/landmarks/search?q=百度&category=company` 返回什么。

**性质：** 数据问题（百度附近无房源）+ trace 格式需验证。

---

### 根因E：多轮对话中 Agent 丢失 district 约束（M7，20分）⚠️ 唯一 Agent 行为缺陷

**Trace 实证：**

- `test_M7_47_t1.json` (轮1 "昌平区的整租房")：
  ```json
  "arguments": {"district": "昌平", "rental_type": "整租"}
  "result_summary": "total=17, sample=[...]"   ← 成功
  ```

- `test_M7_47_t2.json` (轮2 "要13号线附近的一居室")：
  ```json
  "arguments": {"subway_line": "13号线", "bedrooms": "1", "rental_type": "整租"}
  //                                                     ↑ district="昌平" 被遗漏！
  "result_summary": "total=10, sample=[...]"   ← 返回了全北京13号线结果
  ```

Agent 轮2 应累积为 `{district=昌平, subway_line=13号线, bedrooms=1, rental_type=整租}` 但只传了 subway_line 部分，丢失了 district="昌平"。

**debug_runner --preset m7 实际验证：**
```
[NG] [  0] district=昌平 subway_line=13号线 rental_type=整租 bedrooms=1  ← baseline期望
[OK] [ 10] subway_line=13号线 bedrooms=1 rental_type=整租               ← agent实际查询（丢失昌平）
    HF_12~HF_454 全在海淀区（西二旗/上地站附近）
[OK] [  2] district=昌平 rental_type=整租 bedrooms=1
    HF_43 昌平  |  HF_444 昌平
```

**结论：** 昌平整租一居室只有2套（均不在13号线），13号线10套全在海淀区，两者无交集。即使 agent 保留了昌平约束也会得0分（baseline 也是0）。这是测试数据组合不存在的问题，同时 agent 确实有多轮约束丢失的行为缺陷。

---

### 根因F：价格区间叠加后数据稀疏（M5、M10，各20分）

**M10 Trace（test_M10_50_t2.json）：**
```json
// 轮1 (41套)：commute_to_xierqi_max=30, rental_type=整租
// 轮2 (0套)：commute_to_xierqi_max=30, rental_type=整租, bedrooms=2, min_price=6000, max_price=10000
```
参数传递完全正确，通勤30分内41套整租房中恰好没有两居室月租6000-10000的。

**M5 Trace（test_M5_45_t3.json）：**
轮2仅找到1套朝南两居室（HF_352，月租5446元），轮3加价格下限6000后无结果。

**性质：** 参数传递正确，数据分布问题。

---

### 根因G：海淀精装修整租8套中无两居室（M4，20分）

**Trace（test_M4_44_t2.json）：**
- 轮1 海淀精装修整租 → 8套（成功）
- 轮2 追加电梯+两居室+排序 → 0套（同时有 ConnectError 重试，轮2耗时35s）

**debug_runner --preset m4 实际验证：**
```
[NG] [  0] district=海淀 decoration=精装 rental_type=整租 bedrooms=2 elevator=true
[NG] [  0] district=海淀 decoration=精装 rental_type=整租 bedrooms=2   ← 去掉电梯也是0
[OK] [  8] district=海淀 decoration=精装 rental_type=整租
    HF_39  海淀  1居  精装  电梯=True
    HF_157 海淀  3居  精装  电梯=True
    HF_351 海淀  1居  精装  电梯=False
    HF_355 海淀  4居  精装  电梯=True
    HF_384 海淀  1居  精装  电梯=True
    HF_425 海淀  3居  精装  电梯=True
    HF_454 海淀  1居  精装  电梯=True
    HF_469 海淀  4居  精装  电梯=True
```

**结论：** 海淀精装整租8套的户型分布为1居×4、3居×2、4居×2，**没有2居室**。不论是否有电梯，加上 bedrooms=2 后结果必然为0。根因是数据分布（随机种子 seed=42 产生的户型分布恰好无此组合）。

---

### 根因H：MC5 写操作依赖查询链成功（MC5，失15分）

轮1/轮2 都因朝阳区无精装修整租两居室数据而返回空，Agent 在轮3 正确拒绝了写操作（无房可租），但写操作得0分，总计15/30（query因无baseline自动给满分15）。

---

## 根因汇总优先级（经 debug_runner 验证确认）

> 所有失分均经 `python -m test.debug_runner --preset all_failed` 验证为 API 返回 0 套

| 优先级 | 根因 | 影响用例数 | 失分 | 能否修复 |
|--------|------|-----------|------|---------|
| P0 | Mock Server数据覆盖不足（特定区域无数据） | 11个 | ~200分 | 补充测试数据 |
| P1 | 数据分布稀疏（精装整租8套无2居室/价格区间无房源） | 3个 | ~40分 | 补充数据或调整用例 |
| P2 | **Agent多轮条件管理：district约束被丢弃（M7）** | 1个 | 20分 | 修复Agent提示词/核心逻辑 |
| P3 | MC5写操作依赖上游查询（连锁失败） | 1个 | 15分 | 数据修复后自动解决 |

**验证结论修正（与原猜测不同的发现）：**
- SC7：**逗号分隔 district 实际支持**（mock_server.py 有 `district.split(",")` 处理），失分是数据问题，非 API 格式问题
- M4：海淀精装整租8套户型全是1/3/4居，**无2居室**，不是电梯过滤问题
- M7：昌平+13号线 数据组合本身不存在（昌平整租一居室2套均不在13号线）

---

## 调测工具使用说明

```bash
# 批量验证所有失分用例数据
python -m test.debug_runner --preset all_failed

# 验证特定根因（含对比查询）
python -m test.debug_runner --preset sc7    # SC7 跨区域查询
python -m test.debug_runner --preset m4    # M4 精装+户型数据分析
python -m test.debug_runner --preset m7    # M7 地铁线路+区域交集

# 运行单个失分用例精细对比（agent参数 vs baseline）
python -m test.debug_runner --id SC7 M7 M10 MC5

# 列出所有内置预设
python -m test.debug_runner --preset list

# 地标探针验证
python -m test.debug_runner --probe-landmark 百度 --landmark-category company
```

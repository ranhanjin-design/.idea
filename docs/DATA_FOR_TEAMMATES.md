# PawPlan HK — 数据说明（给队友）

正式运行只读 **`data/curated/pawplan.db`**（约 2.2 MB）。  
Agent 聊天、地图 Explore、各查询 API 用的都是这一份库。

GitHub：`ranhanjin-design/.idea` · 分支 `dev01`

---

## 1. 目录怎么分

| 路径 | 是什么 | 要不要手改 |
|------|--------|------------|
| `data/raw/` | 从网站抓下来的原文（JSON / HTML / PDF / TXT） | 一般不要改；当存档 |
| `data/staging/` | 清洗、匹配、地理编码中间结果 | 不要当正式库改 |
| `data/curated/pawplan.db` | **正式 SQLite 库** | 改代码/刷脚本更新；别手工乱改 |
| `data/knowledge/` | 策展知识、商场政策、来源清单等 JSON | 有依据可以改，改完写清核实日期 |

流水线概念：

```
网站 / API  →  data/raw/  →  data/staging/  →  data/curated/pawplan.db
                                              ↑
                                    Agent / 地图 / API 只读这里
```

---

## 2. 数据库表（当前体量）

| 表 | 约条数 | 存什么 |
|----|--------|--------|
| `restaurants` | 1003 | 食环署获准带狗食肆（含少数已退出名单） |
| `restaurant_cuisines` | 1009 | 菜系第二源（非正式官方） |
| `parks` | 252 | 康文署宠物公园 / 宠物共享公园 |
| `places` | 674 | 商场、诊所、美容等 |
| `venue_sources` | 1668 | 每条地点的可追溯来源（URL、证据层级、范围） |

### `places` 类型大约

| place_type | 约条数 |
|------------|--------|
| groomer | 292 |
| vet | 190 |
| dental | 98 |
| mall | 83 |
| emergency | 11 |

### `parks` 类型大约

| park_type | 约条数 |
|-----------|--------|
| inclusive_park（宠物共享公园） | 192 |
| pet_garden（宠物公园） | 60 |

### `restaurants`

- `dog_permission=1`：约 994（当前获准，可推荐）
- `dog_permission=0`：约 9（旧牌照保留，不进入推荐）

主要字段：店名中英、地区、地址、牌照号、来源 URL、核实日期；经纬度多为 0（见第 5 节）。

---

## 3. 分别从哪些网站拔出来的

### Tier 1 — 官方（硬事实）

| 网站 | 抓了什么 | 本地 raw 文件 | 入库去哪 |
|------|----------|---------------|----------|
| **食环署 FEHD**  
  列表：`fehd.gov.hk/.../dog_restaurants_list.html`  
  接口：`.../getData.php` | 获准让狗进入的食肆名单（店名、牌照、地区、地址等），约 994 条 | `fehd_dog_restaurants_current.json` 等 | `restaurants` |
| **康文署 LCSD**  
  `lcsd.gov.hk/clpss/.../Facility/Details.do` 等 | 宠物公园 / 共享公园（约 18 区页面 + JSON/PDF） | `lcsd_*.json` / `html` / `pdf` | `parks` |
| **渔护署 AFCD**  
  `pets.gov.hk` 链到的兽医诊所名单 PDF | 诊所名称、电话、地区、地址（自愿列名，非完整名册） | `afcd_vet_clinics.pdf` | 与 `places`(vet) 交叉匹配身份 |

### Tier 2 — 场地自有

| 来源 | 抓/核了什么 | 本地文件 | 用途 |
|------|-------------|----------|------|
| **各商场官网**宠物政策页（如 IFC pet-policy） | 官网明确写出的带宠规则；约 27 条 | `data/knowledge/mall_pet_policies.json` | 推荐商场时优先引用 |
| 诊所/店舖自有网页 | 联系方式、地址 | 写入 `venue_sources` | 证明「怎么联系」，不等于政府认证服务 |

### Tier 3 — 社区 / 互补（补缺口，不能写成官方确认）

| 网站 | 抓了什么 | 本地 raw | 用途 |
|------|----------|----------|------|
| **GoPaw** `gopaw.io/api/venues`（学生项目获授权自取） | 约 2308 条 venue：名称、分类、地址、电话、坐标、网站等 | `gopaw_venues.json` | 商场/诊所/美容补缺；部分菜系匹配 |
| **DogDogHK** `dogdoghk.com/malls/` | 约 46 个商场目录 | `dogdog_malls.json` | 商场补缺 |
| **PetCircle** `petcircle-hk.vercel.app/grooming` | 约 262 家美容相关 | `petcircle_groomers.json` | 美容补缺 |
| **OpenStreetMap** Overpass（香港范围带 `cuisine` 的餐厅/咖啡/快餐） | 约 4404 个元素的菜系标签 | `osm_hk_cuisines.json` | 菜系第二源 only |

证据细则：`docs/evidence_tiers.md`

---

## 4. 字段含义（读库时注意）

每条地点结果里常见：

| 字段概念 | 含义 |
|----------|------|
| `source_name` / `source_url` | **当前对外展示**的来源（可能已升到官网或政府页） |
| `origin_source_name` | 最初从哪个目录拔出来的（如 GoPaw） |
| `evidence_tier` | 1 / 2 / 3 |
| `source_scope` | 这条来源实际证明什么（例如准入 / 联系方式 / 政策页），别超范围解读 |
| `last_verified_at` | 最后核实日期 |

**排序原则：** 匹配到的政府来源 → 场地自有网页 → DogDog / PetCircle / GoPaw 详情。

---

## 5. 地址从哪来？地图怎么钉？

**地址文字**

- 食肆 / 公园：政府名单或官方页地址原文  
- places：第三方目录或官网页地址；能匹配渔护署诊所名单的，身份更可信  

**坐标**

| 类型 | 坐标情况 | 地图表现 |
|------|----------|----------|
| parks | 多数有真实坐标（约 245/252） | 较准 |
| places | 部分有（约 361/674） | 有则用真实坐标 |
| restaurants | 政府名单不带经纬度；库内多为 0 | 用「地区中心点 + 轻微抖动」落 pin，避免全叠一起 |

地图页：`http://127.0.0.1:8000/explore`  
钉点是可视化近似时，**详情以地址文字为准**，不要当成精确 GPS 导航。

---

## 6. 验收相关边界（别踩坑）

1. **食环署没有菜系字段** → 菜系只能靠第二源；无法确认时要说明，并问是否改查该区获准食肆。  
2. **第三方「宠物友善」≠ FEHD 获准带狗。**  
3. **渔护署宠物店牌照 ≠ 美容服务证明**；诊所名单也不等于急诊/24 小时认证。  
4. **Tier 3 不得覆盖 Tier 1/2**，回复里不要写成「官方确认」。  
5. 名单外旧牌照可留在库里（`dog_permission=0`），但**不要当推荐结果吐出去**。

---

## 7. 一般要不要重新爬？

**不用。** 包里 / 仓库里已有 `pawplan.db`，启动即可。

若真要刷新地点来源（政府名单 + 第三方匹配）：

```powershell
python -m pawplan.ingestion.refresh_venue_sources
```

跑完请跑测试：

```powershell
$env:PAWPLAN_FORCE_DEV="1"
python -m unittest discover -s tests -v
```

---

## 8. 一句话

> 官方名单管「准不准」；商场官网管「场地自己怎么说」；GoPaw / DogDog / PetCircle / OSM 只补缺口。  
> 所有对外查询读的是同一个 `data/curated/pawplan.db`。

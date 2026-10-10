# PawPlan HK — 期中验收（COM4101）

依据 **PawPlan HK Project Briefing** 期中核心要求实现。

## 期中范围（支持）

1. **宠物知识问答**：从策展知识库检索并回答；显示来源名称、链接、最后核实日期；依据不足时明确说明，不编造。  
2. **领域过滤**：股票、作业、一般新闻等无关问题拒绝/引导回项目范围，且**不调用**知识或地点工具。  
3. **单一条件地点查询**  
   - 按地区查询宠物公园 / 宠物共享公园（康文署）  
   - 按地区查询食环署获准让狗进入的食肆  
   - 按地区查询**宠物友善商场 / 宠物诊所 / 美容**：商场优先用**各商场官网宠物政策页（Tier 2）**；香港无政府统一商场名单。GoPaw 仅作诊所/美容等互补目录（Tier 3）  
   - **菜系筛选**：用户点名点心/咖啡/菜系时按**菜系第二源**过滤；**菜系第二源 = OSM + GoPaw 目录（学生项目获授权自取）+ 人工核实**；食环署无菜系字段。店名启发式仅作低置信猜测，不能当作已确认菜系。**无法确认则说明，并询问是否改查获准带狗食肆**；不把不匹配结果当推荐  
4. **结果可追溯**：地点结果来自数据库，含名称、地区、来源、核实日期；无结果明确告知。  
5. **工具调用记录**：记录工具名、参数、结果数量；无关问题 `tool_trace` 为空。

## 明确不支持（期中）

- 把菜系标签当作官方确认的推荐  
- 地图、多地点行程、路线优化、实时重规划、用户档案  

获准食肆查询语义 = **该区 FEHD 获准名单**。菜系第二源 = OSM + [GoPaw](https://gopaw.io/)（`/api/venues`，项目获授权自行采集）+ 人工核实；食环署无菜系字段。未匹配店铺不得强行标注。

## 运行方式

```powershell
cd "c:\Users\19716\Desktop\pet_ai_agent\pet_ai_agent(1)\pet_ai_agent\.idea"
python -m pip install -r requirements.txt
python -m pawplan.api.main
```

浏览器：http://127.0.0.1:8000  

可选：`.env` 中配置 `DEEPSEEK_API_KEY` 启用模型 Tool Calls。  
验收/离线测试请设置 `PAWPLAN_FORCE_DEV=1`（不走付费模型）。

### 示例问题

- `带狗散步时，怎样降低中暑风险？`  
- `可以总结一下今天的股票市场吗？`（应过滤、无工具调用）  
- `沙田有没有获准让狗进入的食肆？`  
- `找一家沙田附近的点心店`（无法确认菜系时应询问是否改查获准食肆）  
- `沙田有没有宠物公园？`  
- `湾仔有没有宠物共享公园？`  
- `沙田有没有宠物友善商场？`  
- `湾仔附近的宠物诊所`  

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查、库统计、`capabilities` |
| POST | `/api/chat` | Agent 对话（`reply` / `mode` / `tool_trace`） |
| POST | `/api/knowledge` | 知识检索 |
| POST | `/api/parks` | 公园检索 |
| POST | `/api/places` | 商场 / 诊所 / 美容检索（GoPaw） |
| POST | `/api/search` | 获准食肆检索（地区；可选 `cuisine`） |

## 测试命令

```powershell
# 推荐：离线全量回归（无外网、不调用付费模型）
$env:PAWPLAN_FORCE_DEV="1"
python -m unittest discover -s tests -v

# 快速冒烟（代表性问句 + health）
python scripts\midterm_smoke.py

# 聊天 Markdown 展示契约（表格不得原样显示竖线）
python -m unittest tests.test_chat_markdown -v
```

## 验收标准

| 标准 | 对应测试 |
|------|----------|
| ≥15 条可重复验收问题（知识 / 过滤 / 食肆 / 公园 / 菜系无法确认 / 商场 / 诊所 / 美容 / 无结果） | `tests/test_acceptance_bank.py` |
| 回答不编造；带来源与核实日期 | acceptance + agent midterm |
| 无关问题不产生工具调用 | acceptance + API chat |
| 地点参数符合用户地区条件 | acceptance + API |
| 菜系筛选且不把不匹配结果当推荐 | health `cuisine_filter=true`，`cuisine_recommendation=false`；acceptance 点心店用例 |
| 证据分层：Tier 1 官方 / Tier 2 商场官网 / Tier 3 社区目录 | `docs/evidence_tiers.md` |
| API 端到端（health / knowledge / parks / search / chat） | `tests/test_api_e2e.py` |
| 数据溯源与体量 | `tests/test_data_quality.py` |

**通过条件：** 上述测试全部通过。分层细则见 `docs/evidence_tiers.md`。

## 重建数据（可选）

```powershell
python -m pawplan.ingestion.run_pipeline --skip-fetch
python -m pawplan.ingestion.run_parks_pipeline --skip-fetch
python -m pawplan.ingestion.geocode --centroid-only --target all
```

`--skip-fetch` 在本地文件已存在时跳过食环署 PDF、OSM Overpass 与 GoPaw `/api/venues` 网络请求。单独拉取 GoPaw：

```powershell
python -m pawplan.ingestion.fetch_gopaw
```

原始文件：`data/raw/gopaw_venues.json`。菜系第二源写入 `data/knowledge/cuisine_second_source.json`（含 `source_url` / 置信度 / 核实日期），实体匹配后自动合并分 ≥0.90，0.75–0.90 进入人工核实队列。

### 宠物友善商场（数据源分层）

香港**没有**政府统一商场名单。分层：

| 层级 | 来源 | 规模 | 说明 |
|------|------|------|------|
| Tier 1 | FEHD 获准食肆、LCSD 公园 | 食肆 ~993、公园 ~252 | 硬过滤 |
| Tier 2 | 各商场官网政策页 | 策展 `mall_pet_policies.json`（≥24） | 最可靠；查询优先 |
| Tier 3 | [DogDogHK](https://dogdoghk.com/malls/) / [PetCircle](https://petcircle-hk.vercel.app/grooming) / GoPaw | 商场补缺、美容 ~260、诊所 ~299 | 社区目录；不得覆盖官方 |

```powershell
python -m pawplan.ingestion.load_mall_policies
python -m pawplan.ingestion.fetch_dogdog_malls
python -m pawplan.ingestion.fetch_petcircle_groomers
```

### 宠物美容（更全目录）

GoPaw 仅约 87 间。更全社区源：[PetCircle HK](https://petcircle-hk.vercel.app/grooming)（约 262 间）。渔护署[持牌宠物店 PDF](https://www.pets.gov.hk/tc_chi/animal_business/pet_shop_list.html)是官方名单，但混有售卖/用品店，不能直接当美容目录。查询美容时优先 PetCircle，GoPaw 补缺口。

不删除 `data/raw` 原始文件；测试不访问外网。

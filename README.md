# PawPlan HK — 期中验收（COM4101）

依据 **PawPlan HK Project Briefing** 期中核心要求实现。

## 期中范围（支持）

1. **宠物知识问答**：从策展知识库检索并回答；显示来源名称、链接、最后核实日期；依据不足时明确说明，不编造。  
2. **领域过滤**：股票、作业、一般新闻等无关问题拒绝/引导回项目范围，且**不调用**知识或地点工具。  
3. **单一条件地点查询**  
   - 按地区查询宠物公园 / 宠物共享公园（康文署）  
   - 按地区查询食环署获准让狗进入的食肆  
   - 按地区查询**宠物友善商场 / 宠物诊所 / 美容**：匹配的政府来源优先，其次为场地自有网页，再以第三方详情补缺；医疗、宠物准入和具体服务的证据范围分别说明。  
   - **菜系筛选**：用户点名点心/咖啡/菜系时按**菜系第二源**过滤；**菜系第二源 = OSM + GoPaw 目录（学生项目获授权自取）+ 人工核实**；食环署无菜系字段。店名启发式仅作低置信猜测，不能当作已确认菜系。**无法确认则说明，并询问是否改查获准带狗食肆**；不把不匹配结果当推荐  
4. **结果可追溯**：地点结果来自数据库，含名称、地区、来源、核实日期；无结果明确告知。  
5. **工具调用记录**：记录工具名、参数、结果数量；无关问题 `tool_trace` 为空。

## 明确不支持（期中）

- 把菜系标签当作官方确认的推荐  
- 多地点行程、路线优化、实时重规划、用户档案；地图目前仅支持地点浏览和来源查看。  

获准食肆查询语义 = **该区 FEHD 获准名单**。菜系第二源 = OSM + [GoPaw](https://gopaw.io/)（`/api/venues`，项目获授权自行采集）+ 人工核实；食环署无菜系字段。未匹配店铺不得强行标注。

## 运行方式

```powershell
git clone --branch dev01 --single-branch https://github.com/ranhanjin-design/.idea.git PawPlan_HK
cd PawPlan_HK
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pawplan.api.main
```

聊天：http://127.0.0.1:8000/；地图：http://127.0.0.1:8000/explore 。

项目分支：`ranhanjin-design/.idea` 的 `dev01`。已随代码保存当前公开地点数据库
`data/curated/pawplan.db`，首次启动无需重新爬取。`.env`、虚拟环境、聊天日志、数据库备份及下载网页缓存不上传。

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

本次上传前的离线回归结果：104 项中 102 项通过。原有两项未通过分别是餐厅坐标覆盖率为 0，
以及菜系测试的允许来源尚未包含已有的 GoPaw 记录；本次地点来源相关检查全部通过。

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

### 食肆、医疗、美容及商场的来源

统一采用与场地资料相符的来源：香港政府网页优先，其次为场地自有网页，再以第三方详情页补充。
每条来源记录绑定名称、地区和地址；场地资料改变后，旧的匹配不会自动沿用。
聊天、查询接口、浏览列表和地图详情使用同一套来源资料。

- 食肆：以[食环署可搜索名单](https://www.fehd.gov.hk/tc_chi/licensing/dog_restaurants/dog_restaurants_list.html)的数据按牌照号码匹配，
  来源链接使用网站实际支持的 `districtID` 筛选。食环署把旺角与油尖分开，共 19 个选项，覆盖香港 18 区。
  最新名单未列出的旧牌照保留为 `dog_permission=0`，退出推荐；不以第三方的「宠物友善」标签代替官方准入许可。
- 医疗：以[渔护署兽医诊所名单入口](https://www.pets.gov.hk/tc_chi/animal_health_and_welfare/vet_clinics_list.html)所链接的当前文件，
  按诊所名称、电话、地区及地址交叉匹配。该网页只提供名单下载，没有逐诊所或逐区 HTML 详情；
  因此同时返回官方入口、名单对应页及诊所自有／第三方详情。名单并不完整，未列名不等于不合法。
  官方列名只证明身份和地址，不证明急诊、牙科、24 小时服务或政府认可服务质量。
- 美容：不把渔护署宠物店牌照当作美容服务证明；使用店铺自有网页或 PetCircle／GoPaw 实际发布的详情页。
  PetCircle 使用 `/businesses/grm-...`，不再固定到第一页；完整店名以网页标题核对。
- 商场：保留商场官网明确的宠物政策页，第三方详情补缺；一般场地联系网页不视作宠物准入政策。

更新和核验所有上述地点（政府名单、第三方目录及场地网页）：

```powershell
python -m pawplan.ingestion.refresh_venue_sources
```

完成其他地点导入后，应再运行上述命令。已有完整缓存时可离线应用：
`python -m pawplan.ingestion.refresh_venue_sources --skip-fetch`。
结果与未匹配记录保存在 `data/knowledge/venue_sources.json`，网页缓存保存在
`data/raw/venue_source_pages/`。部分网站可能暂时无法自动读取：可用的目录详情作为补充，
原有已核实政策保留其原核实日期并标明本次读取情况；没有可核实当前来源的旧记录退出推荐。

### 公园来源

公园的 `source_url` 按**公园类别和所属地区**指向康文署官方场地网页：
[狗公园／宠物公园](https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/District.do?ftid=47) 与
[宠物共享公园](https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/District.do?ftid=165)。
抓取流程遍历全部 18 区的两类页面，并核对中英文版本、地区选项及场地对应关系。
`data/raw/lcsd_park_pages.json` 保存核验时间、各区来源和场地资料，原始网页保存在
`data/raw/lcsd_park_pages/`。导入时优先采用这些网页的当前名单、地址、开放时间和设施；
旧 JSON／PDF 中未列于当前网页的记录保留在暂存文件的 `unlisted_records` 中，不进入推荐名单。
网页未列出不等于已确认关闭。重建时保留同一场地已有的坐标。

更新官方网页和资料后导入：

```powershell
python -m pawplan.ingestion.run_parks_pipeline
```

已有完整网页快照时，可用下列命令离线重建。仅重新检索、核验各区网页而不导入数据库：
`python -m pawplan.ingestion.park_sources`。

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

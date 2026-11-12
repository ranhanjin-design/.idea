PawPlan HK — 队友说明（数据 / 怎么跑 / 别踩坑）
================================================
GitHub：https://github.com/ranhanjin-design/.idea  （分支：dev01）
协作者：按 Write 权限协作；改完请 push 到 dev01。

一、怎么跑起来
--------------
1. python -m venv .venv
2. .venv\Scripts\activate
3. pip install -r requirements.txt
4. copy .env.example .env
   - 不填 DEEPSEEK_API_KEY 也可以：本地规则回退问答
   - 离线验收请加：set PAWPLAN_FORCE_DEV=1
5. 启动：
   python -m uvicorn pawplan.api.main:app --host 127.0.0.1 --port 8000 --reload

打开：
  聊天 Agent：http://127.0.0.1:8000/
  地图 Explore：http://127.0.0.1:8000/explore

健康检查：http://127.0.0.1:8000/api/health

注意：压缩包 / 仓库一般不带 .env（避免泄露 Key）。数据库 pawplan.db 已随包提供，
首次启动无需重新爬取。


二、数据在哪（三层）
------------------
data/
  raw/        原始抓取物（政府页、PDF、第三方 JSON/HTML）。只读存档，别手改当正式库。
  staging/    清洗中间产物（规范化 JSON、地理编码缓存、审核队列）。
  curated/    正式库 → pawplan.db（Agent / 地图 / API 都读这个）
  knowledge/  策展知识与来源清单（问答用文档、商场政策、venue_sources.json 等）

正式运行时请只依赖：
  data/curated/pawplan.db   ≈ 2.2 MB


三、数据库里有什么（当前体量）
----------------------------
表名                  大约条数    用途
restaurants           1003        食环署获准带狗食肆（含少数已退出名单 dog_permission=0）
restaurant_cuisines   1009        菜系第二源（非正式官方；OSM / GoPaw / 人工）
parks                  252        康文署宠物公园 + 宠物共享公园
places                 674        商场 / 诊所 / 美容等
venue_sources         1668        每条地点的可追溯来源（URL、tier、scope）

places 细分（约）：
  groomer 292 | vet 190 | dental 98 | mall 83 | emergency 11

parks 细分（约）：
  inclusive_park 192 | pet_garden 60

restaurants：约 994 条 dog_permission=1（当前获准），约 9 条 =0（旧牌照保留但不推荐）


四、数据分别从哪来（证据分层）
------------------------------
Tier 1 官方（硬事实，可硬过滤）
  - 食肆准入：食环署 FEHD 获准让狗进入食肆名单
    raw: data/raw/fehd_dog_restaurants_*.json / html / txt
  - 公园：康文署 LCSD 宠物公园 / 宠物共享公园
    raw: data/raw/lcsd_*.json / html / pdf
  - 诊所身份/地址（有限）：渔护署公开兽医诊所名单（自愿列名、非完整名册）
    raw: data/raw/afcd_vet_clinics.pdf
  - 知识问答政策类：data/knowledge/midterm_docs.json 等

Tier 2 场地自有（条件性规则）
  - 商场宠物政策：商场官网守则页
    knowledge: data/knowledge/mall_pet_policies.json
  - 诊所/美容自有联系页（仅证明联系方式，不等于服务认证）

Tier 3 社区 / 互补（补缺口，不能写成官方确认）
  - GoPaw /api/venues（学生项目获授权自取）→ 商场/诊所/美容/部分菜系匹配
    raw: data/raw/gopaw_venues.json
  - DogDogHK 商场目录补缺
    raw: data/raw/dogdog_malls*
  - PetCircle 美容目录补缺
    raw: data/raw/petcircle_groomers.json
  - OSM cuisine 标签（仅菜系互补）
    raw: data/raw/osm_hk_cuisines.json

细则见：docs/evidence_tiers.md

重要边界（验收会查）：
  - 食环署没有菜系字段 → 不能把菜系当官方推荐
  - 菜系无法确认时：说明并询问是否改查该区获准食肆；不要硬推不匹配店
  - 第三方「宠物友善」≠ FEHD 获准带狗
  - 渔护署宠物店牌照 ≠ 美容服务证明


五、地址从哪来 / 地图怎么钉
--------------------------
地址字段：
  - 食肆 / 公园：政府名单或官方页上的地址原文入库
  - places：第三方目录或官网页上的地址；匹配官方诊所名单后可提升身份可信度

坐标（latitude / longitude）：
  - 公园：多数有坐标（约 245/252）
  - places：部分有坐标（约 361/674）
  - 食肆：政府名单本身不带经纬度；当前库中 restaurants 坐标基本为 0
    → 地图展示时会用「地区中心点 + 轻微抖动」落点，避免全部叠在一起
    → 这是可视化近似，不是精确门店 GPS；详情仍以地址文字为准

地图页：/explore
  - 筛地区 / 类型 / 关键词
  - 点 pin 看名称、地址、来源、核实日期


六、代码结构（你大概会改哪里）
------------------------------
pawplan/
  api/main.py           FastAPI 入口、路由
  agent/                对话 Agent、工具调用、领域过滤
  tools/                knowledge / parks / places / search / explore
  ingestion/            抓取与入库脚本（刷新来源等）
  db/                   SQLite 访问

前端页面（根目录）：
  main_page.html        Agent 聊天
  explore.html          地图浏览

测试：
  tests/                验收题库、API e2e、数据质量
  建议：set PAWPLAN_FORCE_DEV=1
        python -m unittest discover -s tests -v


七、可选：刷新地点来源（一般不用）
----------------------------------
已有 pawplan.db 时不必重跑。若要更新政府名单 / 第三方目录匹配：

  python -m pawplan.ingestion.refresh_venue_sources

跑完请确认 tests 仍通过，再 commit。


八、给队友的协作约定
--------------------
请改：
  - 功能代码、测试、文档、知识策展 JSON（有依据时）

请不要随手改 / 不要提交：
  - .env（密钥）
  - .venv / __pycache__ / logs
  - 临时探针脚本（_probe_*, _pc* 等）— 已清理，勿再塞回仓库
  - 把 Tier 3 结果改写成「官方确认」措辞

提交前自测：
  1) /api/health 能通
  2) 聊天问一句地区食肆 / 公园
  3) /explore 地图能出点
  4) 有空跑 unittest


九、一句话记住
--------------
官方名单管「准不准」；官网管「场地自己怎么说」；GoPaw/DogDog/PetCircle 只补缺口。
Agent 和地图读的是同一个 data/curated/pawplan.db。

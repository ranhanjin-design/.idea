# PawPlan HK — 期中验收（COM4101）

依据 **PawPlan HK Project Briefing** 期中核心要求实现。

## 期中范围（支持）

1. **宠物知识问答**：从策展知识库检索并回答；显示来源名称、链接、最后核实日期；依据不足时明确说明，不编造。  
2. **领域过滤**：股票、作业、一般新闻等无关问题拒绝/引导回项目范围，且**不调用**知识或地点工具。  
3. **单一条件地点查询**  
   - 按地区查询宠物公园 / 宠物共享公园（康文署）  
   - 按地区查询食环署获准让狗进入的食肆  
   - **菜系筛选**：用户点名点心/咖啡/菜系时按店名与策展标签过滤；食环署名单无官方菜系字段，**无法确认则说明，并询问是否改查获准带狗食肆**；不把不匹配结果当推荐  
4. **结果可追溯**：地点结果来自数据库，含名称、地区、来源、核实日期；无结果明确告知。  
5. **工具调用记录**：记录工具名、参数、结果数量；无关问题 `tool_trace` 为空。

## 明确不支持（期中）

- 把菜系标签当作官方确认的推荐  
- 地图、多地点行程、路线优化、实时重规划、用户档案  

获准食肆查询语义 = **该区 FEHD 获准名单**。菜系筛选用店名/策展标签，**不是**食环署官方菜系字段。

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

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查、库统计、`capabilities` |
| POST | `/api/chat` | Agent 对话（`reply` / `mode` / `tool_trace`） |
| POST | `/api/knowledge` | 知识检索 |
| POST | `/api/parks` | 公园检索 |
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
| ≥15 条可重复验收问题（知识 / 过滤 / 食肆 / 公园 / 无结果） | `tests/test_acceptance_bank.py` |
| 回答不编造；带来源与核实日期 | acceptance + agent midterm |
| 无关问题不产生工具调用 | acceptance + API chat |
| 地点参数符合用户地区条件 | acceptance + API |
| 菜系筛选且不把不匹配结果当推荐 | health `cuisine_filter=true`，`cuisine_recommendation=false`；acceptance 点心店用例 |
| API 端到端（health / knowledge / parks / search / chat） | `tests/test_api_e2e.py` |
| 数据溯源与体量 | `tests/test_data_quality.py` |

**通过条件：** 上述测试全部通过。

## 重建数据（可选）

```powershell
python -m pawplan.ingestion.run_pipeline --skip-fetch
python -m pawplan.ingestion.run_parks_pipeline --skip-fetch
python -m pawplan.ingestion.geocode --centroid-only --target all
```

不删除 `data/raw` 原始文件；测试不访问外网。

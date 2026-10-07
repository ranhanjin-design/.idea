# PawPlan HK — 期中前半（COM4101）

依据 **PawPlan HK Project Briefing**：期中目标是「先回答问题，再推荐地点」。  
**当前实现聚焦期中前半：**

1. 带来源的宠物知识问答  
2. 识别并过滤无关问题  
3. （附带）保留单一条件获准食肆查询，作为后续「地点推荐」基础  

多地点行程、地图、时间线 **不在** 本期范围。

## 快速开始

```powershell
cd "c:\Users\19716\Desktop\pet_ai_agent\pet_ai_agent(1)\pet_ai_agent\.idea"
python -m pip install -r requirements.txt
python -m pawplan.api.main
```

浏览器打开：**http://127.0.0.1:8000**

### 示例问题（期中前半）

- `带狗散步时，怎样降低中暑风险？`
- `我可以带狗进入公众泳滩吗？`
- `进入获准食肆后需要遵守哪些规则？`
- `可以总结一下今天的股票市场吗？`（应被领域过滤）

### 地点查询

- `沙田有没有宠物公园？`
- `湾仔有没有宠物共享公园？`
- `沙田有没有宠物友好咖啡馆？`

可选：配置 `.env` 中的 `DEEPSEEK_API_KEY` 启用完整 Tool Calls；否则走本地规则模式。

## 工具

| 工具 | 用途 |
|------|------|
| `search_knowledge` | 检索策展文档并返回来源 |
| `search_parks` | 查询康文署宠物公园 / 宠物共享公园 |
| `search_restaurants` | 查询食环署获准食肆 |

重建地点库：

```powershell
# 食肆
python -m pawplan.ingestion.run_pipeline --skip-fetch
# 公园（宠物公园 JSON + 共享公园 PDF）
python -m pawplan.ingestion.run_parks_pipeline --skip-fetch
# 地理编码（推荐：先快填地区中心点；再用 Nominatim 尝试提升精度）
python -m pawplan.ingestion.geocode --centroid-only --target all
python -m pawplan.ingestion.geocode --clear-negative-cache --target all --limit 50
python -m pawplan.ingestion.geocode --report-only
```

## 数据组（Briefing 期中前）

| 项 | 状态 |
|----|------|
| 资料来源审查与采集 | ✅ FEHD 食肆 + LCSD 宠物公园/共享公园 + 知识文档 |
| 数据结构与来源字段 | ✅ `source_url`、`last_verified_at`、菜系置信度等 |
| 地理编码与标准化 | ✅ 地区名标准化；宠物公园用官方坐标；其余先 Nominatim，失败则用**地区中心点回退**（`--centroid-only` 可快速全量补齐） |
| 供智能体使用的搜索 API | ✅ `/api/search`、`/api/parks`、`/api/knowledge` + 三个 tool |
| 数据质量测试 | ✅ `tests/test_data_quality.py`（体量、溯源、唯一性、地区、坐标 bbox/覆盖率） |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 + 库统计 + 地理编码覆盖率 |
| POST | `/api/chat` | Agent 对话 |
| POST | `/api/knowledge` | 直接知识检索 |
| POST | `/api/parks` | 直接公园检索 |
| POST | `/api/search` | 直接餐厅检索 |

## 测试

```powershell
python -m unittest tests.test_agent_midterm tests.test_data_quality -v
```

## 与 Briefing 的对应

| Briefing 期中项 | 本期 |
|-----------------|------|
| 带资料来源的宠物知识问答 | ✅ |
| 识别并过滤无关问题 | ✅ |
| 基础工具调用：知识检索 | ✅ |
| 清洗后的食肆库 + 公园库 / 地点推荐 | ✅ 食肆 + 宠物公园/共享公园（单一条件） |
| 行程 / 地图 | ❌ 期末阶段 |

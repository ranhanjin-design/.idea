# Pet Health & Memory（期中后 Module 2 / 基础 Module 3）

## 可行性结论（对照 GitHub + briefing）

**可行，且应嵌进现有 FastAPI + SQLite，不要另起 React/Next 全家桶。**

| GitHub 参考 | 可借鉴 | 不直接搬 |
|-------------|--------|----------|
| [AnoukSmet/Dog-Health-Tracker](https://github.com/AnoukSmet/Dog-Health-Tracker) | 档案 + 每日 weight/food/activity log 模型 | Mongo 栈 |
| [umair-iqbal-61/Pawpal](https://github.com/umair-iqbal-61/Pawpal) | 体重折线 + Agent 读历史 | Supabase 整站重写 |
| [sychcc/PetHealth-2026](https://github.com/sychcc/PetHealth-2026) | Chart.js 体重趋势 | Next.js 大迁移 |
| [WuSuBuDuoMing/pawguard](https://github.com/WuSuBuDuoMing/pawguard) | 成长日记 / 记忆库信息架构 | 微信小程序 |

Briefing 要求：Dashboard + 时间序列记录 + Agent 可查档案；多模态只做「观察 + 追问 + 不确诊」。

本实现：同库新表 `pets` / `pet_daily_records` / `pet_memories`，页面 `/health-dashboard`，CDN Chart.js。

## 打开

http://127.0.0.1:8000/health-dashboard

## API

- `GET /api/pets`
- `GET /api/pets/{id}/dashboard`
- `POST /api/pets` / `POST /api/pets/records` / `POST /api/pets/memories`
- `POST /api/pets/observe`（multipart：pet_id, question, image）

示例档案：Buddy（Golden Retriever）+ 5 周体重演示数据。

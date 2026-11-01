PawPlan HK — 队友快速启动

1) 安装依赖
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt

2) 配置（可选联网 DeepSeek）
   copy .env.example .env
   # 编辑 .env 填入 DEEPSEEK_API_KEY；不填也能用本地规则回退问答

3) 启动
   python -m uvicorn pawplan.api.main:app --host 127.0.0.1 --port 8000 --reload

4) 打开
   聊天: http://127.0.0.1:8000/
   地图: http://127.0.0.1:8000/explore

说明:
- 已包含 data/curated/pawplan.db，一般无需重新爬取
- 未包含 .env（避免泄露 API Key）
- GitHub: https://github.com/ranhanjin-design/.idea/tree/dev01 （dev01 分支）
- 最新地点来源已按政府网页、场地官网、第三方详情的顺序核对。

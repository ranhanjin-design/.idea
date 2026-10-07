import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pawplan.agent.loop import run_agent
from pawplan.database.db import db_stats, init_database
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_restaurants import search_restaurants

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    yield


app = FastAPI(title="PawPlan HK API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    mode: str
    tool_trace: list


class SearchRequest(BaseModel):
    district: str
    cuisine: str | None = None
    limit: int = Field(default=5, ge=1, le=5)


class KnowledgeRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=3, ge=1, le=5)


class ParkSearchRequest(BaseModel):
    district: str
    park_type: str | None = None
    require_dog_latrine: bool = False
    limit: int = Field(default=5, ge=1, le=5)


@app.get("/api/health")
def health():
    stats = db_stats()
    geo = None
    try:
        from pawplan.ingestion.geocode import coverage_report

        geo = coverage_report()
    except Exception:
        geo = None
    return {
        "status": "ok",
        "scope": "midterm-half: knowledge Q&A + domain filter + place search",
        "deepseek_configured": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "database": stats,
        "geocode": geo,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    result = run_agent(body.message.strip())
    return ChatResponse(
        reply=result["reply"],
        mode=result["mode"],
        tool_trace=result.get("tool_trace") or [],
    )


@app.post("/api/knowledge")
def knowledge(body: KnowledgeRequest):
    return search_knowledge(body.query, body.limit)


@app.post("/api/parks")
def parks(body: ParkSearchRequest):
    return search_parks(
        body.district,
        body.park_type,
        body.require_dog_latrine,
        body.limit,
    )


@app.post("/api/search")
def search(body: SearchRequest):
    return search_restaurants(body.district, body.cuisine, body.limit)


@app.get("/")
def index():
    return FileResponse(ROOT / "main_page.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pawplan.api.main:app", host="127.0.0.1", port=8000, reload=True)

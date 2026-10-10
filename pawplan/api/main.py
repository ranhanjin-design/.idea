import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field

from pawplan.agent.loop import run_agent
from pawplan.database.db import db_stats, init_database
from pawplan.tools.explore import explore_browse, explore_catalog, explore_map_points
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_places import search_places
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

_static_dir = ROOT / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list)


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


class PlaceSearchRequest(BaseModel):
    district: str
    place_type: str | None = None
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
        "scope": (
            "midterm: knowledge Q&A + domain filter + "
            "place search (parks / FEHD dog-permitted / GoPaw malls·vets·groomers) + "
            "optional cuisine filter. Unconfirmed cuisine is not recommended; "
            "the agent asks whether to search dog-permitted restaurants instead."
        ),
        "deepseek_configured": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "database": stats,
        "geocode": geo,
        "capabilities": {
            "knowledge_qa": True,
            "domain_filter": True,
            "park_search": True,
            "restaurant_permission_search": True,
            "mall_vet_groomer_search": True,
            "cuisine_filter": True,
            "cuisine_recommendation": False,
        },
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    history = [{"role": item.role, "content": item.content} for item in body.history]
    result = run_agent(body.message.strip(), history=history)
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


@app.post("/api/places")
def places(body: PlaceSearchRequest):
    return search_places(body.district, body.place_type, body.limit)


@app.post("/api/search")
def search(body: SearchRequest):
    return search_restaurants(body.district, body.limit, cuisine=body.cuisine)


@app.get("/api/explore/catalog")
def api_explore_catalog():
    return explore_catalog()


@app.get("/api/explore/browse")
def api_explore_browse(
    category: str,
    district: str | None = None,
    limit: int = 24,
    offset: int = 0,
):
    return explore_browse(category, district=district, limit=limit, offset=offset)


@app.get("/api/explore/map")
def api_explore_map(
    category: str = "all",
    district: str | None = None,
    limit: int = 400,
    q: str | None = None,
):
    return explore_map_points(category, district=district, limit=limit, q=q)


@app.get("/")
def index():
    return FileResponse(
        ROOT / "main_page.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/explore")
def explore_page():
    return FileResponse(
        ROOT / "explore.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pawplan.api.main:app", host="127.0.0.1", port=8000, reload=True)

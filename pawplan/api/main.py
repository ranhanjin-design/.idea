import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Any, Literal

from pydantic import BaseModel, Field

from pawplan.agent.loop import run_agent
from pawplan.database.db import db_stats, init_database
from pawplan.database import pet_health as pet_health_db
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
            "pet_health_dashboard": True,
            "pet_memory_library": True,
            "pet_health_observe_basic": True,
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


@app.get("/health-dashboard")
def health_dashboard_page():
    return FileResponse(
        ROOT / "health.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


# ---- Pet health profile / memory library (after-midterm Module 2 + basic 3) ----


class PetUpsertRequest(BaseModel):
    pet_id: str | None = None
    name: str = Field(..., min_length=1, max_length=80)
    species: str = "dog"
    breed: str | None = None
    sex: str | None = None
    birth_date: str | None = None
    age_years: float | None = None
    neutered: bool = False
    avatar_url: str | None = None
    notes: str | None = None
    is_example: bool = False


class DailyRecordRequest(BaseModel):
    pet_id: str
    record_date: str | None = None
    weight_kg: float | None = None
    food_g: float | None = None
    food_note: str | None = None
    exercise_min: float | None = None
    exercise_note: str | None = None
    notes: str | None = None


class MemoryRequest(BaseModel):
    pet_id: str
    memory_type: str = "note"
    title: str | None = None
    body: str | None = None
    image_path: str | None = None
    event_date: str | None = None
    tags: list[str] | str | None = None


class ObserveRequest(BaseModel):
    pet_id: str
    question: str = Field(..., min_length=1, max_length=2000)
    image_path: str | None = None


@app.get("/api/pets")
def api_list_pets():
    return {"pets": pet_health_db.list_pets()}


@app.get("/api/pets/{pet_id}/dashboard")
def api_pet_dashboard(pet_id: str):
    try:
        return pet_health_db.dashboard_for_pet(pet_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/pets")
def api_upsert_pet(body: PetUpsertRequest):
    return pet_health_db.upsert_pet(body.model_dump())


@app.post("/api/pets/records")
def api_upsert_record(body: DailyRecordRequest):
    try:
        return pet_health_db.upsert_daily_record(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/pets/{pet_id}/memories")
def api_list_memories(pet_id: str, limit: int = 50):
    return {"memories": pet_health_db.list_memories(pet_id, limit=limit)}


@app.post("/api/pets/memories")
def api_add_memory(body: MemoryRequest):
    try:
        return pet_health_db.add_memory(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/pets/observe")
async def api_observe(
    pet_id: str = Form(...),
    question: str = Form(...),
    image: UploadFile | None = File(None),
):
    image_path = None
    if image is not None and image.filename:
        data = await image.read()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="image too large (max 8MB)")
        image_path = pet_health_db.save_upload(image.filename, data)
    try:
        return pet_health_db.observe_health(pet_id, question, image_path=image_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/pets/observe/json")
def api_observe_json(body: ObserveRequest):
    try:
        return pet_health_db.observe_health(
            body.pet_id, body.question, image_path=body.image_path
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/pets/uploads/{filename}")
def api_pet_upload(filename: str):
    safe = Path(filename).name
    path = pet_health_db.UPLOAD_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn # Listen from HTTP requests, and handle them to FastAPI.

    uvicorn.run("pawplan.api.main:app", host="127.0.0.1", port=8000, reload=True)

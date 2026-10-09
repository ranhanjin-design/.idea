from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from xiaoshitou.engine import answer
from xiaoshitou.store import add_memory, list_memories, load_profile, save_profile

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Xiaoshitou", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field(default="her", description="her=扮演她 | coach=哄她教练")


class MemoryIn(BaseModel):
    key: str
    value: str
    verified: bool = True


@app.get("/")
def index():
    return FileResponse(ROOT / "web.html")


@app.get("/api/profile")
def profile():
    return load_profile()


@app.post("/api/profile")
def update_profile(body: dict):
    save_profile(body)
    return {"ok": True}


@app.get("/api/memories")
def memories():
    return {"memories": list_memories()}


@app.post("/api/memories")
def create_memory(body: MemoryIn):
    add_memory(
        body.key,
        body.value,
        source="manual",
        confidence=1.0,
        verified=body.verified,
    )
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatIn):
    return answer(body.message.strip(), mode=body.mode)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("xiaoshitou.api:app", host="127.0.0.1", port=8001, reload=True)

"""TravelSphere API entry point: ``uvicorn app.main:app --reload``."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Read backend/.env (API keys, DATABASE_URL) before modules that read the environment are imported.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .api import router  # noqa: E402
from .database import SessionLocal, init_db  # noqa: E402
from .discover import load_saved  # noqa: E402


_tables_ready = False


def prepare() -> None:
    """Create tables once per process, then pick up city guides built elsewhere."""
    global _tables_ready
    if not _tables_ready:
        init_db()
        _tables_ready = True
    with SessionLocal() as db:
        load_saved(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    prepare()
    yield


app = FastAPI(
    title="TravelSphere API",
    description="AI sightseeing daily itinerary planner & map optimizer",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serverless runtimes may skip lifespan events, so prepare on each API request as well.
@app.middleware("http")
async def prepare_database(request: Request, call_next):
    if request.url.path.startswith("/api"):
        await run_in_threadpool(prepare)
    return await call_next(request)


app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}

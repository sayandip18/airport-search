from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.api.fetch_airports import router as airports_router
from app.api.ingest import router as ingest_router
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(ingest_router)
app.include_router(airports_router, prefix="/api/airports", tags=["airports"])


@app.get("/")
def root():
    return {"message": "Hello from FastAPI"}

from fastapi import FastAPI

from app.api.ingest import router as ingest_router

app = FastAPI()

app.include_router(ingest_router)


@app.get("/")
def root():
    return {"message": "Hello from FastAPI"}

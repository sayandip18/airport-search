import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingest import EnrichmentResponse
from app.services.airport import save_airports
from app.services.ingest import analyze_csv, enrich_airports

router = APIRouter()


@router.post("/ingest", response_model=EnrichmentResponse, status_code=200)
async def ingest_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> EnrichmentResponse:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {exc}") from exc

    analysis = analyze_csv(df)
    airports = analysis["airports"]
    airports_by_iata = {a["iata_code"]: a for a in airports}

    enriched = await enrich_airports(airports)
    saved = await save_airports(enriched, airports_by_iata, db)

    stats = {k: v for k, v in analysis.items() if k != "airports"}
    return EnrichmentResponse(enriched_count=saved, stats=stats)

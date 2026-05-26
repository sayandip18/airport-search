import io
import json

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas.ingest import EnrichmentResponse
from app.services.ingest import analyze_csv, enrich_airports

router = APIRouter()


@router.post("/ingest", response_model=EnrichmentResponse, status_code=200)
async def ingest_csv(file: UploadFile) -> EnrichmentResponse:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {exc}") from exc

    analysis = analyze_csv(df)
    enriched = await enrich_airports(analysis["airports"])

    print(json.dumps(enriched, indent=2, ensure_ascii=False))

    stats = {k: v for k, v in analysis.items() if k != "airports"}
    return EnrichmentResponse(enriched_count=len(enriched), stats=stats)

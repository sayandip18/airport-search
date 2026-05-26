import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ingest import IngestResult
from app.schemas.ingest import IngestResultRead
from app.services.ingest import analyze_csv, run_llm

router = APIRouter()


@router.post("/ingest", response_model=IngestResultRead, status_code=201)
async def ingest_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> IngestResult:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {exc}") from exc

    analysis = analyze_csv(df)
    llm_response = await run_llm(analysis)

    record = IngestResult(filename=file.filename, llm_response=llm_response)
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record

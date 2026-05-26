import uuid
from datetime import datetime

from pydantic import BaseModel


class IngestResultRead(BaseModel):
    id: uuid.UUID
    filename: str
    llm_response: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnrichmentResponse(BaseModel):
    enriched_count: int
    stats: dict

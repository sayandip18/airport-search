from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.airport import Airport
from app.schemas.airport import AirportRead
from app.services.airport import search_airports

router = APIRouter()


@router.get("/search", response_model=list[AirportRead])
async def search_airports_endpoint(
    q: str = Query(
        ...,
        min_length=1,
        description=(
            "Free-text search: IATA/ICAO code, airport name, city, "
            "municipality, metro area, region, or country. "
            "Non-Latin scripts are transliterated to ASCII automatically."
        ),
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return (1–50, default 10).",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[Airport]:
    """Search airports.

    Examples
    --------
    * ``GET /api/airports/search?q=London``        — city / name substring
    * ``GET /api/airports/search?q=LON``           — metro / IATA code
    * ``GET /api/airports/search?q=Londn``         — typo-tolerant
    * ``GET /api/airports/search?q=東京``           — non-Latin (transliterated)
    * ``GET /api/airports/search?q=São+Paulo``     — accented text
    * ``GET /api/airports/search?q=London&limit=5``— custom result count
    """
    return await search_airports(q, limit, db)

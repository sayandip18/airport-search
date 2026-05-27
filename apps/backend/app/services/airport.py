import pycountry
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.models.airport import Airport


def _country_name(code: str) -> str | None:
    country = pycountry.countries.get(alpha_2=code)
    return getattr(country, "name", None)


def _region_name(code: str) -> str | None:
    subdivision = pycountry.subdivisions.get(code=code)
    return getattr(subdivision, "name", None)


async def save_airports(
    enriched: list[dict],
    airports_by_iata: dict[str, dict],
    db: AsyncSession,
) -> int:
    records = []
    for entry in enriched:
        iata = entry["iata_code"]
        source = airports_by_iata.get(iata, {})
        country_code = source.get("iso_country", "")
        region_code = source.get("iso_region", "")

        metro_city = entry.get("metro_city") or {}
        metro_code_field = entry.get("metro_code") or {}

        records.append(Airport(
            name=source.get("name", ""),
            icao_code=source.get("icao_code") or None,
            iata_code=iata,
            municipality_name=source.get("municipality") or None,
            municipality_aliases=entry.get("municipality_aliases", []),
            metro_name=metro_city.get("value"),
            metro_code=metro_code_field.get("value"),
            metro_aliases=entry.get("city_aliases", []),
            country_name=_country_name(country_code),
            country_code=country_code,
            country_alias=entry.get("country_aliases", []),
            region_name=_region_name(region_code),
            region_code=region_code,
            region_alias=entry.get("region_aliases", []),
            rank=source.get("passenger_volume_rank", 5),
        ))

    db.add_all(records)
    await db.commit()
    return len(records)


# Expression that matches the airports_trigram_gin index definition so the
# planner can use it for both ILIKE and word_similarity queries.
_TRIGRAM_CONCAT = """
    immutable_unaccent(
        COALESCE(name, '')              || ' ' ||
        COALESCE(municipality_name, '') || ' ' ||
        COALESCE(metro_name, '')        || ' ' ||
        COALESCE(country_name, '')      || ' ' ||
        COALESCE(iata_code, '')         || ' ' ||
        COALESCE(icao_code, '')
    )
"""


async def search_airports(
    query: str,
    limit: int,
    db: AsyncSession,
) -> list[Airport]:
    """Search airports by any text (name, IATA/ICAO code, city, country).

    Non-Latin scripts (e.g. 東京) are transliterated to ASCII with unidecode
    before querying.  Note: unidecode uses Mandarin pinyin for CJK characters
    ("Dong Jing" for 東京), so Japanese-script queries may not match if the DB
    stores only the romanised name "Tokyo".

    Strategy — trigram only (uses airports_trigram_gin GIN index):
      1. ILIKE '%q%'            — exact substring (LON, London, São Paulo …)
      2. word_similarity(q, …)  — typo-tolerant (Londn → London)
    Results are sorted by passenger_volume_rank DESC (higher rank = busier).
    """
    # Transliterate non-ASCII, strip whitespace, lowercase for case-insensitive
    # matching that mirrors the immutable_unaccent() index expression.
    normalized = unidecode(query).strip().lower()

    if not normalized:
        return []

    stmt = (
        select(Airport)
        .where(
            text(
                f"{_TRIGRAM_CONCAT} ILIKE '%' || :q || '%'"
                f" OR word_similarity(:q, {_TRIGRAM_CONCAT}) > 0.4"
            ).bindparams(q=normalized)
        )
        .order_by(Airport.rank.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())

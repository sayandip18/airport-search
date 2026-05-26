import pycountry
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.airport import Airport


def _country_name(code: str) -> str | None:
    country = pycountry.countries.get(alpha_2=code)
    return country.name if country else None


def _region_name(code: str) -> str | None:
    subdivision = pycountry.subdivisions.get(code=code)
    return subdivision.name if subdivision else None


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

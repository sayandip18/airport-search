import uuid
from typing import Any

from pydantic import BaseModel


class AirportRead(BaseModel):
    id: uuid.UUID
    name: str
    icao_code: str | None
    iata_code: str

    municipality_name: str | None
    municipality_aliases: list[Any]

    metro_name: str | None
    metro_code: str | None
    metro_aliases: list[Any]

    country_name: str | None
    country_code: str
    country_alias: list[Any]

    region_name: str | None
    region_code: str
    region_alias: list[Any]

    model_config = {"from_attributes": True}

import uuid
from typing import Any

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Airport(Base):
    __tablename__ = "airports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    icao_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    iata_code: Mapped[str] = mapped_column(String(3), unique=True, index=True)

    municipality_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipality_aliases: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    metro_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metro_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    metro_aliases: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    country_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    country_alias: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    region_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_code: Mapped[str] = mapped_column(String(10))
    region_alias: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    rank: Mapped[int] = mapped_column(Integer)

    aliases_text: Mapped[str | None] = mapped_column(Text, nullable=True, index=False)

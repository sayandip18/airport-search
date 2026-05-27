import uuid
from typing import Any

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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

    # Maintained automatically by airports_search_vector_trigger (defined in
    # migrations/001_add_search_indexes.sql, extended in 002_add_aliases_text.sql).
    # Never write to either column directly — the trigger rebuilds both on every
    # INSERT/UPDATE.
    # GIN indexes: airports_search_vector_gin, airports_aliases_trigram_gin.
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, nullable=True, index=False)

    # Plain-text concatenation of every alias name across all four JSONB alias
    # arrays.  Used for trigram (pg_trgm) search so aliases participate in the
    # same typo-tolerant / substring matching as the scalar name columns.
    # GIN trigram index: airports_aliases_trigram_gin (migration 002).
    aliases_text: Mapped[str | None] = mapped_column(Text, nullable=True, index=False)

import re

import pycountry
from pykakasi import kakasi
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.models.airport import Airport

# ---------------------------------------------------------------------------
# Transliteration helpers
# ---------------------------------------------------------------------------

# Unicode ranges for CJK Unified Ideographs (kanji / hanzi shared block)
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")

# Unicode ranges exclusively used by Japanese (hiragana + katakana).
# Presence of either is a 100 % reliable signal that the input is Japanese.
_KANA_RE = re.compile(r"[぀-ゟ゠-ヿ]")

# Lazy-initialised kakasi instance.  The kakasi() constructor loads dictionary
# data and takes ~100 ms; initialising it at import time would slow every cold
# start even when no Japanese query is ever made.
_kks: kakasi | None = None


def _get_kks() -> kakasi:
    global _kks
    if _kks is None:
        _kks = kakasi()
    return _kks


def _romanise_ja(text: str) -> str:
    """Convert Japanese text (kanji + kana, or mixed) to Hepburn romaji.

    pykakasi passes through Latin characters unchanged, so mixed input like
    "Tokyo 東京" is handled correctly.
    """
    return " ".join(
        item["hepburn"] for item in _get_kks().convert(text) if item["hepburn"]
    )


def _to_ascii(query: str) -> str:
    """Transliterate a free-text search query to ASCII for trigram matching.

    Decision tree
    -------------
    1. Contains kana (hiragana U+3040–309F / katakana U+30A0–30FF)
       OR any CJK Unified Ideograph (kanji / hanzi)
       → pykakasi (Hepburn romaji)

       Why pykakasi for all CJK and not a langdetect branch?
       langdetect is unreliable on strings shorter than ~20 characters —
       empirically, 2-char airport city kanji (東京, 大阪, 成田, 羽田, 関西)
       are all mis-detected as Korean or Traditional Chinese.  pykakasi, by
       contrast, produces exact or near-exact romaji for every major Japanese
       airport city (toukyou, oosaka, narita, haneda, kansai) and acceptable
       on-yomi readings for Chinese characters (shanhai ≈ shanghai).

    2. Pure Latin / other scripts (Arabic, Cyrillic, accented Latin, …)
       → unidecode  (strips accents, converts to nearest ASCII)
         e.g. São Paulo → "Sao Paulo", Москва → "Moskva"
    """
    if _KANA_RE.search(query) or _CJK_RE.search(query):
        return _romanise_ja(query)

    return unidecode(query)


# ---------------------------------------------------------------------------
# SQL fragments — must match the corresponding index expressions exactly so
# the query planner can use the GIN indexes without a full scan.
#
#   airports_trigram_gin       → _TRIGRAM_CONCAT  (migration 001)
#   airports_aliases_trigram_gin → _ALIASES_EXPR  (migration 002)
# ---------------------------------------------------------------------------

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

_ALIASES_EXPR = "immutable_unaccent(COALESCE(aliases_text, ''))"


# ---------------------------------------------------------------------------
# Ingest helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_airports(
    query: str,
    limit: int,
    db: AsyncSession,
) -> list[Airport]:
    """Search airports by any text (name, IATA/ICAO code, city, country, alias).

    Transliteration
    ---------------
    Non-Latin input is converted to ASCII before querying:
      - Japanese kana          → pykakasi Hepburn romaji
      - CJK (kanji / hanzi)    → langdetect to branch Japanese/other;
                                  pykakasi for Japanese, unidecode otherwise
      - All other scripts      → unidecode (accents stripped, Cyrillic/Arabic
                                  converted to nearest Latin equivalent)

    Search strategy — trigram only, two index scans OR-ed:
    -------------------------------------------------------
    1. Scalar fields (airports_trigram_gin index, migration 001):
         ILIKE '%q%'                 — exact substring  (LON, London, São Paulo)
         word_similarity(q, …) > 0.4 — typo-tolerant    (Londn → London)

    2. Alias names (airports_aliases_trigram_gin index, migration 002):
         Same two conditions against aliases_text, so aliases like
         "Heathrow", "Narita", "Nihon" participate in both substring
         and typo-tolerant matching.

    Results are sorted by passenger_volume_rank DESC (higher = busier airport).
    """
    normalized = _to_ascii(query).strip().lower()

    if not normalized:
        return []

    stmt = (
        select(Airport)
        .where(
            text(
                f"({_TRIGRAM_CONCAT} ILIKE '%' || :q || '%'"
                f" OR word_similarity(:q, {_TRIGRAM_CONCAT}) > 0.4"
                f" OR {_ALIASES_EXPR} ILIKE '%' || :q || '%'"
                f" OR word_similarity(:q, {_ALIASES_EXPR}) > 0.4)"
            ).bindparams(q=normalized)
        )
        .order_by(Airport.rank.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())

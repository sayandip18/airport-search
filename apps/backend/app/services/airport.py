import re

import pycountry
from indic_transliteration import sanscript
from indic_transliteration.detect import detect as _detect_indic_script
from pykakasi import kakasi
from pypinyin import lazy_pinyin
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

# Indic scripts: Devanagari through Malayalam (covers Hindi, Bengali, Tamil,
# Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Oriya).
_INDIC_RE = re.compile(r"[ऀ-ൿ]")

# Lazy-initialised kakasi instance.  The kakasi() constructor loads dictionary
# data and takes ~100 ms; initialising it at import time would slow every cold
# start even when no Japanese query is ever made.
_kks: kakasi | None = None

# Mapping from indic_transliteration.detect() output → sanscript scheme constant.
# detect() returns lowercase names (e.g. 'devanagari', 'tamil').
_INDIC_SCRIPT_MAP: dict[str, str] = {
    "devanagari": sanscript.DEVANAGARI,
    "bengali":    sanscript.BENGALI,
    "gujarati":   sanscript.GUJARATI,
    "gurmukhi":   sanscript.GURMUKHI,
    "kannada":    sanscript.KANNADA,
    "malayalam":  sanscript.MALAYALAM,
    "oriya":      sanscript.ORIYA,
    "tamil":      sanscript.TAMIL,
    "telugu":     sanscript.TELUGU,
}


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


def _romanise_zh(text: str) -> str:
    """Convert Chinese characters to pinyin (no tones) for trigram matching.

    Non-CJK characters (Latin, spaces, digits) are preserved as-is so that
    mixed input like "Shanghai 上海" remains readable after conversion.
    """
    parts = []
    for char in text:
        if _CJK_RE.match(char):
            py = lazy_pinyin(char)
            parts.append(py[0] if py else char)
        else:
            parts.append(char)
    return "".join(parts)


def _romanise_indic(text: str) -> str:
    """Convert Indic-script text to ASCII via IAST then unidecode.

    indic_transliteration auto-detects the source script (Devanagari, Bengali,
    Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Oriya) and outputs
    IAST with diacritics (e.g. muṃbaī).  unidecode then strips the diacritics
    to plain ASCII (mumbai) for trigram matching.
    """
    script = _detect_indic_script(text)
    scheme = _INDIC_SCRIPT_MAP.get(script)
    if not scheme:
        return unidecode(text)
    iast = sanscript.transliterate(text, scheme, sanscript.IAST)
    return unidecode(iast)



def _to_ascii(query: str, lang: str = "") -> str:
    """Transliterate a free-text search query to ASCII for trigram matching.

    Decision tree
    -------------
    1. Contains kana (hiragana U+3040–309F / katakana U+30A0–30FF)
       OR any CJK Unified Ideograph (kanji / hanzi):

       a. Accept-Language primary tag is "zh" → pypinyin (pinyin, no tones)
          e.g. 上海 → "shanghai", 北京 → "beijing"

       b. Accept-Language primary tag is "ja", or no language hint
          → pykakasi (Hepburn romaji)
          e.g. 東京 → "tou kyou", 大阪 → "oosaka"

    2. Indic scripts (U+0900–U+0D7F) → indic_transliteration IAST → unidecode
       e.g. मुंबई → "mumbai", চট্টগ্রাম → "cattagrama"

    3. Everything else (Arabic, Cyrillic, accented Latin, …) → unidecode
       e.g. São Paulo → "Sao Paulo", Москва → "Moskva"
    """
    if _KANA_RE.search(query) or _CJK_RE.search(query):
        primary = lang.split("-")[0].split(";")[0].lower()
        if primary == "zh":
            return _romanise_zh(query)
        return _romanise_ja(query)

    if _INDIC_RE.search(query):
        return _romanise_indic(query)

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
        COALESCE(region_name, '')       || ' ' ||
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
    accept_language: str = "",
) -> list[Airport]:
    """Search airports by any text (name, IATA/ICAO code, city, country, alias).

    Transliteration
    ---------------
    Non-Latin input is converted to ASCII before querying:
      - Japanese kana          → pykakasi Hepburn romaji
      - CJK (kanji / hanzi)    → pykakasi for Japanese, unidecode otherwise
      - All other scripts      → unidecode (accents stripped, Cyrillic/Arabic
                                  converted to nearest Latin equivalent)

    Search strategy — trigram only, two index scans OR-ed:
    -------------------------------------------------------
    1. Scalar fields (airports_trigram_gin index, migration 001):
         ILIKE '%q%'                 — exact substring  (LON, London, São Paulo)
         word_similarity(q, …) > 0.6 — typo-tolerant    (Londn → London)

    2. Alias names (airports_aliases_trigram_gin index, migration 002):
         Same two conditions against aliases_text, so aliases like
         "Heathrow", "Narita", "Nihon" participate in both substring
         and typo-tolerant matching.

    Results are sorted by passenger_volume_rank ASC (rank 1 = busiest/largest airport first).
    """
    normalized = _to_ascii(query, accept_language).strip().lower()

    if not normalized:
        return []

    stmt = (
        select(Airport)
        .where(
            text(
                f"({_TRIGRAM_CONCAT} ILIKE '%' || :q || '%'"
                f" OR word_similarity(:q, {_TRIGRAM_CONCAT}) > 0.6"
                f" OR {_ALIASES_EXPR} ILIKE '%' || :q || '%'"
                f" OR word_similarity(:q, {_ALIASES_EXPR}) > 0.6)"
            ).bindparams(q=normalized)
        )
        .order_by(
            text(
                f"GREATEST(word_similarity(:q, {_TRIGRAM_CONCAT}), word_similarity(:q, {_ALIASES_EXPR})) DESC"
            ).bindparams(q=normalized),
            Airport.rank.asc(),
        )
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())

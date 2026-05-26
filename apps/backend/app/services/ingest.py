import json
import re
from typing import Literal

import pandas as pd
from openai import AsyncOpenAI
from pydantic import BaseModel, field_validator

from app.core.config import settings

_STRIP_TYPES = {"heliport", "closed", "balloonport", "seaplane_base"}

_MILITARY_KEYWORDS = [
    "air force", "afb", "air base", "naval", "military",
    "army", "marine corps", "usaf", "raf", "air station",
]

# smaller batch for alias-heavy prompts reduces cross-airport contamination
_FULL_BATCH_SIZE = 20
_LITE_BATCH_SIZE = 50
_FULL_ENRICHMENT_RANKS = {1, 2, 3}

_IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")

# hardcoded country aliases — deterministic, zero hallucination risk.
# Source "static" distinguishes these from LLM-generated aliases.
_COUNTRY_ALIASES: dict[str, list[dict]] = {
    "AT": [{"name": "Österreich", "type": "endonym", "source": "static", "confidence": "high"}],
    "AU": [{"name": "Oz", "type": "colloquial", "source": "static", "confidence": "high"}],
    "BE": [
        {"name": "Belgique", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "België", "type": "endonym", "source": "static", "confidence": "high"},
    ],
    "BR": [{"name": "Brasil", "type": "endonym", "source": "static", "confidence": "high"}],
    "CH": [
        {"name": "Schweiz", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Suisse", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Svizzera", "type": "endonym", "source": "static", "confidence": "high"},
    ],
    "CN": [
        {"name": "Zhongguo", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "People's Republic of China", "type": "alternate_spelling", "source": "static", "confidence": "high"},
        {"name": "PRC", "type": "colloquial", "source": "static", "confidence": "high"},
    ],
    "CZ": [
        {"name": "Czechia", "type": "alternate_spelling", "source": "static", "confidence": "high"},
        {"name": "Bohemia", "type": "historical", "source": "static", "confidence": "medium"},
    ],
    "DE": [{"name": "Deutschland", "type": "endonym", "source": "static", "confidence": "high"}],
    "DK": [{"name": "Danmark", "type": "endonym", "source": "static", "confidence": "high"}],
    "EG": [{"name": "Misr", "type": "endonym", "source": "static", "confidence": "high"}],
    "ES": [{"name": "España", "type": "endonym", "source": "static", "confidence": "high"}],
    "FI": [{"name": "Suomi", "type": "endonym", "source": "static", "confidence": "high"}],
    "GB": [
        {"name": "United Kingdom", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Britain", "type": "colloquial", "source": "static", "confidence": "high"},
        {"name": "Great Britain", "type": "alternate_spelling", "source": "static", "confidence": "high"},
        # medium: England technically excludes Scotland/Wales/NI
        {"name": "England", "type": "colloquial", "source": "static", "confidence": "medium"},
    ],
    "GR": [
        {"name": "Hellas", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Ellada", "type": "endonym", "source": "static", "confidence": "high"},
    ],
    "HU": [{"name": "Magyarország", "type": "endonym", "source": "static", "confidence": "high"}],
    "IE": [{"name": "Éire", "type": "endonym", "source": "static", "confidence": "high"}],
    "IN": [
        {"name": "Bharat", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Hindustan", "type": "historical", "source": "static", "confidence": "medium"},
    ],
    "IR": [{"name": "Persia", "type": "historical", "source": "static", "confidence": "high"}],
    "IT": [{"name": "Italia", "type": "endonym", "source": "static", "confidence": "high"}],
    "JP": [
        {"name": "Nippon", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Nihon", "type": "endonym", "source": "static", "confidence": "high"},
    ],
    "KH": [{"name": "Kampuchea", "type": "historical", "source": "static", "confidence": "high"}],
    "KR": [{"name": "Republic of Korea", "type": "alternate_spelling", "source": "static", "confidence": "high"}],
    "LK": [{"name": "Ceylon", "type": "historical", "source": "static", "confidence": "high"}],
    "MK": [
        {"name": "Macedonia", "type": "colloquial", "source": "static", "confidence": "high"},
        {"name": "FYROM", "type": "historical", "source": "static", "confidence": "high"},
    ],
    "MM": [{"name": "Burma", "type": "historical", "source": "static", "confidence": "high"}],
    "MX": [{"name": "México", "type": "endonym", "source": "static", "confidence": "high"}],
    "NL": [
        {"name": "Holland", "type": "colloquial", "source": "static", "confidence": "high"},
        {"name": "The Netherlands", "type": "alternate_spelling", "source": "static", "confidence": "high"},
    ],
    "NO": [{"name": "Norge", "type": "endonym", "source": "static", "confidence": "high"}],
    "NZ": [{"name": "Aotearoa", "type": "endonym", "source": "static", "confidence": "high"}],
    "PL": [{"name": "Polska", "type": "endonym", "source": "static", "confidence": "high"}],
    "RO": [{"name": "România", "type": "endonym", "source": "static", "confidence": "high"}],
    "RU": [
        {"name": "Rossiya", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "Soviet Union", "type": "historical", "source": "static", "confidence": "high"},
        {"name": "USSR", "type": "historical", "source": "static", "confidence": "high"},
    ],
    "SE": [{"name": "Sverige", "type": "endonym", "source": "static", "confidence": "high"}],
    "TH": [{"name": "Siam", "type": "historical", "source": "static", "confidence": "high"}],
    "TR": [{"name": "Türkiye", "type": "endonym", "source": "static", "confidence": "high"}],
    "TW": [
        {"name": "Formosa", "type": "historical", "source": "static", "confidence": "high"},
        {"name": "Republic of China", "type": "alternate_spelling", "source": "static", "confidence": "high"},
    ],
    "TZ": [{"name": "Tanganyika", "type": "historical", "source": "static", "confidence": "medium"}],
    "UA": [{"name": "Ukrayina", "type": "endonym", "source": "static", "confidence": "high"}],
    "US": [
        {"name": "United States of America", "type": "endonym", "source": "static", "confidence": "high"},
        {"name": "America", "type": "colloquial", "source": "static", "confidence": "high"},
        {"name": "USA", "type": "alternate_spelling", "source": "static", "confidence": "high"},
    ],
    "VN": [{"name": "Viet Nam", "type": "alternate_spelling", "source": "static", "confidence": "high"}],
    "ZM": [{"name": "Northern Rhodesia", "type": "historical", "source": "static", "confidence": "high"}],
    "ZW": [{"name": "Rhodesia", "type": "historical", "source": "static", "confidence": "high"}],
}


# ---------------------------------------------------------------------------
# Pydantic models — sent to OpenAI as the response_format JSON schema.
# ---------------------------------------------------------------------------

class AliasEntry(BaseModel):
    name: str
    type: Literal["endonym", "exonym", "colloquial", "alternate_spelling", "historical"]
    source: Literal["llm"] = "llm"
    confidence: Literal["high", "medium", "low"]


class ConfidentField(BaseModel):
    value: str
    confidence: Literal["high", "medium", "low"]


class MetroCodeField(BaseModel):
    """Like ConfidentField but normalizes the value to uppercase on parse."""
    value: str
    confidence: Literal["high", "medium", "low"]

    # normalize on parse; invalid codes are caught in _post_process
    @field_validator("value")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()


# country_aliases is intentionally absent — injected from _COUNTRY_ALIASES in
# _post_process so the LLM never has a chance to hallucinate country names.
class EnrichedAirportFull(BaseModel):
    iata_code: str
    metro_city: ConfidentField
    metro_code: MetroCodeField
    municipality_aliases: list[AliasEntry]
    city_aliases: list[AliasEntry]
    region_aliases: list[AliasEntry]


class EnrichedAirportLite(BaseModel):
    iata_code: str
    metro_city: ConfidentField
    metro_code: MetroCodeField


class _BatchFull(BaseModel):
    airports: list[EnrichedAirportFull]


class _BatchLite(BaseModel):
    airports: list[EnrichedAirportLite]


# ---------------------------------------------------------------------------
# CSV analysis
# ---------------------------------------------------------------------------

def _assign_volume_rank(row: pd.Series) -> int:
    if row["type"] == "large_airport" and row["scheduled_service"] == "yes":
        return 1
    elif row["type"] == "large_airport":
        return 2
    elif row["type"] == "medium_airport" and row["scheduled_service"] == "yes":
        return 3
    elif row["type"] == "medium_airport":
        return 4
    else:
        return 5


def analyze_csv(df: pd.DataFrame) -> dict:
    df = df[~df["type"].isin(_STRIP_TYPES)]
    df = df[df["scheduled_service"] == "yes"]
    df = df[df["iata_code"].notna() & (df["iata_code"].str.strip() != "")]

    name_lower = df["name"].str.lower()
    is_military = name_lower.apply(lambda n: any(kw in n for kw in _MILITARY_KEYWORDS))
    df = df[~is_military].copy()

    df["passenger_volume_rank"] = df.apply(_assign_volume_rank, axis=1)

    cols = ["iata_code", "icao_code", "name", "municipality", "iso_country", "iso_region", "passenger_volume_rank"]
    airports = df[cols].fillna("").to_dict("records")

    return {
        "total_airports": len(df),
        "by_rank": df["passenger_volume_rank"].value_counts().sort_index().to_dict(),
        "by_type": df["type"].value_counts().to_dict(),
        "airports": airports,
    }

def _post_process(enriched: list[dict], airports_by_iata: dict[str, dict]) -> list[dict]:
    for entry in enriched:
        iata = entry.get("iata_code", "")
        source_airport = airports_by_iata.get(iata, {})

        # reject any metro_code that isn't exactly 3 uppercase letters
        mc = entry.get("metro_code", {})
        if mc and not _IATA_CODE_RE.match(mc.get("value", "")):
            mc["value"] = iata
            mc["confidence"] = "low"

        # drop any aliases the model marked low-confidence; those are
        # the most likely hallucinations slipping past the prompt instruction
        for field in ("municipality_aliases", "city_aliases", "region_aliases"):
            if field in entry:
                entry[field] = [a for a in entry[field] if a.get("confidence") != "low"]

        # overwrite country_aliases with the hardcoded lookup — the LLM
        # never touches this field, so hallucination here is impossible
        iso_country = source_airport.get("iso_country", "")
        entry["country_aliases"] = _COUNTRY_ALIASES.get(iso_country, [])

    return enriched


# ---------------------------------------------------------------------------
# LLM enrichment
# ---------------------------------------------------------------------------

_FULL_SYSTEM = (
    "You are an aviation geography expert. "
    "Return accurate, verifiable data only. "
    "If you are not certain an alias exists, omit it — do not guess. "
    "Prefer accuracy over completeness."
)

_FULL_USER_TMPL = """\
For each airport in the JSON array below, produce enriched data with these fields:

- iata_code: copy from input unchanged
- metro_city: canonical English name of the metropolitan area the airport serves
  (e.g. Heathrow Airport → "London", Roissy-en-France → "Paris")
- metro_code: official 3-letter IATA city/metro code (e.g. LON, NYC, PAR).
  If no IATA city code exists for the metro area, use the airport's own IATA code.
- municipality_aliases: well-known alternate names for the physical municipality
  (endonyms, exonyms, historical names, colloquial names).
  ONLY include aliases you are certain exist. Return [] if in any doubt.
- city_aliases: well-known alternate names for the metro city
  (e.g. Roma/Rome, München/Munich, Köln/Cologne).
  ONLY include aliases you are certain exist. Return [] if in any doubt.
- region_aliases: well-known alternate names for the region/state/province.
  ONLY include aliases you are certain exist. Return [] if in any doubt.

For metro_city and metro_code assign confidence: "high", "medium", or "low".
For alias entries assign type (endonym | exonym | colloquial | alternate_spelling | historical)
and confidence. Do NOT include aliases with confidence "low" — omit them entirely.

Return exactly one output object per input airport, in the same order.

Input airports:
{airports_json}"""

_LITE_SYSTEM = (
    "You are an aviation geography expert. "
    "Return accurate data only. When uncertain, use confidence 'low'."
)

_LITE_USER_TMPL = """\
For each airport in the JSON array below, produce:

- iata_code: copy from input unchanged
- metro_city: canonical English name of the metropolitan area the airport serves
- metro_code: official 3-letter IATA city/metro code.
  If no IATA city code exists for the metro area, use the airport's own IATA code.

Assign confidence "high", "medium", or "low" for each field.
Return exactly one output object per input airport, in the same order.

Input airports:
{airports_json}"""


async def _call_full(client: AsyncOpenAI, batch: list[dict]) -> list[dict]:
    response = await client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,  # deterministic output for factual extraction
        messages=[
            {"role": "system", "content": _FULL_SYSTEM},
            {"role": "user", "content": _FULL_USER_TMPL.format(
                airports_json=json.dumps(batch, ensure_ascii=False)
            )},
        ],
        response_format=_BatchFull,
    )
    parsed = response.choices[0].message.parsed
    # parsed is None when the model refuses or structured parsing fails
    if parsed is None:
        refusal = response.choices[0].message.refusal
        raise ValueError(f"LLM failed to produce structured output (refusal: {refusal!r})")
    return [a.model_dump() for a in parsed.airports]


async def _call_lite(client: AsyncOpenAI, batch: list[dict]) -> list[dict]:
    response = await client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": _LITE_SYSTEM},
            {"role": "user", "content": _LITE_USER_TMPL.format(
                airports_json=json.dumps(batch, ensure_ascii=False)
            )},
        ],
        response_format=_BatchLite,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        refusal = response.choices[0].message.refusal
        raise ValueError(f"LLM failed to produce structured output (refusal: {refusal!r})")
    return [a.model_dump() for a in parsed.airports]


async def enrich_airports(airports: list[dict]) -> list[dict]:
    """Enrich a list of airport dicts (from analyze_csv) with LLM-generated fields."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    airports_by_iata = {a["iata_code"]: a for a in airports}

    full_airports = [a for a in airports if a["passenger_volume_rank"] in _FULL_ENRICHMENT_RANKS]
    lite_airports = [a for a in airports if a["passenger_volume_rank"] not in _FULL_ENRICHMENT_RANKS]

    results: list[dict] = []

    for i in range(0, len(full_airports), _FULL_BATCH_SIZE):
        batch = full_airports[i : i + _FULL_BATCH_SIZE]
        try:
            enriched = await _call_full(client, batch)
        except Exception as exc:
            print(f"[error] full batch {i}–{i + len(batch)} failed: {exc}")
            continue
        if len(enriched) != len(batch):
            print(f"[warn] full batch {i}–{i + len(batch)}: expected {len(batch)}, got {len(enriched)}")
        results.extend(enriched)

    for i in range(0, len(lite_airports), _LITE_BATCH_SIZE):
        batch = lite_airports[i : i + _LITE_BATCH_SIZE]
        try:
            enriched = await _call_lite(client, batch)
        except Exception as exc:
            print(f"[error] lite batch {i}–{i + len(batch)} failed: {exc}")
            continue
        if len(enriched) != len(batch):
            print(f"[warn] lite batch {i}–{i + len(batch)}: expected {len(batch)}, got {len(enriched)}")
        results.extend(enriched)

    return _post_process(results, airports_by_iata)

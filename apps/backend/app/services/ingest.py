import pandas as pd

_STRIP_TYPES = {"heliport", "closed", "balloonport", "seaplane_base"}

_MILITARY_KEYWORDS = [
    "air force", "afb", "air base", "naval", "military",
    "army", "marine corps", "usaf", "raf", "air station",
]


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

    return {
        "total_airports": len(df),
        "by_rank": df["passenger_volume_rank"].value_counts().sort_index().to_dict(),
        "by_type": df["type"].value_counts().to_dict(),
    }


async def run_llm(analysis: dict) -> str:
    """Send the analysis summary to an LLM and return its response."""
    raise NotImplementedError

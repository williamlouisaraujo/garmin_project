from __future__ import annotations

import pandas as pd


def activities_to_dataframe(activities: list[dict]) -> pd.DataFrame:
    if not activities:
        return pd.DataFrame()
    df = pd.DataFrame(activities)
    for col in ("distance", "duration"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
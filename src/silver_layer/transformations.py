"""Data transformations for Silver layer."""

import pandas as pd


def normalize_location(location: str) -> str:
    """Normalize location names to standardized format.

    Args:
        location: Raw location string from job listing

    Returns:
        Normalized location string
    """
    location = location.lower()

    # Jakarta districts
    if "jakarta selatan" in location or "south jakarta" in location:
        return "Jakarta Selatan"
    elif "jakarta barat" in location or "west jakarta" in location:
        return "Jakarta Barat"
    elif "jakarta pusat" in location or "central jakarta" in location:
        return "Jakarta Pusat"
    elif "jakarta timur" in location or "east jakarta" in location:
        return "Jakarta Timur"
    elif "jakarta utara" in location or "north jakarta" in location:
        return "Jakarta Utara"
    elif "jakarta" in location:
        return "Jakarta"

    # other cities
    elif "yogyakarta" in location or "jogja" in location:
        return "Yogyakarta"
    elif "bandung" in location:
        return "Bandung"
    elif "surabaya" in location:
        return "Surabaya"
    elif "tangerang" in location:
        return "Tangerang"
    elif "bekasi" in location or "cikarang" in location:
        return "Bekasi"
    elif "depok" in location:
        return "Depok"
    elif "bogor" in location or "cileungsi" in location:
        return "Bogor"
    elif "semarang" in location:
        return "Semarang"
    else:
        return location.title()


def apply_location_normalization(df: pd.DataFrame) -> pd.DataFrame:
    """Apply location normalization to DataFrame."""
    if "location" not in df.columns:
        df["location"] = "Unknown"
        return df
    
    #  Perbaikan: paksa jadi string dulu, NaN → "Unknown"
    df["location"] = df["location"].astype(str).fillna("Unknown")
    df["location"] = df["location"].apply(normalize_location)
    
    return df

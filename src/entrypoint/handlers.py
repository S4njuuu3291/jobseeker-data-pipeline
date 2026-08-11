# Lazy import untuk handler (tanpa import top-level yang berat)
import os

# Daftar keyword yang ingin kamu scrape secara rutin


def _get_keywords(default: list[str]) -> list[str]:
    env_keywords = os.getenv("SCRAPE_KEYWORDS")
    if env_keywords:
        return [kw.strip() for kw in env_keywords.split(",") if kw.strip()]
    return default


DEFAULT_KEYWORDS = [
    "data-engineer",
    "etl",
    "big-data-engineer",
]

DEFAULT_KEYWORDS_PLUS = [
    "data+engineer",
    "etl",
    "big+data+engineer",
]

# TechInAsia pakai spasi biasa (di-quote jadi %20 di main)
DEFAULT_KEYWORDS_SPACE = [
    "data engineer",
    "etl developer",
    "big data engineer",
]

# Mapping keyword per platform (untuk generic handler)
PLATFORM_KEYWORDS = {
    "kalibrr": DEFAULT_KEYWORDS,
    "glints": DEFAULT_KEYWORDS_PLUS,
    "jobstreet": DEFAULT_KEYWORDS,
    "dealls": DEFAULT_KEYWORDS_PLUS,
    "techinasia": DEFAULT_KEYWORDS_SPACE,
}


def scraper_handler(event, context):
    """Generic Lambda handler untuk semua platform scraper.

    Dispatch ke pipeline yang sesuai berdasarkan event["platform"].

    Event payload:
        {"platform":"glints"} | {"platform":"jobstreet"} | {"platform":"kalibrr"} | {"platform":"dealls"}
    """
    import asyncio

    platform = (event.get("platform") or "").strip().lower()
    if not platform:
        raise ValueError("Missing 'platform' in event payload")

    if platform == "kalibrr":
        from src.main.main_kalibrr import run_kalibrr_pipeline
        runner = run_kalibrr_pipeline
        label = "Kalibrr"
    elif platform == "glints":
        from src.main.main_glints import run_glints_pipeline
        runner = run_glints_pipeline
        label = "Glints"
    elif platform == "jobstreet":
        from src.main.main_jobstreet import run_jobstreet_pipeline
        runner = run_jobstreet_pipeline
        label = "JobStreet"
    elif platform == "dealls":
        from src.main.main_dealls import run_dealls_pipeline
        runner = run_dealls_pipeline
        label = "Dealls"
    elif platform == "techinasia":
        from src.main.main_techinasia import run_techinasia_pipeline
        runner = run_techinasia_pipeline
        label = "TechInAsia"
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    keywords = _get_keywords(PLATFORM_KEYWORDS.get(platform, []))
    print(f"Scraping platform: {label}")
    try:
        result = asyncio.run(runner(keywords))
        return {
            "statusCode": 200,
            "platform": platform,
            "body": f"{label}: {result} data berhasil diproses",
        }
    except Exception as e:
        print(f"Error di Lambda {label}: {e}")
        raise


# Handler untuk Silver Layer
def silver_layer_handler(event, context):
    """AWS Lambda handler untuk Silver layer transformation."""
    from src.silver_layer.main import lambda_handler

    print("Memicu Lambda Silver Layer...")
    try:
        result = lambda_handler(event, context)
        return result
    except Exception as e:
        print(f"Error di Lambda Silver Layer: {e}")
        raise

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

DEFAULT_KEYWORDS_GLINTS = [
    "data+engineer",
    "etl",
    "big+data+engineer",
]

# Handler untuk Kalibrr
def kalibrr_handler(event, context):
    import asyncio
    from src.main.main_kalibrr import run_kalibrr_pipeline

    print("Memicu Lambda Kalibrr...")
    # asyncio.run digunakan karena Lambda adalah fungsi sinkronous
    # sedangkan scraper kita asinkronous (async/await)
    keywords = _get_keywords(DEFAULT_KEYWORDS)
    try:
        result = asyncio.run(run_kalibrr_pipeline(keywords))
        return {
            "statusCode": 200,
            "body": f"Kalibrr: {result} data berhasil diproses",
        }
    except Exception as e:
        print(f"Error di Lambda Kalibrr: {e}")
        raise


# Handler untuk Glints
def glints_handler(event, context):
    import asyncio
    from src.main.main_glints import run_glints_pipeline

    print("Memicu Lambda Glints...")
    keywords = _get_keywords(DEFAULT_KEYWORDS_GLINTS)
    try:
        result = asyncio.run(run_glints_pipeline(keywords))
        return {
            "statusCode": 200,
            "body": f"Glints: {result} data berhasil diproses",
        }
    except Exception as e:
        print(f"Error di Lambda Glints: {e}")
        raise


# Handler untuk JobStreet
def jobstreet_handler(event, context):
    import asyncio
    from src.main.main_jobstreet import run_jobstreet_pipeline

    print("Memicu Lambda JobStreet...")
    keywords = _get_keywords(DEFAULT_KEYWORDS)
    try:
        result = asyncio.run(run_jobstreet_pipeline(keywords))
        return {
            "statusCode": 200,
            "body": f"JobStreet: {result} data berhasil diproses",
        }
    except Exception as e:
        print(f"Error di Lambda JobStreet: {e}")
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

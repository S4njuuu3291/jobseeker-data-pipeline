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


def _load_runtime_secret(variable: str) -> None:
    """Fetch only the selected function's secret; never print its value."""
    if os.getenv(variable):
        return
    parameter = os.getenv(f"{variable}_PARAMETER")
    if not parameter:
        return  # Local execution can continue using .env as before.
    import boto3

    response = boto3.client("ssm").get_parameter(Name=parameter, WithDecryption=True)
    value = response["Parameter"]["Value"].strip()
    if not value or value == "placeholder":
        raise ValueError(
            f"Populate SSM parameter {parameter} before invoking this Lambda"
        )
    os.environ[variable] = value


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
    if platform == "glints":
        _load_runtime_secret("GLINTS_COOKIE")
    elif platform == "techinasia":
        _load_runtime_secret("TECHINASIA_API_KEY")

    if platform == "kalibrr":
        from src.main.main import run_kalibrr_pipeline

        runner = run_kalibrr_pipeline
        label = "Kalibrr"
    elif platform == "glints":
        from src.main.main import run_glints_pipeline

        runner = run_glints_pipeline
        label = "Glints"
    elif platform == "jobstreet":
        from src.main.main import run_jobstreet_pipeline

        runner = run_jobstreet_pipeline
        label = "JobStreet"
    elif platform == "dealls":
        from src.main.main import run_dealls_pipeline

        runner = run_dealls_pipeline
        label = "Dealls"
    elif platform == "techinasia":
        from src.main.main import run_techinasia_pipeline

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
    _load_runtime_secret("DEEPSEEK_API_KEY")
    from src.silver_layer.main import lambda_handler

    print("Memicu Lambda Silver Layer...")
    try:
        result = lambda_handler(event, context)
        if result.get("statusCode", 500) >= 400:
            # Step Functions retries/stops on a Lambda failure, not on a
            # statusCode buried inside an otherwise successful response.
            raise RuntimeError(
                "Silver transformation failed; see Silver CloudWatch logs"
            )
        return result
    except Exception as e:
        print(f"Error di Lambda Silver Layer: {e}")
        raise

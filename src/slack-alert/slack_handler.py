import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import requests
from boto3 import client

if TYPE_CHECKING:
    from mypy_boto3_athena import AthenaClient

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def import_url():
    ssm = client("ssm")
    try:
        response = ssm.get_parameter(
            Name="/jobscraper/slack/webhook_url", WithDecryption=True
        )
        return response["Parameter"]["Value"]
    except Exception as e:
        logger.error(f"Failed to retrieve Slack webhook URL from SSM: {e}")
        raise


def athena_query(
    ingestion_date: str = datetime.now().strftime("%Y-%m-%d"),
) -> list[dict]:
    # Validasi format tanggal untuk mencegah SQL injection
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ingestion_date):
        raise ValueError(f"Invalid ingestion_date format: {ingestion_date}")

    athena: AthenaClient = client("athena")

    # Use v_jobscraper_clean view which has ingestion_date and discovery_type columns
    # Lake Formation permissions now granted for the view
    query = f"""
    SELECT * FROM v_jobscraper_clean
    WHERE ingestion_date = '{ingestion_date}'
    AND discovery_type = 'NEW'
    """

    logger.info(f"Executing Athena query for date: {ingestion_date}")
    logger.info(f"Query: {query}")

    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": "jobscraper_db"},
        WorkGroup="jobscraper-slack-alert-workgroup",
    )

    query_id = response["QueryExecutionId"]
    logger.info(f"Query ID: {query_id}")

    while True:
        query_status = athena.get_query_execution(QueryExecutionId=query_id)
        status = query_status["QueryExecution"]["Status"]["State"]

        if status in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break

        logger.info(f"Query status: {status}. Waiting for completion...")
        time.sleep(2)

    parsed_data = []

    if status == "SUCCEEDED":
        results = athena.get_query_results(QueryExecutionId=query_id)
        rows = results["ResultSet"]["Rows"]

        logger.info(f"Query returned {len(rows)} rows (including header)")

        if len(rows) <= 1:
            logger.warning("Query completed but no data found.")
            print(f"⚠️ Query completed but no data found. Rows: {len(rows)}")
            return []

        # Parse column names from header
        columns = [col.get("VarCharValue", "") for col in rows[0]["Data"]]
        logger.info(f"Columns: {columns}")
        print(f"📊 Columns: {columns}")

        # Parse data rows
        for row_idx, row in enumerate(rows[1:], 1):
            row_dict = {}
            try:
                for col_idx, col in enumerate(columns):
                    value = row["Data"][col_idx].get("VarCharValue", "")
                    row_dict[col] = value
                parsed_data.append(row_dict)
            except (IndexError, KeyError) as e:
                logger.warning(f"Error parsing row {row_idx}: {e}")
                continue

        logger.info(f"✅ Parsed {len(parsed_data)} job records successfully!")
        print(f"✅ Parsed {len(parsed_data)} job records successfully!")
    else:
        logger.error(f"Query failed with status: {status}")
        print(f"❌ Query failed with status: {status}")
        if "StateChangeReason" in query_status["QueryExecution"]["Status"]:
            reason = query_status["QueryExecution"]["Status"]["StateChangeReason"]
            logger.error(f"Reason: {reason}")
            print(f"❌ Reason: {reason}")

    return parsed_data


def send_slack_alert(blocks: list, webhook_url: str):
    """Send alert message to Slack channel via webhook using Block Kit."""

    payload = {"blocks": blocks}
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print("✅ Alert sent to Slack successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send alert to Slack: {e}")


def shorten_url(url: str) -> str:
    """Shorten URL using TinyURL API."""
    try:
        response = requests.get(
            f"https://tinyurl.com/api-create.php?url={url}", timeout=5
        )
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.warning(f"Failed to shorten URL: {e}")

    return url  # Fallback to original URL


def format_job_blocks(parsed_data: list[dict]) -> list:
    """Format job data into Slack Block Kit format for mobile-friendly display."""

    # Platform emoji and color mapping
    platform_config = {
        "glints": {"emoji": "GLINTS 🎯", "color": "#FF6B6B"},
        "jobstreet": {"emoji": "JOBSTREET 💼", "color": "#4ECDC4"},
        "kalibrr": {"emoji": "KALIBRR ⭐", "color": "#FFE66D"},
    }

    blocks = []

    # Header section
    wib = timezone(timedelta(hours=7))
    now_wib = datetime.now(wib)
    time_str = now_wib.strftime("%d %b, %H:%M WIB")

    if not parsed_data:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "ℹ️ *No new job postings found for today.*",
                },
            }
        )
        return blocks

    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🆕 {len(parsed_data)} New Job{'s' if len(parsed_data) > 1 else ''} Found",
                "emoji": True,
            },
        }
    )

    blocks.append(
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"📋 {time_str}"}]}
    )

    blocks.append({"type": "divider"})

    # Job listings
    for idx, job in enumerate(parsed_data, 1):
        platform = job.get("platform", "unknown").lower()
        config = platform_config.get(platform, {"emoji": "💼", "color": "#5C5C5C"})

        short_url = shorten_url(job["job_url"])

        # Job card with context
        keyword_label = f" • 🔑 {job.get('keyword', '-')}" if job.get("keyword") else ""
        job_text = (
            f"*{idx}. {job['job_title']}*\n"
            f"{config['emoji']} {job['company_name']} • 📍 {job['location']}"
            f"{keyword_label}"
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": job_text,
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open", "emoji": True},
                    "url": short_url,
                    "style": "primary",
                },
            }
        )

        if idx < len(parsed_data):
            blocks.append({"type": "divider"})

    return blocks


def lambda_handler(event, context):
    # Allow override via event payload, fallback to env var, default prod
    env = event.get("ENVIRONMENT") or os.getenv("ENVIRONMENT", "prod")

    # Dev mode: kirim pesan simple aja, skip query/format/parse
    if env == "dev":
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *ALL GOOD* — Slack alert Lambda berjalan dengan baik di environment *dev*."
                }
            }
        ]
        send_slack_alert(blocks, import_url())
        logger.info("Dev mode: simple healthcheck alert sent")
        return {"statusCode": 200, "body": "Dev healthcheck sent"}

    ingestion_date = event.get("ingestion_date", datetime.now().strftime("%Y-%m-%d"))
    # Validasi format tanggal untuk mencegah SQL injection
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ingestion_date):
        raise ValueError(f"Invalid ingestion_date format: {ingestion_date}")
    parsed_data = athena_query(ingestion_date)

    # Format job data into Slack blocks
    blocks = format_job_blocks(parsed_data)

    # Send to Slack
    send_slack_alert(blocks, import_url())
    logger.info(f"Alert sent: {len(parsed_data)} jobs")

    return {"statusCode": 200, "body": "Slack message sent successfully!"}


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    lambda_handler({"ingestion_date": today}, {})

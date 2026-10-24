"""Install the existing Athena views for dev/prod after Terraform apply.

--dry-run only renders SQL and never creates an AWS client.
"""

import argparse
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def view_statements(environment):
    if environment not in {"dev", "prod"}:
        raise ValueError("Environment must be dev or prod")
    suffix = "_dev" if environment == "dev" else ""
    for filename in ("v_jobscraper_clean.sql", "analytics_views.sql"):
        sql = (ROOT / "scripts/athena" / filename).read_text()
        sql = sql.replace('"jobscraper_db"', f'"jobscraper_db{suffix}"')
        sql = sql.replace(
            '"jobscraper_silver_table"', f'"jobscraper_silver_table{suffix}"'
        )
        for statement in sql.split(";"):
            if "CREATE OR REPLACE VIEW" in statement:
                yield statement.strip()


def deploy(environment, timeout=120):
    import boto3

    client = boto3.client("athena")
    suffix = "-dev" if environment == "dev" else ""
    database = "jobscraper_db_dev" if environment == "dev" else "jobscraper_db"
    for statement in view_statements(environment):
        query_id = client.start_query_execution(
            QueryString=statement,
            QueryExecutionContext={"Database": database},
            WorkGroup=f"jobscraper-slack-alert-workgroup{suffix}",
        )["QueryExecutionId"]
        deadline = time.monotonic() + timeout
        while True:
            status = client.get_query_execution(QueryExecutionId=query_id)[
                "QueryExecution"
            ]["Status"]
            if status["State"] == "SUCCEEDED":
                break
            if status["State"] in {"FAILED", "CANCELLED"}:
                raise RuntimeError(
                    f"View query {query_id} failed: {status.get('StateChangeReason', status['State'])}"
                )
            if time.monotonic() >= deadline:
                client.stop_query_execution(QueryExecutionId=query_id)
                raise TimeoutError(f"View query {query_id} timed out")
            time.sleep(2)
        print(f"Athena view installed: {query_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=["dev", "prod"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(";\n\n".join(view_statements(args.environment)) + ";")
    else:
        deploy(args.environment)

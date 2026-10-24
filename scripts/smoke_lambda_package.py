"""Offline smoke test executed with only packaged code + layer directories."""

import importlib
import importlib.util
import io
import sys

name = sys.argv[1]
if importlib.util.find_spec("playwright") is not None:
    raise RuntimeError("Lambda package unexpectedly includes Playwright")
# Force botocore to load the service models offline after pruning.
boto3 = importlib.import_module("boto3")

session = boto3.Session(
    aws_access_key_id="test", aws_secret_access_key="test", region_name="ap-southeast-1"
)
for service in ("s3", "ssm", "sts", "athena", "glue", "kms"):
    session.client(service).close()
if name == "slack":
    importlib.import_module("slack_handler")
else:
    import pandas as pd

    for module in ("pandera.pandas", "boto3", "src.entrypoint.handlers"):
        importlib.import_module(module)

    data = pd.DataFrame(
        {"id": ["native-id"], "salary": pd.array([None], dtype="Int64")}
    )
    buffer = io.BytesIO()
    data.to_parquet(buffer, engine="pyarrow", index=False)
    buffer.seek(0)
    assert pd.read_parquet(buffer).id.tolist() == ["native-id"]
    if name == "bronze":
        assert callable(importlib.import_module("src.main.main").run_scraper_pipeline)

        for platform in ("dealls", "glints", "jobstreet", "kalibrr", "techinasia"):
            importlib.import_module(f"src.scraper.jobscraper_{platform}")
    else:
        assert callable(
            importlib.import_module("src.silver_layer.orchestrator").transform_silver
        )
        for module in ("openai", "json_repair"):
            importlib.import_module(module)
print(f"{name}: packaged imports + native dependency smoke test passed")

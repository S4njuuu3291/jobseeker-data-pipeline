"""Environment isolation and query failure handling for Athena view deployment."""

from unittest.mock import Mock, patch

import pytest

from scripts.deploy_athena_views import deploy, view_statements


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_views_use_the_selected_database_and_table(environment):
    sql = list(view_statements(environment))
    assert len(sql) == 8
    suffix = "_dev" if environment == "dev" else ""
    combined = "\n".join(sql)
    assert f'"jobscraper_db{suffix}"' in combined
    assert f'"jobscraper_silver_table{suffix}"' in combined
    if environment == "dev":
        assert '"jobscraper_db"' not in combined
        assert '"jobscraper_silver_table"' not in combined


def test_failed_view_query_fails_deployment():
    client = Mock()
    client.start_query_execution.return_value = {"QueryExecutionId": "test-query"}
    client.get_query_execution.return_value = {
        "QueryExecution": {
            "Status": {"State": "FAILED", "StateChangeReason": "Schema mismatch"}
        }
    }
    with patch("boto3.client", return_value=client):
        with pytest.raises(RuntimeError, match="Schema mismatch"):
            deploy("dev")
    assert client.start_query_execution.call_args.kwargs["QueryExecutionContext"] == {
        "Database": "jobscraper_db_dev"
    }
    assert client.start_query_execution.call_args.kwargs["WorkGroup"].endswith("-dev")

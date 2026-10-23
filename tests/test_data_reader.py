import io
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.utils.data_reader import read_parquet, reconcile


def test_reader_combines_all_pages_and_batches_without_hiding_duplicate_ids(caplog):
    s3 = MagicMock()
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "batch1.parquet"}, {"Key": "ignore.txt"}]},
        {"Contents": [{"Key": "batch2.parquet"}]},
    ]
    buffers = []
    for ids in [["1", "2"], ["2", "3"]]:
        buf = io.BytesIO()
        pd.DataFrame(
            {
                "job_id": ids,
                "platform": ["kalibrr"] * 2,
                "job_description": ["long text"] * 2,
            }
        ).to_parquet(buf)
        buffers.append(io.BytesIO(buf.getvalue()))
    s3.get_object.side_effect = [{"Body": buf} for buf in buffers]
    with patch("src.utils.data_reader.boto3.client", return_value=s3):
        result = read_parquet("test-bucket", "platform=kalibrr/")
    assert len(result) == 4
    assert result.job_id.tolist() == ["1", "2", "2", "3"]
    assert "job_description" not in result.columns
    assert all(buf.closed for buf in buffers)
    assert "1 baris ID duplikat" in caplog.text


def test_missing_parquet_is_reported_as_error():
    s3 = MagicMock()
    s3.get_paginator.return_value.paginate.return_value = [{}]
    with patch("src.utils.data_reader.boto3.client", return_value=s3):
        with pytest.raises(ValueError, match="tidak berisi parquet"):
            read_parquet("test-bucket", "empty/")


def test_bronze_only_reads_selected_platform_without_silver(capsys):
    with patch(
        "src.utils.data_reader.read_parquet",
        return_value=pd.DataFrame({"job_id": ["123"]}),
    ) as read:
        assert reconcile("2026-10-23", platforms=("kalibrr",), layer="bronze") == []
    assert read.call_count == 1
    assert read.call_args.args[1] == "platform=kalibrr/ingestion_date=2026-10-23/"
    output = capsys.readouterr().out
    assert "kalibrr" in output
    assert "SILVER" not in output

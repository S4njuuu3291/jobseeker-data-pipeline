"""
Manifest manager untuk incremental dedup pipeline.

Menyimpan daftar job_id yang sudah pernah discrape di S3 (format Parquet),
agar pipeline tidak scrape/parsing ulang data yang sama setiap hari.

Alur:
  1. Baca manifest Parquet dari S3 → populate seen_ids
  2. Scrape → skip job_id yang sudah ada
  3. Upload data baru ke Bronze
  4. Update manifest: timpa file Parquet dengan seen_ids terbaru

Struktur S3:
  s3://<bronze-bucket>/manifests/<platform>/job_ids.parquet
  Satu kolom: job_id (string)
"""

import io
import logging
import os
from typing import Set

import boto3
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa

logger = logging.getLogger(__name__)

MANIFEST_KEY = "manifests/{platform}/job_ids.parquet"


def _get_bucket_name() -> str:
    """Get Bronze bucket name from environment."""
    bucket = os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket:
        raise ValueError("AWS_S3_BUCKET_NAME environment variable not set")
    return bucket


def _manifest_key(platform: str) -> str:
    """Generate S3 key untuk file manifest Parquet."""
    return MANIFEST_KEY.format(platform=platform)


def read_manifest(platform: str) -> Set[str]:
    """Baca file manifest Parquet dari S3, return set of job_ids.

    Args:
        platform: Nama platform (glints, kalibrr, jobstreet)

    Returns:
        Set of job_id strings. Empty set jika manifest belum ada.
    """
    s3 = boto3.client("s3")
    bucket = _get_bucket_name()
    key = _manifest_key(platform)

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body_bytes = response["Body"].read()
        table = pq.read_table(io.BytesIO(body_bytes))
        df = table.to_pandas()
        job_ids = set(df["job_id"].dropna().tolist()) if "job_id" in df.columns else set()
        logger.info(f"📋 Manifest {platform}: {len(job_ids)} job_id existing")
        return job_ids
    except s3.exceptions.NoSuchKey:
        logger.info(f"📋 Manifest {platform} belum ada — first run, start fresh")
        return set()
    except Exception as e:
        logger.warning(f"⚠️  Gagal baca manifest {platform}: {e}, start fresh")
        return set()


def update_manifest(platform: str, seen_ids: Set[str]) -> bool:
    """Simpan seen_ids sebagai file Parquet (create or replace).

    Args:
        platform: Nama platform
        seen_ids: Complete set of job_ids yang sudah discrape

    Returns:
        True if sukses, False otherwise
    """
    s3 = boto3.client("s3")
    bucket = _get_bucket_name()
    key = _manifest_key(platform)

    # Pastikan selalu ada data — minimal DataFrame kosong dengan kolom job_id
    df = pd.DataFrame({"job_id": sorted(seen_ids) if seen_ids else []})
    table = pa.Table.from_pandas(df)

    try:
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=buf.getvalue().to_pybytes(),
        )
        logger.info(f"📋 Manifest {platform} tersimpan: {len(seen_ids)} job_ids")
        return True
    except Exception as e:
        logger.error(f"❌ Gagal simpan manifest {platform}: {e}")
        return False


def filter_new_jobs(cards: list[dict], seen_ids: Set[str]) -> list[dict]:
    """Filter job cards, return hanya yang job_id-nya BELUM ada di manifest.

    Args:
        cards: List dari collect_job_cards() — [{job_id, job_title, ...}, ...]
        seen_ids: Set of job_ids dari read_manifest()

    Returns:
        List job cards yang belum pernah discrape (baru).
    """
    if not seen_ids:
        return cards

    new_cards = []
    skipped = 0
    for card in cards:
        jid = card.get("job_id")
        if jid and jid in seen_ids:
            skipped += 1
        else:
            new_cards.append(card)

    if skipped:
        logger.info(f"⏭️  Skip {skipped} job sudah ada di manifest")
    return new_cards


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python manifest.py <platform> read")
        print("  python manifest.py <platform> update [job_id ...]")
        print("  python manifest.py <platform> filter <job_id1> <job_id2> ...")
        sys.exit(1)

    platform = sys.argv[1]
    action = sys.argv[2]

    if action == "read":
        ids = read_manifest(platform)
        print(f"Total: {len(ids)} job_ids")
        for jid in sorted(ids):
            print(f"  {jid}")

    elif action == "update":
        new_ids = set(sys.argv[3:]) if len(sys.argv) > 3 else set()
        if new_ids:
            update_manifest(platform, new_ids)
            print(f"✅ Manifest {platform} diupdate dengan {len(new_ids)} job_ids")
        else:
            update_manifest(platform, set())
            print(f"✅ Manifest {platform} dibuat (kosong)")

    elif action == "filter":
        seen = read_manifest(platform)
        cards = [{"job_id": jid, "job_title": f"Job-{jid[:8]}"} for jid in sys.argv[3:]]
        baru = filter_new_jobs(cards, seen)
        print(f"Dari {len(cards)} card, {len(baru)} baru (sisanya sudah di manifest)")
        for c in baru:
            print(f"  ✅ {c['job_id']} - {c['job_title']}")

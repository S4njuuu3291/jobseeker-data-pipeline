"""Build Linux CPython 3.12 x86_64 Lambda ZIPs without Docker or a browser.

Run from the repository root: python scripts/build_lambda_packages.py
All resolved versions are constrained by poetry.lock. No local .env or data files
are copied. Deployment uploads the resulting ZIPs through an S3 artifact bucket.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 250 * 1024 * 1024
LAYERS = {
    "data": "lambda-layers/shared-data/requirements.txt",
    "bronze": "lambda-layers/bronze/requirements.txt",
    "silver": "lambda-layers/silver/requirements.txt",
    "slack": "lambda-layers/slack-alert-layer/requirements.txt",
}


def archive(source, destination):
    with zipfile.ZipFile(
        destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                # Stable timestamps keep identical source/dependencies from
                # publishing new layer versions just because CI ran again.
                info = zipfile.ZipInfo(
                    path.relative_to(source).as_posix(), (2020, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)


def prune(target):
    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_dir() and path.name in {"tests", "test", "__pycache__"}:
            shutil.rmtree(path)
        elif path.is_file() and path.suffix in {".pyc", ".pyo"}:
            path.unlink()
    shutil.rmtree(target / "bin", ignore_errors=True)
    # Development headers are useful for compiling extensions, not for running
    # pandas/Arrow. Drop them to leave headroom below Lambda's 250 MB limit.
    for directory in ("pyarrow/include", "pyarrow/src", "numpy/_core/include"):
        shutil.rmtree(target / directory, ignore_errors=True)
    # Preserve dist-info, timezone data and all Parquet runtime libraries.


def uncompressed_size(path):
    with zipfile.ZipFile(path) as package:
        return sum(entry.file_size for entry in package.infolist())


def build(output):
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Build with Python 3.12 (the Lambda runtime).")
    output.mkdir(parents=True, exist_ok=True)
    work = output / "staging"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    lock = tomllib.loads((ROOT / "poetry.lock").read_text())
    constraints = work / "constraints.txt"
    constraints.write_text(
        "\n".join(sorted({f"{p['name']}=={p['version']}" for p in lock["package"]}))
        + "\n"
    )
    for name, requirement in LAYERS.items():
        directory = work / f"{name}-layer"
        target = directory / "python"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--platform",
                "manylinux_2_28_x86_64",
                "--platform",
                "manylinux2014_x86_64",
                "--python-version",
                "3.12",
                "--implementation",
                "cp",
                "--abi",
                "cp312",
                "--no-compile",
                "-c",
                str(constraints),
                "-r",
                str(ROOT / requirement),
                "-t",
                str(target),
            ],
            check=True,
        )
        prune(target)
        if name in {"bronze", "silver"}:
            shared = work / "data-layer" / "python"
            for common in shared.rglob("*"):
                duplicate = target / common.relative_to(shared)
                if common.is_file() and duplicate.is_file():
                    duplicate.unlink()
        archive(directory, output / f"{name}-layer.zip")

    for name in ("bronze", "silver"):
        directory = work / f"{name}-code"
        allowed = (
            {"entrypoint", "utils", "main", "scraper"}
            if name == "bronze"
            else {"entrypoint", "utils", "silver_layer", "ai"}
        )
        for source in (ROOT / "src").rglob("*.py"):
            relative = source.relative_to(ROOT)
            if "__pycache__" in relative.parts or "dev-docs" in relative.parts:
                continue
            if len(relative.parts) > 2 and relative.parts[1] not in allowed:
                continue
            if relative.parts[1] == "utils" and source.stem not in {
                "__init__",
                "time_utils",
                "manifest",
                "keywords",
                "data_validator",
                "upload_to_s3",
            }:
                continue
            dest = directory / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        archive(directory, output / f"{name}.zip")
    directory = work / "slack-code"
    directory.mkdir()
    for source in (ROOT / "src/slack-alert").glob("*.py"):
        shutil.copyfile(source, directory / source.name)
    archive(directory, output / "slack.zip")

    validate_packages(output, work)


def validate_packages(output, work):
    sizes = {}
    for name, layers in {
        "bronze": ["data", "bronze"],
        "silver": ["data", "silver"],
        "slack": ["slack"],
    }.items():
        size = uncompressed_size(output / f"{name}.zip") + sum(
            uncompressed_size(output / f"{layer}-layer.zip") for layer in layers
        )
        sizes[name] = {
            "uncompressed_bytes": size,
            "limit_bytes": LIMIT,
            "layers": layers,
        }
        if size >= LIMIT:
            raise SystemExit(
                f"{name}: code + layers are {size:,} bytes; Lambda limit is {LIMIT:,}."
            )
    (output / "manifest.json").write_text(json.dumps(sizes, indent=2) + "\n")
    print(json.dumps(sizes, indent=2))
    # Confirm the staged Linux native extensions actually load on the Linux CI
    # runner and exercise a Parquet round trip before anything is deployed.
    for name in ("bronze", "silver", "slack"):
        paths = [work / f"{name}-code"]
        if name != "slack":
            paths.append(work / "data-layer/python")
        paths.append(work / f"{name}-layer/python")
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(map(str, paths)),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_DEFAULT_REGION": "ap-southeast-1",
            "platform": "kalibrr,glints,jobstreet,dealls,techinasia",
        }
        # -S excludes the build environment's site-packages so missing layer
        # dependencies cannot be hidden by a developer machine or CI tools.
        subprocess.run(
            [sys.executable, "-S", str(ROOT / "scripts/smoke_lambda_package.py"), name],
            env=env,
            cwd=output,
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".lambda-build")
    args = parser.parse_args()
    build(args.output.resolve())

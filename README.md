# WNBA Data Sync Service

Continuously synchronize WNBA parquet datasets from GitHub into Azure Blob Storage.

## What this does

- Discovers parquet files from one or more GitHub source paths.
- Uploads new files into blob storage.
- Detects changes with file SHA metadata and uploads only updated files.
- Skips unchanged files for incremental, idempotent sync runs.

## Environment variables

Required:

- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER`

Optional with defaults:

- `GITHUB_OWNER=sportsdataverse`
- `GITHUB_REPO=wehoop-wnba-data`
- `GITHUB_BRANCH=main`
- `GITHUB_TOKEN=` (recommended for higher API rate limits)
- `GITHUB_BASE_PATH=wnba/team_box/parquet`
- `GITHUB_BASE_PATHS=` comma-separated list of source paths (preferred over `GITHUB_BASE_PATH`)
- `BLOB_STRIP_PREFIX=wnba/` strips this prefix from blob names
- `SYNC_MAX_FILES=` positive integer limit for quick test runs

If both `GITHUB_BASE_PATHS` and `GITHUB_BASE_PATH` are set, `GITHUB_BASE_PATHS` is used.

## Setup

```bash
python -m venv env
source env/Scripts/activate
pip install -r requirements.txt
```

## Run examples

Single path:

```bash
GITHUB_BASE_PATH=wnba/player_box/parquet python src/sync.py
```

Multiple paths:

```bash
GITHUB_BASE_PATHS=wnba/team_box/parquet,wnba/player_box/parquet,wnba/schedules/parquet python src/sync.py
```

Quick test run with a file cap:

```bash
GITHUB_BASE_PATHS=wnba/team_box/parquet,wnba/player_box/parquet SYNC_MAX_FILES=5 python src/sync.py
```

## Output

Each run prints a summary JSON like:

```json
{
	"total_files_scanned": 200,
	"new_files_uploaded": 40,
	"updated_files_uploaded": 10,
	"files_skipped": 150,
	"files_errored": 0,
	"execution_time_seconds": 12.341
}
```

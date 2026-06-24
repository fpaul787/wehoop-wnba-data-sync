"""Incremental GitHub-to-Blob parquet sync entrypoint."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from github_client import build_default_client
import requests

from storage_client import build_storage_client_from_env


def _parse_sync_max_files(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid SYNC_MAX_FILES='{value}'. Expected a positive integer."
        ) from exc

    if parsed <= 0:
        raise ValueError(
            f"Invalid SYNC_MAX_FILES='{value}'. Expected a positive integer."
        )

    return parsed


def _parse_base_paths() -> list[str]:
    """Resolve one or more GitHub base paths from environment variables."""

    def _normalize_and_dedupe_paths(raw_paths: list[str]) -> list[str]:
        normalized_paths: list[str] = []
        seen_paths: set[str] = set()

        for raw_path in raw_paths:
            normalized_path = raw_path.strip().strip("/")
            if not normalized_path or normalized_path in seen_paths:
                continue

            seen_paths.add(normalized_path)
            normalized_paths.append(normalized_path)

        return normalized_paths

    base_paths_env = os.getenv("GITHUB_BASE_PATHS")
    if base_paths_env and base_paths_env.strip():
        parsed_paths = _normalize_and_dedupe_paths(base_paths_env.split(","))
        if parsed_paths:
            return parsed_paths

        raise ValueError(
            "Invalid GITHUB_BASE_PATHS: no valid non-empty paths after normalization. "
            "Provide one or more comma-separated values such as "
            "'wnba/team_box/parquet,wnba/player_box/parquet'."
        )

    fallback_path = os.getenv("GITHUB_BASE_PATH", "wnba/team_box/parquet")
    parsed_fallback = _normalize_and_dedupe_paths([fallback_path])
    if parsed_fallback:
        return parsed_fallback

    raise ValueError(
        "Invalid GITHUB_BASE_PATH: no valid non-empty path after normalization. "
        "Example: 'wnba/team_box/parquet'."
    )


def _collect_files_for_paths(
    github_client: Any,
    *,
    base_paths: list[str],
    branch: str,
) -> list[Any]:
    """Aggregate parquet files for multiple source roots, deduplicated by path."""

    files_by_path: dict[str, Any] = {}
    for base_path in base_paths:
        discovered_files = github_client.list_parquet_files(base_path=base_path, branch=branch)
        for discovered_file in discovered_files:
            files_by_path[discovered_file.path] = discovered_file

    return sorted(files_by_path.values(), key=lambda file: file.path)


def _download_and_upload_file(
    storage_client: Any,
    *,
    blob_name: str,
    download_url: str,
    github_sha: str,
    timeout: int = 120,
) -> None:
    # Stream payload to avoid loading whole parquet files into memory.
    with requests.get(download_url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        response.raw.decode_content = True
        storage_client.upload_with_github_sha(
            blob_name=blob_name,
            content=response.raw,
            github_sha=github_sha,
            overwrite=True,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    start_time = time.perf_counter()
    branch = os.getenv("GITHUB_BRANCH", "main")
    base_paths = _parse_base_paths()
    max_files_env = os.getenv("SYNC_MAX_FILES")
    max_files = _parse_sync_max_files(max_files_env)
    strip_prefix = os.getenv("BLOB_STRIP_PREFIX", "wnba/").strip()

    github_client = build_default_client()
    storage_client = build_storage_client_from_env()

    files = _collect_files_for_paths(github_client, base_paths=base_paths, branch=branch)
    if max_files is not None:
        files = files[:max_files]

    logging.info(
        "discovered_parquet_files=%s base_paths=%s branch=%s",
        len(files),
        base_paths,
        branch,
    )

    new_files_uploaded = 0
    updated_files_uploaded = 0
    skipped_files = 0
    errored_files = 0

    for source_file in files:
        blob_name = storage_client.map_source_path_to_blob_name(
            source_file.path,
            strip_prefix=strip_prefix,
        )

        try:
            if not storage_client.blob_exists(blob_name):
                _download_and_upload_file(
                    storage_client,
                    blob_name=blob_name,
                    download_url=source_file.download_url,
                    github_sha=source_file.sha,
                )
                new_files_uploaded += 1
                logging.info(
                    "file_uploaded_new source_path=%s blob_name=%s sha=%s",
                    source_file.path,
                    blob_name,
                    source_file.sha,
                )
                continue

            existing_sha = storage_client.get_blob_github_sha(blob_name)
            if existing_sha == source_file.sha:
                skipped_files += 1
                logging.info(
                    "file_skipped_unchanged source_path=%s blob_name=%s sha=%s",
                    source_file.path,
                    blob_name,
                    source_file.sha,
                )
                continue

            _download_and_upload_file(
                storage_client,
                blob_name=blob_name,
                download_url=source_file.download_url,
                github_sha=source_file.sha,
            )
            updated_files_uploaded += 1
            logging.info(
                "file_uploaded_updated source_path=%s blob_name=%s old_sha=%s new_sha=%s",
                source_file.path,
                blob_name,
                existing_sha,
                source_file.sha,
            )
        except Exception:
            errored_files += 1
            logging.exception(
                "file_sync_error source_path=%s blob_name=%s",
                source_file.path,
                blob_name,
            )

    elapsed_seconds = time.perf_counter() - start_time
    summary = {
        "total_files_scanned": len(files),
        "new_files_uploaded": new_files_uploaded,
        "updated_files_uploaded": updated_files_uploaded,
        "files_skipped": skipped_files,
        "files_errored": errored_files,
        "execution_time_seconds": round(elapsed_seconds, 3),
    }

    logging.info("sync_summary %s", json.dumps(summary))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

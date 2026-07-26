"""GitHub API client for parquet file discovery."""

from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

from dotenv import load_dotenv
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout


GITHUB_API_BASE = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"


@dataclass(frozen=True)
class GitHubParquetFile:
    """Metadata required to sync a parquet file."""

    name: str
    path: str
    sha: str
    download_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "sha": self.sha,
            "download_url": self.download_url,
        }


class GitHubClient:
    """Thin wrapper around the GitHub REST API."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay_seconds: float = 60,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.timeout = timeout
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be >= 0")
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _get_json(self, url: str) -> Any:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except HTTPError as error:
                status_code = error.response.status_code if error.response is not None else None
                is_server_error = status_code is not None and 500 <= status_code < 600
                if not is_server_error or attempt >= self.max_retries:
                    raise
                last_error = error
            except (Timeout, ConnectionError) as error:
                if attempt >= self.max_retries:
                    raise
                last_error = error

            time.sleep(self.retry_delay_seconds)

        raise RuntimeError("Failed to fetch GitHub API response") from last_error

    def _list_contents(self, path: str, branch: str) -> list[dict[str, Any]]:
        encoded_path = path.strip("/")
        url = f"{GITHUB_API_BASE}/repos/{self.owner}/{self.repo}/contents/{encoded_path}?ref={branch}"
        data = self._get_json(url)

        if isinstance(data, list):
            return data
        return [data]

    def list_parquet_files(
        self,
        base_path: str = "wnba/team_box/parquet",
        branch: str = "main",
    ) -> list[GitHubParquetFile]:
        """Return all parquet files under a path in the repository."""

        parquet_files: list[GitHubParquetFile] = []
        pending_paths = [base_path.strip("/")]

        while pending_paths:
            current_path = pending_paths.pop()
            entries = self._list_contents(path=current_path, branch=branch)

            for entry in entries:
                entry_type = entry.get("type")
                entry_path = entry.get("path")
                if not entry_path:
                    continue

                if entry_type == "dir":
                    pending_paths.append(entry_path)
                    continue

                if entry_type != "file":
                    continue
                if not entry_path.endswith(".parquet"):
                    continue

                parquet_files.append(
                    GitHubParquetFile(
                        name=entry_path.rsplit("/", 1)[-1],
                        path=entry_path,
                        sha=entry["sha"],
                        download_url=entry.get("download_url")
                        or f"{RAW_BASE}/{self.owner}/{self.repo}/{branch}/{entry_path}",
                    )
                )

        parquet_files.sort(key=lambda file: file.path)
        return parquet_files


def build_default_client() -> GitHubClient:
    """Create a client configured from environment variables."""

    load_dotenv()

    owner = os.getenv("GITHUB_OWNER", "sportsdataverse")
    repo = os.getenv("GITHUB_REPO", "wehoop-wnba-data")
    token = os.getenv("GITHUB_TOKEN")
    return GitHubClient(owner=owner, repo=repo, token=token)

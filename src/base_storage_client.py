"""Abstract storage client contract used by sync operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class BaseStorageClient(ABC):
    """Storage operations required by the sync service."""

    @abstractmethod
    def blob_exists(self, blob_name: str) -> bool:
        """Return whether the target blob currently exists."""

    @abstractmethod
    def get_blob_metadata(self, blob_name: str) -> dict[str, str]:
        """Fetch metadata for a given blob name."""

    @abstractmethod
    def get_blob_github_sha(self, blob_name: str) -> str | None:
        """Return the stored GitHub SHA metadata value, if present."""

    @abstractmethod
    def upload_blob_bytes(
        self,
        blob_name: str,
        content: bytes | BinaryIO,
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload bytes to backing storage, optionally including metadata."""

    @abstractmethod
    def upload_with_github_sha(
        self,
        blob_name: str,
        content: bytes | BinaryIO,
        github_sha: str,
        overwrite: bool = True,
    ) -> None:
        """Upload content with SHA metadata included in the same write request."""

    @abstractmethod
    def map_source_path_to_blob_name(self, source_path: str, strip_prefix: str) -> str:
        """Map GitHub source path to destination blob name."""

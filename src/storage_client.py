"""Azure Blob storage client outline for sync operations."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import BinaryIO

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


@dataclass(frozen=True)
class StorageConfig:
    """Runtime configuration for Azure Blob storage access."""

    connection_string: str
    container_name: str
    metadata_sha_key: str = "github_sha"


class StorageClient:
    """Operations required by the sync service for blob state tracking."""

    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.connection_string = config.connection_string
        self.container_name = config.container_name
        self.metadata_sha_key = config.metadata_sha_key

        if not self.connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")
        if not self.container_name:
            raise ValueError("AZURE_STORAGE_CONTAINER is required")

        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )
        self.container_client = self.blob_service_client.get_container_client(
            self.container_name
        )

    def _get_blob_client(self, blob_name: str):
        return self.container_client.get_blob_client(blob_name)

    def blob_exists(self, blob_name: str) -> bool:
        """Return whether the target blob currently exists."""

        return self._get_blob_client(blob_name).exists()

    def get_blob_metadata(self, blob_name: str) -> dict[str, str]:
        """Fetch blob metadata for a given blob name."""

        blob_client = self._get_blob_client(blob_name)
        try:
            properties = blob_client.get_blob_properties()
        except ResourceNotFoundError:
            return {}
        return properties.metadata or {}

    def get_blob_github_sha(self, blob_name: str) -> str | None:
        """Return the stored GitHub SHA metadata value, if present."""

        metadata = self.get_blob_metadata(blob_name)
        return metadata.get(self.metadata_sha_key)

    def upload_blob_bytes(
        self,
        blob_name: str,
        content: bytes | BinaryIO,
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload bytes to blob storage, optionally including metadata."""

        self._get_blob_client(blob_name).upload_blob(
            content,
            overwrite=overwrite,
            metadata=metadata,
        )

    def set_blob_metadata(self, blob_name: str, metadata: dict[str, str]) -> None:
        """Set blob metadata for a blob."""

        self._get_blob_client(blob_name).set_blob_metadata(metadata=metadata)

    def upload_with_github_sha(
        self,
        blob_name: str,
        content: bytes | BinaryIO,
        github_sha: str,
        overwrite: bool = True,
    ) -> None:
        """Upload content with SHA metadata included in the same write request."""

        metadata = self.get_blob_metadata(blob_name)
        metadata[self.metadata_sha_key] = github_sha
        self.upload_blob_bytes(
            blob_name=blob_name,
            content=content,
            overwrite=overwrite,
            metadata=metadata,
        )

    def map_source_path_to_blob_name(self, source_path: str, strip_prefix: str) -> str:
        """Map GitHub source path to destination blob name."""

        normalized_source = source_path.lstrip("/")
        normalized_prefix = strip_prefix.strip("/")

        if normalized_prefix and normalized_source.startswith(f"{normalized_prefix}/"):
            return normalized_source[len(normalized_prefix) + 1 :]

        return normalized_source


def build_storage_config_from_env() -> StorageConfig:
    """Create storage config from environment variables."""

    load_dotenv()

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER", "")

    return StorageConfig(
        connection_string=connection_string,
        container_name=container_name,
        metadata_sha_key="github_sha",
    )


def build_storage_client_from_env() -> StorageClient:
    """Create storage client from environment variables."""

    return StorageClient(config=build_storage_config_from_env())

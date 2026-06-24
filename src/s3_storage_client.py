"""Amazon S3 storage client implementation for sync operations."""

from __future__ import annotations

from dataclasses import dataclass
import io
import os
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from base_storage_client import BaseStorageClient


@dataclass(frozen=True)
class S3StorageConfig:
    """Runtime configuration for Amazon S3 access."""

    bucket_name: str
    region_name: str | None = None
    endpoint_url: str | None = None
    key_prefix: str = ""
    metadata_sha_key: str = "github_sha"


class S3StorageClient(BaseStorageClient):
    """Operations required by the sync service for S3 object state tracking."""

    def __init__(self, config: S3StorageConfig) -> None:
        self.config = config
        self.bucket_name = config.bucket_name
        self.metadata_sha_key = config.metadata_sha_key
        self.key_prefix = config.key_prefix.strip("/")

        if not self.bucket_name:
            raise ValueError("AWS_S3_BUCKET is required")

        self.s3_client = boto3.client(
            "s3",
            region_name=config.region_name,
            endpoint_url=config.endpoint_url,
        )

    def _resolve_key(self, blob_name: str) -> str:
        normalized = blob_name.lstrip("/")
        if self.key_prefix:
            return f"{self.key_prefix}/{normalized}"
        return normalized

    def _head_object(self, blob_name: str) -> dict:
        object_key = self._resolve_key(blob_name)
        return self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)

    def blob_exists(self, blob_name: str) -> bool:
        """Return whether the target object currently exists."""

        try:
            self._head_object(blob_name)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def get_blob_metadata(self, blob_name: str) -> dict[str, str]:
        """Fetch object metadata for a given object key."""

        try:
            response = self._head_object(blob_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return {}
            raise

        metadata = response.get("Metadata") or {}
        return {str(key): str(value) for key, value in metadata.items()}

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
        """Upload bytes to S3, optionally including metadata."""

        object_key = self._resolve_key(blob_name)
        extra_args = {"Metadata": metadata or {}}

        if isinstance(content, bytes):
            stream: BinaryIO = io.BytesIO(content)
        else:
            stream = content

        if not overwrite and self.blob_exists(blob_name):
            raise FileExistsError(
                f"Object already exists in bucket '{self.bucket_name}': {object_key}"
            )

        self.s3_client.upload_fileobj(
            Fileobj=stream,
            Bucket=self.bucket_name,
            Key=object_key,
            ExtraArgs=extra_args,
        )

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
        """Map GitHub source path to destination object key suffix."""

        normalized_source = source_path.lstrip("/")
        normalized_prefix = strip_prefix.strip("/")

        if normalized_prefix and normalized_source.startswith(f"{normalized_prefix}/"):
            return normalized_source[len(normalized_prefix) + 1 :]

        return normalized_source


def build_s3_storage_config_from_env() -> S3StorageConfig:
    """Create S3 storage config from environment variables."""

    load_dotenv()

    region_name = (os.getenv("AWS_REGION") or "").strip() or None
    endpoint_url = (os.getenv("AWS_S3_ENDPOINT_URL") or "").strip() or None

    return S3StorageConfig(
        bucket_name=os.getenv("AWS_S3_BUCKET", ""),
        region_name=region_name,
        endpoint_url=endpoint_url,
        key_prefix=os.getenv("AWS_S3_KEY_PREFIX", ""),
        metadata_sha_key="github_sha",
    )


def build_s3_storage_client_from_env() -> S3StorageClient:
    """Create S3 storage client from environment variables."""

    return S3StorageClient(config=build_s3_storage_config_from_env())

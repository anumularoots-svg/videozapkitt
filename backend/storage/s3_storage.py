"""
S3 Storage Abstraction

Handles all file storage operations.
Uses MinIO locally, AWS S3 in production.
"""

from __future__ import annotations
import os
import boto3
from botocore.config import Config
from config import get_settings

settings = get_settings()


class S3Storage:
    """S3-compatible storage client."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.s3_bucket

    def ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def upload_file(self, local_path: str, s3_key: str) -> str:
        """Upload a file and return the S3 key."""
        self.client.upload_file(local_path, self.bucket, s3_key)
        return s3_key

    def download_file(self, s3_key: str, local_path: str):
        """Download a file from S3."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.client.download_file(self.bucket, s3_key, local_path)

    def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """Generate a presigned download URL."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

    def list_files(self, prefix: str) -> list[str]:
        """List files under a prefix."""
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]

    def delete_file(self, s3_key: str):
        """Delete a file."""
        self.client.delete_object(Bucket=self.bucket, Key=s3_key)

    def get_project_path(self, project_id: str) -> str:
        """Return the S3 prefix for a project."""
        return f"projects/{project_id}/"

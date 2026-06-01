"""S3 storage for application attachments."""

from __future__ import annotations

import uuid
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.config import settings


class AttachmentStorageError(Exception):
    """Raised when attachment storage operations fail."""


def _s3_client():
    kwargs: dict = {"region_name": settings.AWS_REGION}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def build_attachment_key(user_id: uuid.UUID, application_id: uuid.UUID, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")[:200]
    return f"attachments/{user_id}/{application_id}/{uuid.uuid4().hex}_{safe_name}"


def upload_attachment(
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    filename: str,
    content_type: str,
    body: BinaryIO,
    size_bytes: int,
) -> str:
    bucket = settings.AWS_S3_BUCKET_ATTACHMENTS
    if not bucket:
        raise AttachmentStorageError("AWS_S3_BUCKET_ATTACHMENTS is not configured")

    key = build_attachment_key(user_id, application_id, filename)
    client = _s3_client()
    try:
        client.upload_fileobj(
            Fileobj=body,
            Bucket=bucket,
            Key=key,
            ExtraArgs={
                "ContentType": content_type,
            },
        )
    except ClientError as exc:
        raise AttachmentStorageError(str(exc)) from exc
    return key


def delete_attachment(s3_key: str) -> None:
    bucket = settings.AWS_S3_BUCKET_ATTACHMENTS
    if not bucket or not s3_key:
        return
    client = _s3_client()
    try:
        client.delete_object(Bucket=bucket, Key=s3_key)
    except ClientError:
        # Best-effort delete; DB row is authoritative.
        pass


def generate_download_url(s3_key: str, *, filename: str, expires_in: int = 3600) -> str:
    bucket = settings.AWS_S3_BUCKET_ATTACHMENTS
    if not bucket:
        raise AttachmentStorageError("AWS_S3_BUCKET_ATTACHMENTS is not configured")
    client = _s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        raise AttachmentStorageError(str(exc)) from exc

"""S3 storage for user data export ZIP archives."""

from __future__ import annotations

import io
import uuid
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models.export import EXPORT_PRESIGNED_TTL_SECONDS


class ExportStorageError(Exception):
    """Raised when export storage operations fail."""


def _s3_client():
    kwargs: dict = {"region_name": settings.AWS_REGION}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def build_export_key(user_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"exports/{user_id}/{job_id}.zip"


def upload_export_zip(
    *,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    body: bytes | BinaryIO,
) -> str:
    bucket = settings.S3_EXPORT_BUCKET
    if not bucket:
        raise ExportStorageError("S3_EXPORT_BUCKET is not configured")

    key = build_export_key(user_id, job_id)
    client = _s3_client()
    fileobj = body if isinstance(body, io.IOBase) else io.BytesIO(body)
    try:
        client.upload_fileobj(
            Fileobj=fileobj,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/zip"},
        )
    except ClientError as exc:
        raise ExportStorageError(str(exc)) from exc
    return key


def generate_export_download_url(
    s3_key: str,
    *,
    expires_in: int = EXPORT_PRESIGNED_TTL_SECONDS,
) -> str:
    bucket = settings.S3_EXPORT_BUCKET
    if not bucket:
        raise ExportStorageError("S3_EXPORT_BUCKET is not configured")
    client = _s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ResponseContentDisposition": 'attachment; filename="smart_resume_export.zip"',
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        raise ExportStorageError(str(exc)) from exc


def delete_export_object(s3_key: str) -> None:
    bucket = settings.S3_EXPORT_BUCKET
    if not bucket or not s3_key:
        return
    client = _s3_client()
    try:
        client.delete_object(Bucket=bucket, Key=s3_key)
    except ClientError:
        pass


def delete_user_export_prefix(user_id: uuid.UUID) -> None:
    """Best-effort delete of all export objects for a user."""
    bucket = settings.S3_EXPORT_BUCKET
    if not bucket:
        return
    prefix = f"exports/{user_id}/"
    client = _s3_client()
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = page.get("Contents") or []
            if not objects:
                continue
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
    except ClientError:
        pass


__all__ = [
    "ExportStorageError",
    "build_export_key",
    "delete_export_object",
    "delete_user_export_prefix",
    "generate_export_download_url",
    "upload_export_zip",
]

"""Cloudflare R2 storage backend.

R2 speaks the S3 API, so we use boto3 with a custom endpoint URL. When R2
is configured, asset PUT/GET/DELETE go to R2; otherwise we fall back to
the existing Emergent Object Storage (storage_service).

Config (in /app/backend/.env):
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET (defaults to "nxt1-assets")
    R2_PUBLIC_BASE  (optional; e.g. https://assets.nxt1.app — if omitted we
                     use the standard r2.cloudflarestorage.com URL which
                     requires a presigned GET. For "real public" assets,
                     bind the bucket to a custom domain in CF and set this.)
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger("nxt1.r2")


def is_configured() -> bool:
    return bool(
        os.environ.get("R2_ACCOUNT_ID", "").strip()
        and os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        and os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    )


def _bucket() -> str:
    return (os.environ.get("R2_BUCKET") or "nxt1-assets").strip()


def status() -> dict:
    return {
        "configured": is_configured(),
        "bucket": _bucket() if is_configured() else None,
        "public_base": (os.environ.get("R2_PUBLIC_BASE") or "").strip() or None,
        "missing": [
            k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
            if not (os.environ.get(k) or "").strip()
        ],
    }


def _client():
    import boto3  # noqa
    from botocore.config import Config

    account_id = os.environ["R2_ACCOUNT_ID"].strip()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """No-op if the bucket exists; create it otherwise."""
    if not is_configured():
        raise RuntimeError("R2 not configured")
    s3 = _client()
    bucket = _bucket()
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        try:
            s3.create_bucket(Bucket=bucket)
            logger.info(f"created R2 bucket {bucket}")
        except Exception as e:
            # Race with parallel creators is fine; surface other failures.
            if "BucketAlreadyOwnedByYou" not in str(e) and "BucketAlreadyExists" not in str(e):
                raise


def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload bytes to R2. Returns {provider, bucket, path, size, public_url?}."""
    if not is_configured():
        raise RuntimeError("R2 not configured")
    ensure_bucket()
    s3 = _client()
    bucket = _bucket()
    s3.put_object(
        Bucket=bucket,
        Key=path,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    public_base = (os.environ.get("R2_PUBLIC_BASE") or "").strip().rstrip("/")
    public_url = f"{public_base}/{path}" if public_base else None
    return {
        "provider": "r2",
        "bucket": bucket,
        "path": path,
        "size": len(data),
        "public_url": public_url,
    }


def get_object(path: str) -> Tuple[bytes, str]:
    s3 = _client()
    obj = s3.get_object(Bucket=_bucket(), Key=path)
    body = obj["Body"].read()
    return body, obj.get("ContentType", "application/octet-stream")


def delete_object(path: str) -> None:
    s3 = _client()
    s3.delete_object(Bucket=_bucket(), Key=path)


def presigned_get(path: str, expires_in: int = 3600) -> str:
    s3 = _client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": path},
        ExpiresIn=int(expires_in),
    )

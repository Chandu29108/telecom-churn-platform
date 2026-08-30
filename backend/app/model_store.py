"""
Model storage abstraction — replaces the previous unconditional local-disk
persistence (storage/models/org_<id>/latest_model.joblib), which silently
loses every organization's trained model on any redeploy/restart on a
platform with an ephemeral filesystem (this includes Render's standard web
service disk).

Two backends:
- LocalModelStore: plain filesystem. Fine for local dev / docker-compose /
  running the test suite. NOT safe in production on ephemeral-disk hosts.
- R2ModelStore: Cloudflare R2 (S3-compatible object storage). Chosen over
  AWS S3 because R2's free tier (10GB, and — unlike S3 — no egress fees)
  needs only a Cloudflare account, not a full AWS billing setup, to start.
  Chosen over Supabase Storage because nothing else in this stack uses
  Supabase, so R2 doesn't pull in an unrelated vendor. Implemented against
  the standard boto3 S3 client — only the endpoint URL and credentials are
  R2-specific — so moving to real AWS S3 later is a config change, not a
  code change.

Selection is config-driven (get_model_store()), same pattern this codebase
already uses for the LLM provider (see llm/factory.py): if R2 credentials
are present, use R2; otherwise fall back to local disk. This means local
dev and the test suite keep working with zero extra setup, and production
only needs environment variables set — no code path changes between them.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import joblib

logger = logging.getLogger("churn_platform.model_store")


def _serialize(obj) -> bytes:
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    return buf.getvalue()


def _deserialize(data: bytes):
    return joblib.load(io.BytesIO(data))


class ModelNotFoundError(Exception):
    pass


class LocalModelStore:
    """Filesystem-backed store, one file per (org, version, artifact)."""

    name = "local"

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _path(self, org_id: int, version: int, artifact: str) -> Path:
        d = self.base_dir / f"org_{org_id}" / f"v{version}"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{artifact}.joblib"

    def save(self, org_id: int, version: int, artifact: str, obj) -> None:
        self._path(org_id, version, artifact).write_bytes(_serialize(obj))

    def load(self, org_id: int, version: int, artifact: str):
        path = self._path(org_id, version, artifact)
        if not path.exists():
            raise ModelNotFoundError(f"{path} not found")
        return _deserialize(path.read_bytes())


class R2ModelStore:
    """Cloudflare R2, addressed via the S3-compatible API. Key layout:
    org_<id>/models/v<version>/<artifact>.joblib — mirrors the local
    store's directory layout so the two are easy to reason about side by
    side, and keeps every org's artifacts under a distinct top-level
    prefix (defense in depth alongside the DB-level org_id scoping that
    already gates which version a request is even allowed to ask for)."""

    name = "r2"

    def __init__(self, bucket: str, endpoint_url: str, access_key: str, secret_key: str):
        import boto3  # imported lazily so boto3 isn't a hard dependency
        # for anyone running local-only dev without it installed.

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )

    def _key(self, org_id: int, version: int, artifact: str) -> str:
        return f"org_{org_id}/models/v{version}/{artifact}.joblib"

    def save(self, org_id: int, version: int, artifact: str, obj) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(org_id, version, artifact),
            Body=_serialize(obj),
        )

    def load(self, org_id: int, version: int, artifact: str):
        from botocore.exceptions import ClientError

        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._key(org_id, version, artifact))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise ModelNotFoundError(self._key(org_id, version, artifact)) from e
            raise
        return _deserialize(resp["Body"].read())


def get_model_store(local_dir: Path):
    """local_dir is passed in (rather than read from config directly here)
    so callers/tests that already point their own MODEL_DIR at an isolated
    tmp directory keep working unchanged when R2 isn't configured."""
    from .config import R2_BUCKET_NAME, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

    if R2_BUCKET_NAME and R2_ENDPOINT_URL and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
        return R2ModelStore(R2_BUCKET_NAME, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
    return LocalModelStore(local_dir)

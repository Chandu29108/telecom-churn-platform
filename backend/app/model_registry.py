"""
Shared model-version lifecycle logic, used by both routers/analysis.py
(training a new version on upload) and routers/prediction.py (loading the
active version for single-customer prediction) so the "what does it mean
for a version to be active" rule lives in exactly one place.

Replaces the old behaviour of unconditionally overwriting
storage/models/org_<id>/latest_model.joblib on every upload with labels —
that gave no way to tell which model is actually live, no history, and no
way to recover if a newly trained model turned out worse than the one it
replaced.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models_db import ModelVersion
from .model_store import get_model_store, ModelNotFoundError


def get_active_version(db: Session, org_id: int) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.org_id == org_id, ModelVersion.is_active == 1)
        .first()
    )


def load_active_model(db: Session, org_id: int, local_dir):
    """Returns (model, columns, ModelVersion) for the org's currently
    active model, or (None, None, None) if none has been trained yet."""
    version = get_active_version(db, org_id)
    if version is None:
        return None, None, None
    store = get_model_store(local_dir)
    try:
        model = store.load(org_id, version.version, "model")
        columns = store.load(org_id, version.version, "columns")
    except ModelNotFoundError:
        # DB says a version is active but its artifact is missing from the
        # configured store (e.g. someone switched R2 buckets, or a local
        # dev volume was wiped). Treat as "no model" rather than crashing
        # the request — same fallback the caller already has for orgs that
        # have never trained a model at all.
        return None, None, None
    return model, columns, version


def create_new_version(
    db: Session, org_id: int, run_id: int, model, columns: list,
    metrics: dict, row_count: int, created_by: int, local_dir,
) -> ModelVersion:
    """Saves the artifact to the configured store, deactivates whatever
    version was previously active for this org, and records the new one as
    active. Old versions are kept (not deleted) — that's the rollback
    path: reactivating an older ModelVersion row is a metadata change, the
    artifact itself is still sitting in the store under its own version
    number."""
    store = get_model_store(local_dir)

    last = (
        db.query(ModelVersion)
        .filter(ModelVersion.org_id == org_id)
        .order_by(ModelVersion.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1

    store.save(org_id, next_version, "model", model)
    store.save(org_id, next_version, "columns", columns)

    db.query(ModelVersion).filter(
        ModelVersion.org_id == org_id, ModelVersion.is_active == 1
    ).update({"is_active": 0})

    version = ModelVersion(
        org_id=org_id,
        version=next_version,
        run_id=run_id,
        storage_backend=store.name,
        metrics=metrics,
        feature_columns_count=len(columns),
        row_count=row_count,
        is_active=1,
        created_by=created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version

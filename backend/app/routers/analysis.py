"""
The core workflow: upload CSV -> engineer features -> train + evaluate ->
score every customer -> explain the highest-risk customers with SHAP ->
persist run + scores to Postgres, scoped to the caller's org -> return
dashboard-ready JSON (KPIs, charts, insights, recommendations).

Phase 2 change: this now runs ASYNCHRONOUSLY via FastAPI BackgroundTasks
instead of blocking the request. POST /upload does only cheap, fast
validation (extension, size, header sanity) and returns a Job immediately;
the actual training/SHAP/scoring work happens in _process_job, which the
frontend polls for via GET /jobs/{id}.

Every endpoint here requires auth and every query is filtered by
`current_user.org_id` — this is the multi-tenancy boundary. Trained models
are versioned per-org (see model_registry.py / model_store.py) so two
organizations never score against, or leak insight from, each other's
model, and so a newly trained model never silently replaces a working one
with no history or rollback path.

--- FastAPI BackgroundTasks: when it's enough, and when it isn't ---

Sufficient right now because: this is a single-process deployment, job
volume is low (one org uploads at a time in practice), and a job either
finishes within the request-response cycle's process lifetime or gets
recovered by the startup sweep below.

Becomes unsafe when ANY of these become true:
  - Multiple app instances/replicas run behind a load balancer — a
    BackgroundTask only runs on the instance that accepted the request, so
    there is no shared job queue across instances, and the startup-sweep
    recovery only helps the instance that restarts, not a job whose
    instance is simply gone (e.g. an autoscale-down).
  - Job volume/duration grows enough that jobs queue up waiting for a free
    thread in the process's threadpool (BackgroundTasks run sync functions
    via a threadpool, not a real scheduler) — there's no visibility into
    that queue depth today.
  - You need jobs to survive a deploy: a BackgroundTask in flight during a
    graceful shutdown is only as safe as however long the platform's
    shutdown grace period is; Render's is generous but not unlimited.
  - You need priority, delayed/scheduled jobs, or per-org fairness (one
    org's jobs shouldn't starve another's) — none of that exists here.

Migration trigger: the first time any of the above is true in production
— not hypothetically, but observed (e.g. two Render instances running, or
a job queue depth worth alerting on) — migrate to Celery + Redis (or a
managed queue). The Job model/table and the QUEUED/PROCESSING/COMPLETED/
FAILED/CANCELLED status contract are deliberately queue-agnostic: a Celery
task can write to the exact same `jobs` table and the polling API/frontend
would not need to change at all.
"""
import csv as csv_module
import io
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Request, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from .. import pipeline, insights as insight_engine
from ..database import get_db, SessionLocal as _SessionLocal
from ..deps import get_current_user, require_owner, require_verified
from ..models_db import AnalysisRun, CustomerScore, User, ModelVersion, Job, Organization
from ..config import (
    MODEL_DIR, UPLOAD_DIR, RATE_LIMIT_UPLOAD, MAX_UPLOAD_ROWS, MAX_UPLOAD_COLUMNS,
    MAX_JOB_RETRIES,
)
from ..ml import explainability
from ..model_registry import load_active_model, create_new_version
from ..audit import log_event

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
logger = logging.getLogger("churn_platform.analysis")
limiter = Limiter(key_func=get_remote_address)

# Module-level so tests can monkeypatch it to a test-isolated engine, the
# same pattern already used for MODEL_DIR in tests/conftest.py — the
# background task runs outside the request's dependency-injected `db`
# session (which is closed by the time the task starts), so it needs its
# own session factory reference.
SessionLocal = _SessionLocal

TOP_N_EXPLAIN = 50  # only explain as many rows as the dashboard actually shows
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB — generous for CSV, prevents unbounded memory use


def _job_temp_dir(org_id: int) -> Path:
    d = UPLOAD_DIR / f"org_{org_id}" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cleanup_temp_file(job: Job) -> None:
    if not job.temp_file_path:
        return
    try:
        p = Path(job.temp_file_path)
        if p.exists():
            p.unlink()
    except Exception:
        logger.exception("job.temp_file_cleanup_failed job_id=%s", job.id)


def _set_stage(db: Session, job: Job, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    db.commit()


def _process_job(job_id: int) -> None:
    """Runs in a FastAPI BackgroundTasks threadpool thread, AFTER the
    upload request has already returned a job_id to the client. Uses its
    own DB session (see SessionLocal above) since the request-scoped
    session is gone by the time this runs."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            logger.error("job.not_found_at_start job_id=%s", job_id)
            return
        if job.status == "CANCELLED":
            return

        job.status = "PROCESSING"
        job.started_at = datetime.utcnow()
        db.commit()
        log_event(db, None, "analysis.started", user_id=job.user_id, org_id=job.org_id,
                  resource_type="job", resource_id=job.id)

        try:
            with open(job.temp_file_path, "rb") as f:
                raw = f.read()

            _set_stage(db, job, "DATA_PREPARATION", 15)
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")

            if len(df) < 50:
                raise ValueError("Need at least 50 rows to produce a meaningful analysis.")

            # Personal (single-seat) workspaces default to a lower row cap
            # than organization accounts — see Organization.max_upload_rows
            # and PERSONAL_MAX_UPLOAD_ROWS in config.py. NULL means "use
            # the global MAX_UPLOAD_ROWS default", which is what every
            # pre-existing organization account has.
            org = db.query(Organization).filter(Organization.id == job.org_id).first()
            effective_max_rows = (org.max_upload_rows if org and org.max_upload_rows else MAX_UPLOAD_ROWS)
            if len(df) > effective_max_rows:
                raise ValueError(
                    f"File has {len(df):,} rows, which exceeds the current limit of "
                    f"{effective_max_rows:,} for your account. Split the file, or upgrade "
                    f"to an Organization account for a higher limit."
                )

            id_col = "mobile_number" if "mobile_number" in df.columns else None

            _set_stage(db, job, "FEATURE_ENGINEERING", 30)
            X, y = pipeline.engineer_features(df)
            eda = pipeline.eda_summary(df, y)

            metrics, feature_importance, risk_counts, scored, model = {}, [], {}, None, None
            new_model_columns = None

            if y is not None and y.nunique() == 2:
                _set_stage(db, job, "MODEL_TRAINING", 50)
                model, metrics, feature_importance = pipeline.train_and_evaluate(X, y)
                new_model_columns = list(X.columns)
                _set_stage(db, job, "MODEL_EVALUATION", 65)
                scored = pipeline.score_customers(model, X, df[id_col] if id_col else None)
            else:
                _set_stage(db, job, "MODEL_EVALUATION", 55)
                model, cols, _active_version = load_active_model(db, job.org_id, MODEL_DIR)
                if model is not None:
                    X = X.reindex(columns=cols, fill_value=0)
                    scored = pipeline.score_customers(model, X, df[id_col] if id_col else None)

            top_records = []
            if scored is not None:
                risk_counts = scored["risk_tier"].value_counts().to_dict()
                top_scored = scored.sort_values("churn_probability", ascending=False).head(TOP_N_EXPLAIN)
                top_records = top_scored.to_dict("records")

                if model is not None:
                    _set_stage(db, job, "SHAP_ANALYSIS", 80)
                    try:
                        X_top = X.loc[top_scored.index]
                        factor_lists = explainability.explain_batch(model, X_top, top_n=3)
                        for rec, factors in zip(top_records, factor_lists):
                            rec["top_factors"] = factors
                    except Exception:
                        logger.exception("SHAP explanation failed for job %s; continuing without it.", job_id)
                        for rec in top_records:
                            rec["top_factors"] = []

            _set_stage(db, job, "CUSTOMER_SCORING", 88)

            _set_stage(db, job, "INSIGHT_GENERATION", 93)
            insights_list = insight_engine.build_insights(eda, metrics, feature_importance, risk_counts)
            recommendations = insight_engine.build_recommendations(eda, feature_importance, risk_counts)

            run = AnalysisRun(
                filename=job.filename, row_count=len(df), trained=1 if metrics else 0,
                org_id=job.org_id, created_by=job.user_id, eda_summary=eda, metrics=metrics,
                feature_importance=feature_importance, risk_counts=risk_counts,
                insights=insights_list, recommendations=recommendations,
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            model_version = None
            if new_model_columns is not None:
                model_version = create_new_version(
                    db, job.org_id, run.id, model, new_model_columns,
                    metrics, len(df), job.user_id, MODEL_DIR,
                )

            if scored is not None:
                db.bulk_save_objects([
                    CustomerScore(
                        run_id=run.id, customer_id=str(row.customer_id),
                        churn_probability=float(row.churn_probability),
                        churn_flag=int(row.churn_flag), risk_tier=row.risk_tier,
                    )
                    for row in scored.itertuples()
                ])
                db.commit()
                # top_factors were computed only for the top-N explained
                # rows (top_records) — update those specific rows now that
                # they have real ids, rather than folding this into the
                # bulk_save_objects above (which doesn't return ids).
                if top_records:
                    factor_by_customer = {
                        str(r["customer_id"]): r.get("top_factors", [])
                        for r in top_records if "customer_id" in r
                    }
                    if factor_by_customer:
                        rows = (
                            db.query(CustomerScore)
                            .filter(CustomerScore.run_id == run.id,
                                    CustomerScore.customer_id.in_(factor_by_customer.keys()))
                            .all()
                        )
                        for r in rows:
                            r.top_factors = factor_by_customer.get(r.customer_id, [])
                        db.commit()

            job.status = "COMPLETED"
            job.stage = "COMPLETED"
            job.progress = 100
            job.row_count = len(df)
            job.analysis_run_id = run.id
            job.completed_at = datetime.utcnow()
            db.commit()
            _cleanup_temp_file(job)

            logger.info(
                "analysis.upload_completed org_id=%s user_id=%s job_id=%s run_id=%s rows=%s trained=%s",
                job.org_id, job.user_id, job.id, run.id, len(df), bool(metrics),
            )
            log_event(db, None, "analysis.completed", user_id=job.user_id, org_id=job.org_id,
                      resource_type="analysis_run", resource_id=run.id, metadata={"job_id": job.id})

        except Exception as e:
            db.rollback()
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error_message = str(e)[:1000]
                job.completed_at = datetime.utcnow()
                db.commit()
                logger.exception("analysis.upload_failed org_id=%s job_id=%s", job.org_id, job.id)
                log_event(db, None, "analysis.failed", user_id=job.user_id, org_id=job.org_id,
                          success=False, resource_type="job", resource_id=job.id,
                          metadata={"error": str(e)[:500]})
    finally:
        db.close()


@router.post("/upload", status_code=202)
@limiter.limit(RATE_LIMIT_UPLOAD)
async def upload_and_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (200MB limit).")

    # Fast, synchronous validation only — anything that requires actually
    # loading the full dataframe into memory (row/column counts, training)
    # happens in the background job, not here, so the request returns
    # quickly regardless of file size.
    try:
        header_line = raw.split(b"\n", 1)[0].decode("utf-8", errors="replace")
        header_fields = next(csv_module.reader([header_line]))
        seen, duplicate_cols = set(), []
        for h in header_fields:
            if h in seen and h not in duplicate_cols:
                duplicate_cols.append(h)
            seen.add(h)
        if duplicate_cols:
            raise HTTPException(
                400,
                f"File has duplicate column names ({', '.join(duplicate_cols[:5])}"
                f"{'...' if len(duplicate_cols) > 5 else ''}), which makes feature "
                f"engineering ambiguous. Please rename duplicate columns and re-upload.",
            )
        if len(header_fields) > MAX_UPLOAD_COLUMNS:
            raise HTTPException(
                413,
                f"File has {len(header_fields):,} columns, which exceeds the current "
                f"limit of {MAX_UPLOAD_COLUMNS:,}.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV header: {e}")

    # Duplicate-job guard: prevents the same org from stacking up several
    # heavy training jobs at once against a single-process BackgroundTasks
    # threadpool (see the module docstring's "when this becomes unsafe").
    existing = (
        db.query(Job)
        .filter(Job.org_id == current_user.org_id, Job.status.in_(["QUEUED", "PROCESSING"]))
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            f"An analysis (job #{existing.id}) is already in progress for your "
            f"organization. Wait for it to complete before starting another.",
        )

    # A quick row-count sanity check (cheap: just counts newlines) so an
    # obviously-too-small file fails fast instead of queueing a job that
    # will fail moments later — the authoritative row/column checks still
    # happen against the parsed dataframe inside the job itself.
    approx_rows = raw.count(b"\n")
    if approx_rows < 50:
        raise HTTPException(400, "Need at least 50 rows to produce a meaningful analysis.")

    temp_dir = _job_temp_dir(current_user.org_id)
    temp_path = temp_dir / f"{uuid.uuid4().hex}.csv"
    with open(temp_path, "wb") as f:
        f.write(raw)

    job = Job(
        org_id=current_user.org_id, user_id=current_user.id,
        filename=file.filename, status="QUEUED", stage="UPLOAD_VALIDATION",
        progress=0, temp_file_path=str(temp_path),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_event(db, request, "analysis.upload_queued", user_id=current_user.id,
              org_id=current_user.org_id, resource_type="job", resource_id=job.id,
              metadata={"filename": file.filename})

    background_tasks.add_task(_process_job, job.id)

    return _job_to_dict(job)


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id, "status": job.status, "stage": job.stage, "progress": job.progress,
        "error_message": job.error_message, "filename": job.filename, "row_count": job.row_count,
        "analysis_run_id": job.analysis_run_id, "retry_count": job.retry_count,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jobs = (
        db.query(Job)
        .filter(Job.org_id == current_user.org_id)
        .order_by(Job.created_at.desc())
        .limit(20)
        .all()
    )
    return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == current_user.org_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    return _job_to_dict(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified),
):
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == current_user.org_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status != "FAILED":
        raise HTTPException(400, "Only a failed job can be retried.")
    if not job.temp_file_path or not os.path.exists(job.temp_file_path):
        raise HTTPException(410, "The original upload is no longer available. Please re-upload the file.")
    if job.retry_count >= MAX_JOB_RETRIES:
        raise HTTPException(429, f"This job has already been retried {MAX_JOB_RETRIES} times. Please re-upload instead.")

    existing = (
        db.query(Job)
        .filter(Job.org_id == current_user.org_id, Job.status.in_(["QUEUED", "PROCESSING"]))
        .first()
    )
    if existing:
        raise HTTPException(409, f"An analysis (job #{existing.id}) is already in progress for your organization.")

    job.status = "QUEUED"
    job.stage = "UPLOAD_VALIDATION"
    job.progress = 0
    job.error_message = None
    job.retry_count += 1
    job.started_at = None
    job.completed_at = None
    db.commit()

    log_event(db, None, "analysis.retry", user_id=current_user.id, org_id=current_user.org_id,
              resource_type="job", resource_id=job.id, metadata={"retry_count": job.retry_count})

    background_tasks.add_task(_process_job, job.id)
    return _job_to_dict(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Best-effort cancellation: BackgroundTasks has no real interrupt
    mechanism once a job is PROCESSING, so this only reliably stops a job
    that's still QUEUED (hasn't started running yet). A PROCESSING job is
    marked CANCELLED but the underlying thread will run to completion —
    documented limitation, matches the module docstring's BackgroundTasks
    caveats."""
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == current_user.org_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status not in ("QUEUED", "PROCESSING"):
        raise HTTPException(400, "Only a queued or in-progress job can be cancelled.")

    job.status = "CANCELLED"
    job.completed_at = datetime.utcnow()
    db.commit()
    _cleanup_temp_file(job)
    log_event(db, None, "analysis.cancelled", user_id=current_user.id, org_id=current_user.org_id,
              resource_type="job", resource_id=job.id)
    return _job_to_dict(job)


@router.get("/models")
def list_model_versions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Model version history for the caller's org — what's live now, what
    it was trained on, and what came before it."""
    versions = (
        db.query(ModelVersion)
        .filter(ModelVersion.org_id == current_user.org_id)
        .order_by(ModelVersion.version.desc())
        .all()
    )
    return [
        {
            "version": v.version, "run_id": v.run_id, "metrics": v.metrics,
            "row_count": v.row_count, "is_active": bool(v.is_active),
            "storage_backend": v.storage_backend, "created_at": v.created_at,
        }
        for v in versions
    ]


@router.post("/models/{version}/activate")
def activate_model_version(
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Owner-only rollback: reactivate an older model version. The
    artifact was never deleted (create_new_version only deactivates, it
    doesn't remove old versions), so this is a metadata-only change —
    scoring/prediction picks up whichever version is is_active on its next
    request."""
    target = (
        db.query(ModelVersion)
        .filter(ModelVersion.org_id == current_user.org_id, ModelVersion.version == version)
        .first()
    )
    if not target:
        raise HTTPException(404, "Model version not found.")

    db.query(ModelVersion).filter(
        ModelVersion.org_id == current_user.org_id, ModelVersion.is_active == 1
    ).update({"is_active": 0})
    target.is_active = 1
    db.commit()

    logger.info(
        "analysis.model_activated org_id=%s version=%s by_user_id=%s",
        current_user.org_id, version, current_user.id,
    )
    log_event(db, None, "model.activated", user_id=current_user.id, org_id=current_user.org_id,
              resource_type="model_version", resource_id=target.id, metadata={"version": version})
    return {"version": target.version, "is_active": True}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.org_id == current_user.org_id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {"id": r.id, "filename": r.filename, "created_at": r.created_at,
         "row_count": r.row_count, "trained": bool(r.trained)}
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.org_id == current_user.org_id)
        .first()
    )
    if not run:
        raise HTTPException(404, "Run not found.")
    scores = db.query(CustomerScore).filter(CustomerScore.run_id == run_id) \
        .order_by(CustomerScore.churn_probability.desc()).limit(50).all()
    log_event(db, None, "analysis.accessed", user_id=current_user.id, org_id=current_user.org_id,
              resource_type="analysis_run", resource_id=run.id)
    return {
        "run_id": run.id,
        "filename": run.filename,
        "row_count": run.row_count,
        "trained": bool(run.trained),
        "eda_summary": run.eda_summary,
        "metrics": run.metrics,
        "feature_importance": run.feature_importance,
        "risk_counts": run.risk_counts,
        "insights": run.insights,
        "recommendations": run.recommendations,
        "top_high_risk_customers": [
            {"customer_id": s.customer_id, "churn_probability": s.churn_probability,
             "churn_flag": s.churn_flag, "risk_tier": s.risk_tier,
             "top_factors": s.top_factors or []}
            for s in scores
        ],
    }

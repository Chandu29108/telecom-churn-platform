"""
Chat-style Q&A over a single org's analysis results — "which segment
should I target this week", "why did the churn rate jump", etc. This is
deliberately NOT a general-purpose chatbot: the system prompt constrains
it to the specific run's JSON context and instructs it to say so rather
than invent numbers when the context doesn't have an answer. That's a
narrower, more defensible feature than a free-floating assistant, and it's
the exact wedge the market-research report flagged as the highest-value
differentiator competitors are only just starting to ship.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..deps import get_current_user
from ..models_db import AnalysisRun, User
from ..schemas import CopilotRequest, CopilotResponse
from ..llm.factory import get_llm_provider
from ..config import RATE_LIMIT_DEFAULT

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
logger = logging.getLogger("churn_platform.copilot")
limiter = Limiter(key_func=get_remote_address)

SYSTEM_PROMPT = (
    "You are a churn-analytics copilot for a telecom retention team. "
    "Answer ONLY using the analysis JSON context provided in the user "
    "message — never invent numbers, customer counts, or feature names "
    "that aren't present in it. If the context doesn't contain what's "
    "needed to answer, say so plainly and suggest what to upload or check "
    "instead. Be concise (3-6 sentences unless a list is clearer), "
    "business-focused, and specific — cite the actual numbers from the "
    "context rather than describing them vaguely."
)


@router.post("", response_model=CopilotResponse)
def ask(
    request: Request,
    payload: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(AnalysisRun).filter(AnalysisRun.org_id == current_user.org_id)
    run = (
        query.filter(AnalysisRun.id == payload.run_id).first()
        if payload.run_id
        else query.order_by(AnalysisRun.created_at.desc()).first()
    )
    if not run:
        raise HTTPException(404, "No analysis run found for your organization yet — upload a dataset first.")

    context = {
        "filename": run.filename,
        "row_count": run.row_count,
        "eda_summary": run.eda_summary,
        "metrics": run.metrics,
        "top_feature_importance": (run.feature_importance or [])[:10],
        "risk_counts": run.risk_counts,
        "insights": run.insights,
        "recommendations": run.recommendations,
    }
    user_prompt = f"Analysis context (JSON):\n{context}\n\nRetention team question: {payload.question}"

    provider = get_llm_provider()
    try:
        answer = provider.chat(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.warning("copilot provider=%s failed: %s", provider.name, e)
        raise HTTPException(
            503,
            f"The copilot's local LLM isn't reachable right now ({e}). "
            f"Make sure Ollama is running (`ollama serve`) and the model is "
            f"pulled (`ollama pull llama3.1`), then try again.",
        )

    return CopilotResponse(run_id=run.id, answer=answer, provider=provider.name)

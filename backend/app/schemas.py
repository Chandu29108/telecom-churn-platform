"""Pydantic response models — kept close to the DB/pipeline shapes so the
frontend gets predictable, typed JSON instead of loosely-shaped dicts."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters.")
    full_name: str
    # "organization": organization_name is required, creates/joins a
    # multi-seat org. "personal": organization_name is ignored — a
    # private, single-seat workspace is created automatically. See
    # routers/auth.py register() for the full branching logic.
    account_type: Literal["personal", "organization"] = "organization"
    organization_name: Optional[str] = None
    # Required to join an EXISTING organization (get this from an owner via
    # POST /api/auth/invites). Not needed when organization_name doesn't
    # match any existing org yet — that path creates a brand-new org and
    # the registering user becomes its owner. Always implies
    # account_type="organization" — you can't be invited into a personal
    # workspace, since those are single-seat by definition.
    invite_token: Optional[str] = None


class InviteCreate(BaseModel):
    expires_hours: int = Field(default=168, ge=1, le=720, description="Default 7 days, max 30.")


class InviteOut(BaseModel):
    id: int
    token: str
    org_id: int
    role: str
    expires_at: str
    used: bool


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    org_id: int
    organization_name: str
    account_type: str = "organization"
    role: str
    is_verified: bool = False

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class CheckoutOut(BaseModel):
    checkout_url: str


class BillingStatusOut(BaseModel):
    plan: str
    subscription_status: Optional[str] = None


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    event_type: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    success: bool
    ip_address: Optional[str]
    created_at: str
    metadata_: Optional[dict] = Field(default=None, alias="event_metadata")

    class Config:
        from_attributes = True
        populate_by_name = True


class JobOut(BaseModel):
    id: int
    status: str
    stage: str
    progress: int
    error_message: Optional[str] = None
    filename: str
    row_count: Optional[int] = None
    analysis_run_id: Optional[int] = None
    retry_count: int = 0
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# --------------------------------------------------------------------------- #
# Explainability (SHAP)
# --------------------------------------------------------------------------- #
class ExplanationFactor(BaseModel):
    feature: str
    impact: float          # signed SHAP value
    direction: str          # "increases_risk" | "decreases_risk"


# --------------------------------------------------------------------------- #
# Copilot
# --------------------------------------------------------------------------- #
class CopilotRequest(BaseModel):
    question: str
    run_id: Optional[int] = None


class CopilotResponse(BaseModel):
    run_id: int
    answer: str
    provider: str


class PredictRequest(BaseModel):
    """
    Single-customer prediction form. Fields map to the highest-importance
    features identified in the source notebook (Section 5 feature
    importance chart) so the form stays short but still meaningful —
    asking for all 169 engineered features in a UI would be unusable.
    """
    total_ic_mou_8: float
    total_ic_mou_7: float = 0
    total_ic_mou_6: float = 0
    last_day_rch_amt_8: float = 0
    roam_og_mou_8: float = 0
    total_rech_amt_8: float = 0
    total_rech_amt_7: float = 0
    total_rech_amt_6: float = 0
    arpu_8: float = 0
    arpu_7: float = 0
    arpu_6: float = 0
    aon: float = 365  # customer age-on-network, in days


class PredictResponse(BaseModel):
    churn_probability: float
    churn_flag: bool
    risk_tier: str
    confidence: float
    recommended_action: str
    explanation_mode: str  # "shap" | "heuristic"
    top_factors: list[ExplanationFactor] = []

"""API routes.  POST /api/generate drafts a document, POST /api/review checks one, GET /api/document-types
describes the form fields.  Generate and review need an API key when login is required (see auth.py) and
are rate limited per user (see ai_core/limits.py)."""
import os
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ai_core import DESCRIPTIONS, DOCUMENT_TYPES, generate_document, missing_required
from ai_core.document_schemas import to_dict
from ai_core.gemini_generator import LANGUAGES
from ai_core.india_legal import notices
from ai_core.limits import MAX_DOCUMENT_CHARS, RateLimitExceeded, check_and_consume, check_input_size
from ai_core.review import review_document
from auth import api_user

router = APIRouter(prefix="/api")


def current_user(x_api_key: str | None = Header(default=None)) -> str:
    """Who is calling? Sent as the `X-API-Key` header."""
    try:
        return api_user(x_api_key)
    except PermissionError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "ApiKey"})


def _spend(user: str, kind: str) -> None:
    try:
        check_and_consume(user, kind)
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": str(exc.retry_after)})


class GenerateRequest(BaseModel):
    doc_type: str
    effective_date: date
    language: str = "English"
    details: dict[str, str] = Field(default_factory=dict)   # field key -> value (see /api/document-types)
    parties: str = ""   # legacy single-string input, still accepted
    terms: str = ""     # legacy; same as details["additional_terms"]


class ReviewRequest(BaseModel):
    doc_type: str
    document: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    language: str = "English"
    use_ai: bool = True


@router.get("/document-types")
def document_types() -> dict:
    return {"languages": list(LANGUAGES),
            "types": [{"name": t, "description": DESCRIPTIONS[t], "fields": to_dict(t)} for t in DOCUMENT_TYPES]}


@router.post("/generate")
def generate(req: GenerateRequest, user: str = Depends(current_user)) -> dict:
    if req.doc_type not in DOCUMENT_TYPES:
        raise HTTPException(422, f"Unknown document type '{req.doc_type}'. Choose one of: {', '.join(DOCUMENT_TYPES)}")
    if req.language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported language '{req.language}'. Choose one of: {', '.join(LANGUAGES)}")
    details = dict(req.details)
    if req.parties.strip():
        details.setdefault("party1_name", req.parties.split(" and ")[0].strip())
        details.setdefault("party2_name", " and ".join(req.parties.split(" and ")[1:]).strip())
    missing = missing_required(req.doc_type, details)
    if missing:
        raise HTTPException(422, "Missing required field(s): " + ", ".join(missing))
    try:
        check_input_size(details, req.parties, req.terms)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _spend(user, "generate")          # only valid, in-size requests use up quota
    try:
        res = generate_document(req.doc_type, details, req.effective_date, terms=req.terms, language=req.language)
    except Exception:
        raise HTTPException(500, "Could not generate the document. Please try again.")   # no internals in the response
    return {"document": res.text, "source": res.source, "model": res.model, "warning": res.warning,
            "notices": [n._asdict() for n in notices(req.doc_type, details)]}


@router.post("/review")
def review(req: ReviewRequest, user: str = Depends(current_user)) -> dict:
    if req.doc_type not in DOCUMENT_TYPES:
        raise HTTPException(422, f"Unknown document type '{req.doc_type}'.")
    if req.language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported language '{req.language}'.")
    key = os.getenv("GEMINI_API_KEY", "").strip() if req.use_ai else ""
    if key:
        _spend(user, "review")        # rule-based checks are free; only the AI pass costs money
    res = review_document(req.doc_type, req.document, key, req.language)
    return {"issues": [i._asdict() for i in res.issues], "ai_used": res.ai_used, "model": res.model, "warning": res.warning}

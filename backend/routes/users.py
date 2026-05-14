"""User accounts: signup, signin, profile, onboarding.

Distinct from /api/auth/login (admin password gate). Token sub for users is
the user_id; verify_token accepts both since they share the same JWT secret.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import user_service

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.users")

router = APIRouter(prefix="/api", tags=["users"])


# ----- Models -----
class SignupIn(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""


class SigninIn(BaseModel):
    email: str
    password: str


class OnboardingIn(BaseModel):
    company: Optional[str] = ""
    use_case: Optional[str] = ""
    request: Optional[str] = ""
    referral: Optional[str] = ""


class AuthOut(BaseModel):
    token: str
    user: dict


async def _user_from_token(sub: str) -> Optional[dict]:
    if not sub or sub == "admin":
        return None
    return await db.users.find_one({"user_id": sub}, {"_id": 0})


async def require_admin(sub: str = Depends(verify_token)) -> str:
    if sub != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return sub


# ----- Admin: list / approve / deny user accounts -----
@router.get("/users")
async def list_users(_: str = Depends(require_admin)):
    cur = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(500)
    items = await cur.to_list(length=500)
    return {"items": [user_service.public_user(u) for u in items]}


class AccessUpdateIn(BaseModel):
    access_status: str  # "approved" | "denied" | "pending"


@router.post("/users/{user_id}/access")
async def update_user_access(user_id: str, body: AccessUpdateIn,
                             _: str = Depends(require_admin)):
    if body.access_status not in {"approved", "denied", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "access_status": body.access_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    rec = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user_service.public_user(rec)


# ----- Signup / Signin -----
@router.post("/users/signup", response_model=AuthOut)
async def signup(body: SignupIn):
    email = user_service.normalize_email(body.email)
    if not user_service.validate_email(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email.")
    perr = user_service.validate_password(body.password)
    if perr:
        raise HTTPException(status_code=400, detail=perr)
    existing = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="An account with that email already exists. Sign in instead.")
    rec = user_service.new_user_record(email, body.password, body.name or "")
    await db.users.insert_one(rec)
    token = user_service.make_user_token(rec["user_id"])
    return AuthOut(token=token, user=user_service.public_user(rec))


@router.post("/users/signin", response_model=AuthOut)
async def signin(body: SigninIn):
    email = user_service.normalize_email(body.email)
    rec = await db.users.find_one({"email": email}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=401, detail="No account with that email.")
    if not user_service.verify_password(body.password, rec.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = user_service.make_user_token(rec["user_id"])
    return AuthOut(token=token, user=user_service.public_user(rec))


# ----- Profile -----
@router.get("/users/me")
async def me(sub: str = Depends(verify_token)):
    rec = await _user_from_token(sub)
    if not rec:
        # Admin token has no profile
        if sub == "admin":
            return {"role": "admin", "user_id": "admin", "email": None,
                    "name": "Admin", "onboarded": True}
        raise HTTPException(status_code=404, detail="User not found")
    return user_service.public_user(rec)


@router.post("/users/me/onboarding")
async def submit_onboarding(body: OnboardingIn, sub: str = Depends(verify_token)):
    rec = await _user_from_token(sub)
    if not rec:
        raise HTTPException(status_code=404, detail="User not found")
    submission = {
        "company": (body.company or "")[:120],
        "use_case": (body.use_case or "")[:300],
        "request": (body.request or "")[:1500],
        "referral": (body.referral or "")[:120],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.update_one(
        {"user_id": rec["user_id"]},
        {"$set": {
            "onboarding": submission,
            "onboarded": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    # Cross-post into the existing access_requests collection so admin sees it
    try:
        await db.access_requests.insert_one({
            "id": __import__("uuid").uuid4().hex,
            "name": rec.get("name") or rec.get("email"),
            "email": rec.get("email"),
            "company": submission["company"],
            "message": submission["request"] or submission["use_case"],
            "status": "new",
            "notes": f"From signed-in user {rec.get('email')}. Use case: {submission['use_case']}. Referral: {submission['referral']}",
            "created_at": submission["submitted_at"],
            "updated_at": submission["submitted_at"],
            "source": "user_onboarding",
            "user_id": rec["user_id"],
        })
    except Exception as e:
        logger.warning(f"access_requests cross-post failed: {e}")
    return {"ok": True, "user": user_service.public_user({**rec, "onboarded": True})}

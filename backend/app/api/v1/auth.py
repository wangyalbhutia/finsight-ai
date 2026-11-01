from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, hash_token, decode_token
from app.core.config import settings
from app.core.deps import get_current_user, bearer
from fastapi.security import HTTPAuthorizationCredentials
from app.models.models import User, RefreshToken, AuditLog, RevokedAccessToken
from app.schemas.schemas import RegisterIn, LoginIn, RefreshIn, TokenOut
from datetime import datetime, timedelta, timezone
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])

def _issue(db, user, family_id=None):
    family_id = family_id or secrets.token_hex(16)
    access = create_access_token(user.id)
    refresh = create_refresh_token()
    exp = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh), family_id=family_id, expires_at=exp))
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user_id": user.id, "email": user.email}

@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    cur = data.preferred_currency or data.currency or "INR"
    user = User(email=data.email, full_name=data.full_name, hashed_password=hash_password(data.password), currency=cur, preferred_currency=cur)
    db.add(user); db.commit(); db.refresh(user)
    db.add(AuditLog(user_id=user.id, action="register", detail=user.email)); db.commit()
    return _issue(db, user)

@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    db.add(AuditLog(user_id=user.id, action="login", detail="")); db.commit()
    return _issue(db, user)

@router.post("/refresh")
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    h = hash_token(data.refresh_token)
    rec = db.query(RefreshToken).filter(RefreshToken.token_hash == h).first()
    if not rec:
        raise HTTPException(401, "Invalid refresh token")
    # REUSE DETECTION: presenting a revoked/rotated token revokes the whole family
    if rec.revoked:
        db.query(RefreshToken).filter(RefreshToken.family_id == rec.family_id).update({"revoked": True})
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected; token family revoked")
    exp = rec.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < datetime.now(timezone.utc):
        rec.revoked = True; db.commit(); raise HTTPException(401, "Refresh token expired")
    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(401, "User not found")
    # rotation: old token revoked, new token in same family
    rec.revoked = True; db.commit()
    return _issue(db, user, family_id=rec.family_id)

@router.post("/logout")
def logout(data: RefreshIn = None, db: Session = Depends(get_db), current: User = Depends(get_current_user), creds: HTTPAuthorizationCredentials = Depends(bearer)):
    # revoke access token via denylist (jti)
    try:
        payload = decode_token(creds.credentials)
        jti = payload.get("jti")
        if jti:
            exp_ts = payload.get("exp")
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None
            if not db.query(RevokedAccessToken).filter(RevokedAccessToken.jti == jti).first():
                db.add(RevokedAccessToken(jti=jti, user_id=current.id, expires_at=exp_dt))
    except Exception:
        pass
    # revoke refresh tokens: specific if supplied, otherwise all for user
    if data and data.refresh_token:
        rec = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(data.refresh_token), RefreshToken.user_id == current.id).first()
        if rec:
            rec.revoked = True
    else:
        db.query(RefreshToken).filter(RefreshToken.user_id == current.id).update({"revoked": True})
    db.add(AuditLog(user_id=current.id, action="logout", detail="")); db.commit()
    return {"detail": "Logged out"}

@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return {"id": current.id, "email": current.email, "full_name": current.full_name, "currency": getattr(current, "currency", "INR") or "INR", "preferred_currency": getattr(current, "preferred_currency", "INR") or "INR"}

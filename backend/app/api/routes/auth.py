from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_iccc, require_roles
from app.models.user import User, UserRole
from app.schemas.common import FieldBoothIn, FieldBoothOut, FieldJoinIn, LoginIn, MeOut, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password
from app.services.field_booth import MAX_JOINS, current_booth, issue_booth, redeem_booth
from app.services.rate_limit import client_ip, enforce, gate
from app.services.refs import ensure_bus, normalize_bus_code

router = APIRouter(prefix="/auth", tags=["auth"])


def _booth_out(booth) -> FieldBoothOut:
    return FieldBoothOut(
        code=booth.code,
        expires_in=booth.expires_in,
        redeemed=booth.redeemed,
        bus_code=booth.bus_code,
        joins=booth.joins,
        max_joins=getattr(booth, "max_joins", MAX_JOINS),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    lock_key = f"login:{email}"
    gate.check(lock_key)
    enforce(f"login:{client_ip(request)}:{email}", limit=8, window_s=300)
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        gate.fail(lock_key, limit=5, window_s=900, lock_s=900)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    gate.ok(lock_key)
    token = create_access_token(user.id, user.role.value, scope="iccc")
    return TokenOut(access_token=token, role=user.role, user_id=user.id, full_name=user.full_name, scope="iccc")


@router.post("/register", response_model=UserOut)
def register(
    body: RegisterIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        scope=getattr(user, "auth_scope", "iccc"),
    )


@router.post("/field-booth", response_model=FieldBoothOut)
def open_field_booth(body: FieldBoothIn, db: Session = Depends(get_db), user: User = Depends(require_iccc)):
    try:
        bus_code = normalize_bus_code(body.bus_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_bus(db, bus_code)
    db.commit()
    booth = issue_booth(user_id=user.id, role=user.role.value, full_name=user.full_name, bus_code=bus_code)
    return _booth_out(booth)


@router.get("/field-booth", response_model=FieldBoothOut)
def read_field_booth(_: User = Depends(require_iccc)):
    booth = current_booth()
    if booth is None:
        raise HTTPException(status_code=404, detail="No live field booth. Arm one from Overview.")
    return _booth_out(booth)


@router.post("/field-join", response_model=TokenOut)
def join_field_booth(body: FieldJoinIn, request: Request, db: Session = Depends(get_db)):
    pin_key = f"field-join:{client_ip(request)}"
    gate.check(pin_key)
    enforce(pin_key, limit=10, window_s=300)
    try:
        booth = redeem_booth(body.code)
    except ValueError as exc:
        gate.fail(pin_key, limit=6, window_s=900, lock_s=900)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    gate.ok(pin_key)
    user = db.get(User, booth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Field booth officer is no longer active")
    token = create_access_token(user.id, user.role.value, scope="field")
    return TokenOut(
        access_token=token,
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
        scope="field",
        bus_code=booth.bus_code,
    )

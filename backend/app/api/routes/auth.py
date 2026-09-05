from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.common import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id, user.role.value)
    return TokenOut(access_token=token, role=user.role, user_id=user.id, full_name=user.full_name)


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


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

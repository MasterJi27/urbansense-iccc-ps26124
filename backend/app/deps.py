from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {
    UserRole.OPERATOR: 1,
    UserRole.INSPECTOR: 2,
    UserRole.ADMIN: 3,
    UserRole.SUPER_ADMIN: 4,
}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_roles(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if not roles:
            return user
        required_rank = min(ROLE_RANK.get(r, 0) for r in roles)
        user_rank = ROLE_RANK.get(user.role, 0)
        if user_rank < required_rank:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker

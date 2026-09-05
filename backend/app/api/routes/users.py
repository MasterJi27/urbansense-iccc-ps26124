from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.user import User, UserRole
from app.schemas.common import UserOut

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    return db.query(User).all()

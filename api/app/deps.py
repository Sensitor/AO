import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Subscription, User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    sub = decode_token(token)
    if not sub:
        raise credentials_error
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise credentials_error
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_error
    return user


def require_active_subscription(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Gate les actions à valeur derrière un abonnement actif.

    Opt-in : si `STRIPE_SECRET_KEY` est vide, la facturation est désactivée et
    tout passe (mode dev/gratuit).
    """
    if not settings.stripe_secret_key:
        return user
    sub = (
        db.query(Subscription).filter(Subscription.org_id == user.org_id).first()
    )
    if sub and sub.status in {"active", "trialing"}:
        return user
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="Abonnement actif requis pour cette action.",
    )

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in User from a request's Authorization header.

    Future endpoints
    import this and add `user: User = Depends(get_current_user)` as a
    parameter - FastAPI runs this automatically before their own code,
    and rejects the request with 401 if it raises here.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    subject = decode_access_token(token)
    if subject is None:
        raise credentials_exception

    # A token whose subject isn't a number (e.g. "abc") would make int()
    # crash with a 500. Treat it as an invalid token and return 401 instead.
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise credentials_exception from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user
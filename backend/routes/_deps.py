"""Shared FastAPI dependencies + db handle for the modular route packages."""
import os
import jwt
from fastapi import Depends, Header, HTTPException, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient

# Single shared Mongo client / db
_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET", "nxt1-secret")
JWT_ALG = "HS256"


def verify_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    return verify_token_value(token)


def verify_token_value(token: str) -> str:
    """Raw token verification (used by WebSocket auth-via-query)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    return payload.get("sub", "admin")


__all__ = ["db", "verify_token", "verify_token_value",
            "Depends", "Header", "HTTPException", "Query"]

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.auth.jwt_auth import verify_api_key, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
_limiter = Limiter(key_func=get_remote_address)


class TokenRequest(BaseModel):
    api_key: str


@router.post("/token")
@_limiter.limit("10/minute")
def get_token(request: Request, body: TokenRequest) -> dict:
    if not verify_api_key(body.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return {"access_token": create_access_token(), "token_type": "bearer"}

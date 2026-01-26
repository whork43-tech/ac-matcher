# auth.py
from __future__ import annotations

import os
from typing import Optional

from fastapi import Request
from fastapi.responses import Response
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ✅ 建議你改成環境變數：APP_SECRET="一串很長很亂的字"
SECRET = os.getenv("APP_SECRET", "change-me-to-a-long-random-secret")
serializer = URLSafeSerializer(SECRET, salt="session")

COOKIE_NAME = "ac_session"


def hash_password(password: str) -> str:
    return pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd.verify(password, password_hash)


def set_session(resp: Response, user_id: int) -> None:
    token = serializer.dumps({"user_id": user_id})
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
    )


def clear_session(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME)


def get_user_id(request: Request) -> Optional[int]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = serializer.loads(token)
        return int(data.get("user_id"))
    except (BadSignature, ValueError, TypeError):
        return None

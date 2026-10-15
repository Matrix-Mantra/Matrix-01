"""Login.

AUTH_MODE=firebase: the browser signs in with Google through Firebase Authentication and sends the
                    Firebase ID token as "Authorization: Bearer <token>". We verify it with google-auth.
AUTH_MODE=dev:      for local testing and demos. The browser sends "Bearer dev:<name>". Never use on a
                    public site you care about: anyone can type any name.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Header, HTTPException

from . import config


@dataclass(frozen=True)
class User:
    uid: str
    name: str


def _short_name(full: str) -> str:
    """Show reviewers as first name + initial for privacy, e.g. 'Sita K.'"""
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    if not parts:
        return "User"
    return parts[0][:24] + (f" {parts[-1][0]}." if len(parts) > 1 else "")


def _verify_firebase(token: str) -> User:
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_firebase_token(token, ga_requests.Request(),
                                                audience=config.FIREBASE_WEB_CONFIG["projectId"])
    except Exception as exc:
        raise HTTPException(401, "Login expired. Please log in again.") from exc
    if not claims or not claims.get("sub"):
        raise HTTPException(401, "Invalid login.")
    return User(uid=claims["sub"], name=_short_name(claims.get("name") or claims.get("email", "").split("@")[0]))


def _verify_dev(token: str) -> User:
    if not token.startswith("dev:"):
        raise HTTPException(401, "Invalid login.")
    name = token[4:].strip()[:40]
    if not name:
        raise HTTPException(401, "Invalid login.")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "user"
    return User(uid=f"dev-{slug}", name=_short_name(name))


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in.")
    token = authorization[7:].strip()
    if config.AUTH_MODE == "firebase":
        return _verify_firebase(token)
    return _verify_dev(token)


# ------------------------------------------------------------------ simple per-user daily limits

_usage: dict[tuple[str, str, int], int] = defaultdict(int)


def check_limit(user: User, action: str, limit: int) -> None:
    day = int(time.time() // 86400)
    key = (user.uid, action, day)
    if _usage[key] >= limit:
        raise HTTPException(429, "Daily limit reached. Please try again tomorrow.")
    _usage[key] += 1

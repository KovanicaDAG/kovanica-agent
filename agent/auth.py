"""Real JWT-based authentication for the Kovanica DevTeam Agent.

Two modes:

* JWKS mode (production): when ``AUTH_JWKS_URL`` is set, ``Authorization:
  Bearer <jwt>`` is verified against the JWKS published at that URL using
  PyJWT. The ``iss`` and ``aud`` claims are validated when ``AUTH_ISSUER`` /
  ``AUTH_AUDIENCE`` are configured, and exp is always enforced. A token whose
  roles intersect ``AUTH_DEV_ROLES`` maps to ``dev``; otherwise ``user``.

* Dev/offline mode: when ``AUTH_JWKS_URL`` is empty, authentication falls back
  to a shared secret bearer token from ``AUTH_DEV_TOKEN``. A request carrying
  ``Authorization: Bearer <AUTH_DEV_TOKEN>`` is ``dev``; every other request
  is ``user`` (fail-closed for dev). If ``AUTH_DEV_TOKEN`` is also empty,
  everyone defaults to ``user``.

A client-supplied role is never trusted directly; it is always derived from the
verified token (or the dev token) server-side.
"""

import os
import time
from typing import Any

from fastapi import HTTPException

__all__ = ["verify_token", "resolve_role"]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


JWKS_URL = _env("AUTH_JWKS_URL")
ISSUER = _env("AUTH_ISSUER")
AUDIENCE = _env("AUTH_AUDIENCE")
DEV_ROLES = {r for r in _env("AUTH_DEV_ROLES").split(",") if r}
DEV_TOKEN = _env("AUTH_DEV_TOKEN")

try:  # optional at import time so the module always imports
    import jwt  # PyJWT
    from jwt import PyJWKClient
    _JWT_AVAILABLE = True
    _jwt, _PyJWKClient = jwt, PyJWKClient
except Exception:  # pragma: no cover - import fallback
    _JWT_AVAILABLE = False
    _jwt, _PyJWKClient = None, None


def _error(msg: str, status: int = 401) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


def _decode_claims(token: str, jwks_client: Any) -> dict:
    """Verify a raw JWT against the JWKS and return its decoded claims."""
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    options = {"verify_exp": True, "verify_iss": bool(ISSUER),
               "verify_aud": bool(AUDIENCE)}
    kwargs: dict = {"algorithms": ["RS256"],
                    "options": options}
    if ISSUER:
        kwargs["issuer"] = ISSUER
    if AUDIENCE:
        kwargs["audience"] = AUDIENCE
    return _jwt.decode(token, signing_key.key, **kwargs)


def _claims_to_role(claims: dict) -> str:
    """Map decoded claims to 'dev' or 'user' via AUTH_DEV_ROLES."""
    granted = set(claims.get("roles") or [])
    realm = claims.get("realm_access") or {}
    if isinstance(realm, dict):
        granted |= set(realm.get("roles") or [])
    if DEV_ROLES and granted & DEV_ROLES:
        return "dev"
    return "user"


# Cache the JWKS client (Keycloak keys are rotated rarely); PyJWKClient already
# handles refresh, but we additionally cap it behind a short TTL.
_jwks_client = None
_jwks_client_ts = 0.0
_JWKS_TTL = float(_env("AUTH_JWKS_TTL", "300") or 300)


def _get_jwks_client() -> Any:
    global _jwks_client, _jwks_client_ts
    now = time.time()
    if _jwks_client is None or now - _jwks_client_ts > _JWKS_TTL:
        _jwks_client = _PyJWKClient(JWKS_URL)
        _jwks_client_ts = now
    return _jwks_client


def _verify_token_jwks(authorization: str) -> str:
    """JWKS mode: verify a Bearer JWT and return the derived role."""
    if not _JWT_AVAILABLE:
        raise _error(
            "JWT authentication is enabled (AUTH_JWKS_URL set) but the PyJWT "
            "library is not installed. Install 'PyJWT' and 'cryptography'.",
            status=500,
        )
    token = _extract_bearer(authorization)
    claims = _decode_claims(token, _get_jwks_client())
    return _claims_to_role(claims)


def _extract_bearer(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise _error("Missing or malformed Authorization header")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise _error("Missing or malformed Authorization header")
    return token


def _verify_token_dev(authorization: str) -> str:
    """Dev/offline mode: match the shared secret bearer token."""
    if authorization == f"Bearer {DEV_TOKEN}":
        return "dev"
    return "user"


def verify_token(authorization: str | None) -> str:
    """Verify ``Authorization`` and return ``"dev"`` or ``"user"``.

    Raises ``HTTPException(401)`` on a missing/invalid credential and
    ``HTTPException(403)`` for a role denial that is explicitly surfaced. In
    dev/offline mode a non-dev credential never raises; it simply yields
    ``"user"``.
    """
    auth = authorization or ""
    if JWKS_URL:
        return _verify_token_jwks(auth)
    return _verify_token_dev(auth)


def resolve_role(authorization: str | None) -> str:
    """Wrapper kept for backwards compatibility.

    Delegates to :func:`verify_token`; any verification failure is translated
    into a 403 rather than propagating a 401, so unauthorised callers see a
    uniform forbidden response.
    """
    try:
        return verify_token(authorization)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise
        raise _error(exc.detail, status=403) from exc

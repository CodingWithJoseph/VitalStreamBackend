import hashlib

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vitalstream.config import Settings

bearer = HTTPBearer(auto_error=False)


class Authenticator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = jwt.PyJWKClient(settings.oidc_jwks_url, timeout=5, lifespan=300)

    def __call__(self, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None:
            raise HTTPException(
                401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            key = self.keys.get_signing_key_from_jwt(credentials.credentials).key
            claims = jwt.decode(
                credentials.credentials,
                key,
                algorithms=["RS256"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer_url,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise jwt.InvalidTokenError("Missing subject")
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(503, "Identity provider temporarily unavailable") from None
        except jwt.PyJWTError:
            raise HTTPException(
                401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}
            ) from None
        # Ownership never comes from a body/path/header chosen by the caller.
        return hashlib.sha256(f"{claims['iss']}\0{claims['sub']}".encode()).hexdigest()

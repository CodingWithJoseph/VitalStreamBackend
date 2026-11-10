from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./vitalstream.db"
    oidc_issuer_url: str = "http://10.0.2.2:8080/realms/vitalstream"
    oidc_audience: str = "vitalstream-api"
    oidc_jwks_url: str = "http://localhost:8080/realms/vitalstream/protocol/openid-connect/certs"
    allow_synthetic: bool = True

    @model_validator(mode="after")
    def production_configuration(self):
        if self.environment == "production":
            if not all(
                url.startswith("https://") for url in (self.oidc_issuer_url, self.oidc_jwks_url)
            ):
                raise ValueError("Production OIDC endpoints must use HTTPS")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if self.allow_synthetic:
                raise ValueError("Production must disable synthetic uploads")
        return self

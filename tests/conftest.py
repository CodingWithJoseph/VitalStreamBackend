import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from vitalstream.config import Settings
from vitalstream.database import Base, Observation
from vitalstream.main import create_app


@pytest.fixture
def client(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    if not url.startswith("sqlite"):
        assert make_url(url).database.endswith("_test"), "Use a dedicated *_test database"
    app = create_app(Settings(database_url=url, _env_file=None))
    Base.metadata.create_all(app.state.engine)
    with app.state.engine.begin() as connection:
        connection.execute(delete(Observation))
    app.dependency_overrides[app.state.auth] = lambda: "alice"
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def record():
    identifier = str(uuid4())
    return dict(
        id=identifier,
        source="synthetic",
        source_record_id=identifier,
        revision=1,
        value=62.0,
        unit="bpm",
        metric="resting_heart_rate",
        synthetic=True,
        observed_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )


@pytest.fixture
def signed_client(client, monkeypatch):
    client.app.dependency_overrides.clear()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        client.app.state.auth.keys,
        "get_signing_key_from_jwt",
        lambda _: SimpleNamespace(key=key.public_key()),
    )

    def token(**changes):
        now = datetime.now(UTC)
        claims = dict(
            sub="alice",
            iss=client.app.state.auth.settings.oidc_issuer_url,
            aud="vitalstream-api",
            iat=now,
            exp=now + timedelta(minutes=5),
        )
        claims.update(changes)
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}

    return client, token
